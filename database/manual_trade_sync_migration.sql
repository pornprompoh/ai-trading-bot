-- Apply once to existing installations before deploying manual MT5 trade sync.
alter table public.trades
    add column if not exists execution_source text not null default 'BOT_SMC';

alter table public.trades
    alter column sl_price drop not null,
    alter column tp_price drop not null;

grant select, insert, update on public.trades to service_role;
