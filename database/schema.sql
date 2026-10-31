create table if not exists public.trading_accounts (
    id uuid primary key default gen_random_uuid(),
    login bigint not null,
    server text not null,
    balance numeric(18, 2) not null default 0,
    updated_at timestamptz not null default now(),
    unique (login, server)
);

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
    opened_at timestamptz not null,
    timeframe text,
    status text not null default 'open' check (status in ('open', 'closed')),
    close_price numeric(18, 8),
    profit_loss numeric(18, 2),
    exit_reason text,
    closed_at timestamptz
);

create table if not exists public.ai_trade_logs (
    id uuid primary key default gen_random_uuid(),
    trade_id uuid not null unique references public.trades(id) on delete cascade,
    indicators jsonb not null default '{}'::jsonb,
    timeframe text,
    reasoning text not null,
    created_at timestamptz not null default now()
);

alter table public.trading_accounts enable row level security;
alter table public.trades enable row level security;
alter table public.ai_trade_logs enable row level security;
