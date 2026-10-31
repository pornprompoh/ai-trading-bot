# Northstar Trading Dashboard

Private React + Vite dashboard for the MT5 trading engine. It reads account,
trade, snapshot, and AI-log data from Supabase using a publishable/anon key and
requires a Supabase Auth session. The backend `SUPABASE_KEY` must never be
copied into this frontend.

## Run locally

```powershell
Copy-Item .env.example .env
npm install
npm run dev
```

Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in `dashboard/.env`, then
restart Vite. Add a user under **Supabase → Authentication → Users** and sign
in with that user's email and password.

## Supabase setup

1. For an existing installation, run
   `database/dashboard_controls_migration.sql` in the Supabase SQL Editor
   before deploying the updated bot or dashboard. For a new installation,
   `database/schema.sql` contains the complete schema. The migration adds
   scanner state, risk metrics, an account-level auto-trading gate, and an
   authenticated emergency-command queue with RLS.
2. Grant the Auth user access to the intended trading account. Find the
   account's BIGINT `account_id` in `trading_accounts` and the user's UUID in
   Supabase Auth, then run:

   ```sql
   insert into public.dashboard_account_access (user_id, account_id)
   select 'AUTH_USER_UUID', 123
   where not exists (
       select 1
       from public.dashboard_account_access
       where user_id = 'AUTH_USER_UUID'
         and account_id = 123
   );
   ```

3. Keep the existing backend `.env` key server-side (service-role key). The
   frontend uses only the Supabase publishable/anon key; never enable public
   read policies for trading data.
4. Restart the Python bot after applying the schema. The scanner updates each
   watched symbol every engine cycle; account margin/equity snapshots are saved
   every five minutes. Auto-trading requires both the account switch and
   `AUTO_TRADING_ENABLED=true` in the server-side `.env`; it remains Demo-only.
   Emergency close commands are queued for the engine and are accepted only
   when its connected MT5 account is Demo. The browser never sends MT5 orders.

The UI refreshes every 30 seconds. Metrics are aggregated by the
`dashboard_trade_metrics` security-invoker view, while the trades and decision
feed show the latest 100 trades and 30 AI logs.
