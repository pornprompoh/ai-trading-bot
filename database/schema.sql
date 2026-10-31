create table if not exists public.trading_accounts (
    id uuid primary key default gen_random_uuid(),
    login bigint not null,
    server text not null,
    balance numeric(18, 2) not null default 0,
    updated_at timestamptz not null default now(),
    constraint unique_login_server unique (login, server)
);

-- Migrate installations created with an older schema (including last_balance).
alter table public.trading_accounts
    add column if not exists balance numeric(18, 2);

do $$
begin
    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'trading_accounts'
          and column_name = 'last_balance'
    ) then
        execute '
            update public.trading_accounts
            set balance = last_balance
            where last_balance is not null
              and (balance is null or balance = 0)
        ';
    end if;
end
$$;

update public.trading_accounts set balance = 0 where balance is null;
alter table public.trading_accounts
    alter column balance set default 0,
    alter column balance set not null;

-- Reuse an existing unique(login, server) key where possible; otherwise add it.
do $$
declare
    login_attnum smallint;
    server_attnum smallint;
    existing_constraint text;
begin
    select attnum into login_attnum
    from pg_attribute
    where attrelid = 'public.trading_accounts'::regclass
      and attname = 'login' and not attisdropped;

    select attnum into server_attnum
    from pg_attribute
    where attrelid = 'public.trading_accounts'::regclass
      and attname = 'server' and not attisdropped;

    select conname into existing_constraint
    from pg_constraint
    where conrelid = 'public.trading_accounts'::regclass
      and contype = 'u'
      and cardinality(conkey) = 2
      and conkey @> array[login_attnum, server_attnum]::smallint[]
    limit 1;

    if existing_constraint is null then
        alter table public.trading_accounts
            add constraint unique_login_server unique (login, server);
    elsif existing_constraint <> 'unique_login_server' then
        if exists (
            select 1 from pg_constraint
            where conrelid = 'public.trading_accounts'::regclass
              and conname = 'unique_login_server'
        ) then
            raise exception
                'Constraint unique_login_server exists but is not UNIQUE(login, server).';
        end if;
        execute format(
            'alter table public.trading_accounts rename constraint %I to unique_login_server',
            existing_constraint
        );
    end if;
end
$$;

create table if not exists public.trades (
    id uuid primary key default gen_random_uuid(),
    account_id uuid not null references public.trading_accounts(id),
    ticket bigint not null unique,
    symbol text not null,
    side text not null check (side in ('BUY', 'SELL')),
    volume numeric(18, 8) not null check (volume > 0),
    open_price numeric(18, 8) not null,
    stop_loss numeric(18, 8) not null,
    take_profit numeric(18, 8) not null,
    context jsonb not null default '{}'::jsonb,
    opened_at timestamptz not null,
    timeframe text,
    status text not null default 'open' check (status in ('open', 'closed')),
    close_price numeric(18, 8),
    profit_loss numeric(18, 2),
    exit_reason text,
    closed_at timestamptz
);

alter table public.trades
    add column if not exists context jsonb not null default '{}'::jsonb;

create table if not exists public.ai_trade_logs (
    id uuid primary key default gen_random_uuid(),
    trade_id uuid not null unique references public.trades(id) on delete cascade,
    indicators jsonb not null default '{}'::jsonb,
    timeframe text,
    reasoning text not null,
    context jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

alter table public.ai_trade_logs
    add column if not exists context jsonb not null default '{}'::jsonb;

create table if not exists public.account_equity_snapshots (
    id uuid primary key default gen_random_uuid(),
    account_id uuid not null references public.trading_accounts(id) on delete cascade,
    balance numeric(18, 2) not null,
    equity numeric(18, 2) not null,
    margin numeric(18, 2) not null default 0,
    free_margin numeric(18, 2) not null default 0,
    captured_at timestamptz not null default now()
);

create index if not exists account_equity_snapshots_account_captured_idx
    on public.account_equity_snapshots (account_id, captured_at desc);

create table if not exists public.dashboard_account_access (
    user_id uuid not null references auth.users(id) on delete cascade,
    account_id uuid not null references public.trading_accounts(id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (user_id, account_id)
);

alter table public.trading_accounts enable row level security;
alter table public.trades enable row level security;
alter table public.ai_trade_logs enable row level security;
alter table public.account_equity_snapshots enable row level security;
alter table public.dashboard_account_access enable row level security;

drop policy if exists "Users can read their dashboard account access"
    on public.dashboard_account_access;
create policy "Users can read their dashboard account access"
    on public.dashboard_account_access for select to authenticated
    using (user_id = (select auth.uid()));

drop policy if exists "Users can read assigned trading accounts"
    on public.trading_accounts;
create policy "Users can read assigned trading accounts"
    on public.trading_accounts for select to authenticated
    using (
        exists (
            select 1 from public.dashboard_account_access access
            where access.account_id = trading_accounts.id
              and access.user_id = (select auth.uid())
        )
    );

drop policy if exists "Users can read assigned trades"
    on public.trades;
create policy "Users can read assigned trades"
    on public.trades for select to authenticated
    using (
        exists (
            select 1 from public.dashboard_account_access access
            where access.account_id = trades.account_id
              and access.user_id = (select auth.uid())
        )
    );

drop policy if exists "Users can read assigned AI trade logs"
    on public.ai_trade_logs;
create policy "Users can read assigned AI trade logs"
    on public.ai_trade_logs for select to authenticated
    using (
        exists (
            select 1
            from public.trades trade
            join public.dashboard_account_access access
              on access.account_id = trade.account_id
            where trade.id = ai_trade_logs.trade_id
              and access.user_id = (select auth.uid())
        )
    );

drop policy if exists "Users can read assigned account snapshots"
    on public.account_equity_snapshots;
create policy "Users can read assigned account snapshots"
    on public.account_equity_snapshots for select to authenticated
    using (
        exists (
            select 1 from public.dashboard_account_access access
            where access.account_id = account_equity_snapshots.account_id
              and access.user_id = (select auth.uid())
        )
    );

grant select on public.dashboard_account_access to authenticated;
grant select on public.trading_accounts to authenticated;
grant select on public.trades to authenticated;
grant select on public.ai_trade_logs to authenticated;
grant select on public.account_equity_snapshots to authenticated;
grant insert, select on public.account_equity_snapshots to service_role;

create or replace view public.dashboard_trade_metrics
with (security_invoker = true)
as
select
    account_id,
    count(*)::bigint as total_trades,
    count(*) filter (where status = 'closed')::bigint as closed_trades,
    count(*) filter (where status = 'open')::bigint as open_trades,
    count(*) filter (where status = 'closed' and profit_loss > 0)::bigint as winning_trades,
    coalesce(sum(profit_loss) filter (where status = 'closed'), 0) as realized_pnl,
    coalesce(sum(profit_loss) filter (where status = 'closed' and profit_loss > 0), 0)
        as gross_profit,
    coalesce(abs(sum(profit_loss) filter (where status = 'closed' and profit_loss < 0)), 0)
        as gross_loss
from public.trades
group by account_id;

grant select on public.dashboard_trade_metrics to authenticated;
