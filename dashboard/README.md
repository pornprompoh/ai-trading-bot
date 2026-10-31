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

1. Run the repository's `database/schema.sql` in the Supabase SQL Editor. It
   creates the equity-snapshot and account-access tables, a metrics view, and
   RLS policies scoped to each authenticated user's assigned accounts.
2. Grant the Auth user access to the intended trading account. Find its UUID
   and the user's UUID in Supabase, then run:

   ```sql
   insert into public.dashboard_account_access (user_id, account_id)
   values ('AUTH_USER_UUID', 'TRADING_ACCOUNT_UUID')
   on conflict do nothing;
   ```

3. Keep the existing backend `.env` key server-side (service-role key). The
   frontend uses only the Supabase publishable/anon key; never enable public
   read policies for trading data.
4. Restart the Python bot after applying the schema. It records balance/equity
   snapshots every five minutes; the chart and bot heartbeat become available
   after snapshots start arriving.

The UI refreshes every 30 seconds. Metrics are aggregated by the
`dashboard_trade_metrics` security-invoker view, while the trades and decision
feed show the latest 100 trades and 30 AI logs.
