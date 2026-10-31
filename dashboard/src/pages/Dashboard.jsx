import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  Bot,
  ChevronDown,
  CircleHelp,
  Clock3,
  Command,
  LogOut,
  PanelTop,
  RefreshCw,
  Shield,
  SlidersHorizontal,
  Sparkles,
  Wallet,
} from 'lucide-react'
import { fetchAccountDashboard, fetchAccounts } from '../lib/dashboardData'
import { money } from '../lib/format'
import { supabase } from '../lib/supabase'
import AiLogFeed from '../components/AiLogFeed'
import SummaryCards from '../components/SummaryCards'
import TradesTable from '../components/TradesTable'

const REFRESH_INTERVAL_MS = 30_000
const BOT_ACTIVE_WITHIN_MS = 11 * 60 * 1000
const EquityChart = lazy(() => import('../components/EquityChart'))

function shortTime(value) {
  if (!value) return 'Waiting for first heartbeat'
  return new Date(value).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

function Navigation({ openTrades }) {
  const links = [
    { href: '#overview', label: 'Overview', icon: PanelTop, selected: true },
    { href: '#trade-activity', label: 'Trade activity', icon: Activity, count: openTrades },
    { href: '#ai-insights', label: 'AI insights', icon: Sparkles },
  ]

  return (
    <nav aria-label="Main navigation" className="space-y-1">
      <p className="px-3 pb-2 pt-5 text-[9px] font-bold tracking-[0.18em] text-[#657479]">WORKSPACE</p>
      {links.map(({ href, label, icon: Icon, selected, count }) => (
        <a
          className={`group flex items-center gap-3 rounded-xl px-3 py-2.5 text-xs transition ${
            selected
              ? 'border border-[#344338] bg-[#19251d] font-semibold text-[#c8f19a]'
              : 'text-[#89979a] hover:bg-[#141d21] hover:text-[#e3ece8]'
          }`}
          href={href}
          key={href}
        >
          <Icon className={selected ? 'text-[#b6f36b]' : 'text-[#718186] group-hover:text-[#b6f36b]'} size={16} />
          <span>{label}</span>
          {count > 0 && (
            <span className="mono ml-auto rounded-md bg-[#202b2e] px-1.5 py-0.5 text-[9px] text-[#9caaaa]">
              {count}
            </span>
          )}
        </a>
      ))}
    </nav>
  )
}

function Brand() {
  return (
    <div className="flex items-center gap-3 px-2">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-[#34473d] bg-[#18251d] text-[#b6f36b]">
        <Activity size={18} strokeWidth={2.2} />
      </span>
      <span>
        <span className="block text-[13px] font-bold tracking-[0.09em] text-[#ecf3ef]">NORTHSTAR</span>
        <span className="mt-0.5 block text-[8px] font-semibold tracking-[0.2em] text-[#738388]">AI TRADING ENGINE</span>
      </span>
    </div>
  )
}

function AccountOverview({ account, equity, pnl, pnlPercent, lastHeartbeat, active }) {
  return (
    <section className="relative overflow-hidden rounded-2xl border border-[#304238] bg-[linear-gradient(115deg,#18251e_0%,#14201d_48%,#121a1d_100%)] p-5 sm:p-6">
      <div className="pointer-events-none absolute -right-14 -top-20 h-56 w-56 rounded-full border border-[#d1f6a0]/[0.07]" />
      <div className="pointer-events-none absolute -right-2 -top-8 h-36 w-36 rounded-full border border-[#d1f6a0]/[0.06]" />
      <div className="relative flex flex-col gap-6 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[9px] font-bold tracking-wide ${active ? 'border-[#4b673c] bg-[#26391f] text-[#c4f18f]' : 'border-[#554b37] bg-[#302a1d] text-[#e2bd72]'}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${active ? 'animate-pulse bg-[#b6f36b]' : 'bg-[#d6a957]'}`} />
              BOT {active ? 'ACTIVE' : 'INACTIVE'}
            </span>
            <span className="inline-flex items-center gap-1.5 text-[10px] text-[#93a39d]">
              <span className="h-1 w-1 rounded-full bg-[#668078]" />
              Last heartbeat {shortTime(lastHeartbeat)}
            </span>
          </div>
          <h1 className="mt-4 text-[22px] font-semibold tracking-[-0.04em] text-[#eef4ef] sm:text-[26px]">
            Account performance
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[#9aaba4]">
            <span className="mono">#{account.login}</span>
            <span className="h-1 w-1 rounded-full bg-[#53645d]" />
            <span>{account.server}</span>
            <span className="h-1 w-1 rounded-full bg-[#53645d]" />
            <span className="mono text-[#71847c]">{account.id.slice(0, 8)}…</span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-3 sm:gap-x-10 xl:pr-3">
          <HeroValue label="BALANCE" value={money(account.balance)} />
          <HeroValue label="EQUITY" value={equity == null ? '—' : money(equity)} />
          <HeroValue
            label="TOTAL P&L"
            tone={pnl >= 0 ? 'positive' : 'negative'}
            value={`${pnl >= 0 ? '+' : ''}${money(pnl)}`}
            subvalue={`${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%`}
          />
        </div>
      </div>
    </section>
  )
}

function HeroValue({ label, value, tone = 'default', subvalue }) {
  const color =
    tone === 'positive' ? 'text-[#c0ef8a]' : tone === 'negative' ? 'text-[#ff9784]' : 'text-[#e7efeb]'
  return (
    <div>
      <p className="text-[9px] font-bold tracking-[0.16em] text-[#81948a]">{label}</p>
      <p className={`mono mt-1.5 text-lg font-medium tracking-[-0.04em] ${color}`}>{value}</p>
      {subvalue && <p className={`mono mt-0.5 text-[10px] ${color}`}>{subvalue}</p>}
    </div>
  )
}

function LoadingPanel({ message = 'Loading account data…' }) {
  return (
    <div className="flex min-h-[280px] items-center justify-center rounded-2xl border border-[#202c32] bg-[#10171b] text-xs text-[#8c9a9d]">
      <span className="mr-3 h-4 w-4 animate-spin rounded-full border-2 border-[#34413f] border-t-[#b6f36b]" />
      {message}
    </div>
  )
}

export default function Dashboard({ session }) {
  const [accounts, setAccounts] = useState([])
  const [accountId, setAccountId] = useState('')
  const [dashboard, setDashboard] = useState(null)
  const [loadingAccounts, setLoadingAccounts] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [lastUpdated, setLastUpdated] = useState(null)
  const [now, setNow] = useState(null)

  useEffect(() => {
    const updateClock = () => setNow(new Date())
    updateClock()
    const timer = window.setInterval(updateClock, 30_000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    let active = true
    fetchAccounts()
      .then((rows) => {
        if (!active) return
        setAccounts(rows)
        setAccountId((current) => current && rows.some((row) => row.id === current) ? current : rows[0]?.id ?? '')
      })
      .catch((fetchError) => {
        if (active) setError(fetchError.message)
      })
      .finally(() => {
        if (active) setLoadingAccounts(false)
      })
    return () => {
      active = false
    }
  }, [])

  const refresh = useCallback(async () => {
    if (!accountId) return
    setRefreshing(true)
    try {
      const result = await fetchAccountDashboard(accountId)
      setDashboard(result)
      setError('')
      setLastUpdated(new Date())
    } catch (fetchError) {
      setError(fetchError.message)
    } finally {
      setRefreshing(false)
    }
  }, [accountId])

  useEffect(() => {
    if (!accountId) return undefined
    let active = true
    const load = async () => {
      setRefreshing(true)
      try {
        const result = await fetchAccountDashboard(accountId)
        if (!active) return
        setDashboard(result)
        setError('')
        setLastUpdated(new Date())
      } catch (fetchError) {
        if (active) setError(fetchError.message)
      } finally {
        if (active) setRefreshing(false)
      }
    }
    load()
    const timer = window.setInterval(load, REFRESH_INTERVAL_MS)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [accountId])

  const account = accounts.find((row) => row.id === accountId)
  const metrics = dashboard?.metrics
  const latestSnapshot = dashboard?.snapshots.at(-1)
  const equity = latestSnapshot ? Number(latestSnapshot.equity) : null
  const realizedPnl = Number(metrics?.realized_pnl) || 0
  const floatingPnl = equity == null || !account ? 0 : equity - Number(account.balance)
  const totalPnl = realizedPnl + floatingPnl
  const startingBalance = account ? Number(account.balance) - realizedPnl : 0
  const totalPnlPercent = startingBalance > 0 ? (totalPnl / startingBalance) * 100 : 0
  const botActive =
    latestSnapshot &&
    now &&
    now.getTime() - new Date(latestSnapshot.captured_at).getTime() < BOT_ACTIVE_WITHIN_MS
  const openTrades = Number(metrics?.open_trades) || 0

  const serverLabel = useMemo(() => account?.server ?? 'No trading account', [account])

  if (loadingAccounts) return <LoadingPanel message="Loading your private workspace…" />

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-[224px] flex-col border-r border-[#1e292f] bg-[#0c1115] px-4 py-5 lg:flex">
        <Brand />
        <Navigation openTrades={openTrades} />
        <div className="mt-auto">
          <div className="rounded-xl border border-[#27343a] bg-[#11191d] p-3">
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#1d3024] text-[#b6f36b]">
                <Shield size={14} />
              </span>
              <div>
                <p className="text-[10px] font-semibold text-[#d8e2de]">Private workspace</p>
                <p className="mt-0.5 text-[9px] text-[#738388]">Authenticated access</p>
              </div>
            </div>
          </div>
          <button
            className="mt-4 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[10px] text-[#859396] transition hover:bg-[#172024] hover:text-white"
            onClick={() => supabase.auth.signOut()}
            type="button"
          >
            <LogOut size={14} /> Sign out
            <span className="ml-auto max-w-[105px] truncate text-[9px] text-[#657479]">
              {session.user.email}
            </span>
          </button>
        </div>
      </aside>

      <main className="min-w-0 lg:pl-[224px]">
        <header className="sticky top-0 z-10 border-b border-[#1e292f] bg-[#0b1014]/90 backdrop-blur-xl">
          <div className="mx-auto flex h-[62px] max-w-[1500px] items-center justify-between gap-3 px-4 sm:px-7 xl:px-9">
            <div className="flex min-w-0 items-center gap-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[#34473d] bg-[#18251d] text-[#b6f36b] lg:hidden">
                <Activity size={16} />
              </span>
              <div className="min-w-0">
                <p className="truncate text-[11px] font-semibold text-[#d5dfdc]">Trading overview</p>
                <p className="hidden text-[9px] text-[#69797e] sm:block">Monitor account and AI execution context</p>
              </div>
              <span className="hidden h-4 w-px bg-[#29343a] sm:block" />
              <div className="hidden items-center gap-1.5 text-[10px] text-[#8e9b9d] md:flex">
                <span className={`h-1.5 w-1.5 rounded-full ${botActive ? 'bg-[#b6f36b]' : 'bg-[#d2aa5d]'}`} />
                {botActive ? 'Engine connected' : 'Engine offline'}
              </div>
            </div>

            <div className="flex items-center gap-2 sm:gap-3">
              {accounts.length > 1 && (
                <label className="relative">
                  <span className="sr-only">Select trading account</span>
                  <select
                    className="h-9 max-w-[150px] appearance-none rounded-lg border border-[#29363b] bg-[#11191d] pl-3 pr-8 text-[10px] text-[#c1ceca] outline-none focus:border-[#536a54] sm:max-w-none sm:text-xs"
                    onChange={(event) => {
                      setDashboard(null)
                      setAccountId(event.target.value)
                    }}
                    value={accountId}
                  >
                    {accounts.map((item) => (
                      <option key={item.id} value={item.id}>
                        #{item.login} · {item.server}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[#78878a]" size={13} />
                </label>
              )}
              <div className="hidden text-right sm:block">
                <p className="text-[9px] text-[#6f7f83]">Last synced</p>
                <p className="mono mt-0.5 text-[10px] text-[#a2b0ad]">
                  {lastUpdated ? shortTime(lastUpdated) : '—'}
                </p>
              </div>
              <button
                aria-label="Refresh dashboard data"
                className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#29363b] bg-[#11191d] text-[#9aabaa] transition hover:border-[#536a54] hover:text-[#b6f36b] disabled:opacity-50"
                disabled={refreshing}
                onClick={refresh}
                type="button"
              >
                <RefreshCw className={refreshing ? 'animate-spin' : ''} size={15} />
              </button>
              <button
                aria-label="Sign out"
                className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#29363b] bg-[#11191d] text-[#9aabaa] transition hover:border-[#713c3c] hover:text-[#ff988a] lg:hidden"
                onClick={() => supabase.auth.signOut()}
                type="button"
              >
                <LogOut size={15} />
              </button>
            </div>
          </div>
        </header>

        <div className="mx-auto max-w-[1500px] px-4 pb-10 pt-6 sm:px-7 sm:pt-8 xl:px-9">
          <div className="mb-5 flex items-end justify-between gap-4">
            <div>
              <p className="text-[9px] font-bold tracking-[0.2em] text-[#789078]">LIVE ACCOUNT MONITOR</p>
              <h1 className="mt-2 text-[25px] font-semibold tracking-[-0.05em] text-[#f0f5f2] sm:text-[30px]">
                Good evening<span className="text-[#b6f36b]">.</span>
              </h1>
            </div>
            <div className="hidden items-center gap-2 pb-1 text-[10px] text-[#768589] sm:flex">
              <Clock3 size={13} />
              {now
                ? now.toLocaleDateString('en-US', {
                    weekday: 'short',
                    month: 'short',
                    day: 'numeric',
                  })
                : '—'}
              <span className="mx-1 h-3 w-px bg-[#2b363b]" />
              <span className="mono">
                {now
                  ? `UTC${now.getTimezoneOffset() <= 0 ? '+' : '-'}${String(Math.abs(now.getTimezoneOffset()) / 60).padStart(2, '0')}:00`
                  : 'UTC'}
              </span>
            </div>
          </div>

          {error && (
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#694343] bg-[#2d1d1d] px-4 py-3 text-xs text-[#ffc3b5]">
              <span>{error}</span>
              <button className="font-semibold underline underline-offset-2" onClick={refresh} type="button">
                Retry
              </button>
            </div>
          )}

          {!account ? (
            <div className="rounded-2xl border border-[#344338] bg-[#141d18] p-6 text-sm text-[#d3dfd8]">
              <div className="flex items-center gap-2 font-semibold">
                <CircleHelp className="text-[#b6f36b]" size={18} />
                No trading account is assigned to this user.
              </div>
              <p className="mt-2 max-w-2xl text-xs leading-6 text-[#91a19a]">
                Add your Supabase Auth user and account UUID to <code>dashboard_account_access</code> in the Supabase SQL Editor.
              </p>
            </div>
          ) : !dashboard ? (
            <LoadingPanel message="Fetching protected trading data…" />
          ) : (
            <>
              <div id="overview">
                <AccountOverview
                  account={account}
                  active={Boolean(botActive)}
                  equity={equity}
                  lastHeartbeat={latestSnapshot?.captured_at}
                  pnl={totalPnl}
                  pnlPercent={totalPnlPercent}
                />
              </div>

              <div className="mt-4">
                <SummaryCards account={account} equity={equity} metrics={metrics} />
              </div>

              <div className="mt-4 grid grid-cols-1 gap-4 2xl:grid-cols-[minmax(0,1.65fr)_minmax(330px,0.85fr)]">
                <Suspense fallback={<LoadingPanel message="Loading account chart…" />}>
                  <EquityChart snapshots={dashboard.snapshots} />
                </Suspense>
                <div className="rounded-2xl border border-[#202c32] bg-[#10171b] p-5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-[#334338] bg-[#19251d] text-[#b6f36b]">
                        <Wallet size={16} />
                      </span>
                      <div>
                        <h2 className="text-sm font-semibold text-[#e8efec]">Account details</h2>
                        <p className="mt-0.5 text-[10px] text-[#718186]">Live MT5 snapshot</p>
                      </div>
                    </div>
                    <span className="rounded-full border border-[#2a373d] bg-[#172126] px-2 py-1 text-[9px] font-semibold text-[#a6b3b0]">
                      {account.server.includes('Demo') ? 'DEMO' : 'CONNECTED'}
                    </span>
                  </div>
                  <div className="mt-5 space-y-3">
                    <DetailRow label="Account login" value={`#${account.login}`} />
                    <DetailRow label="Server" value={serverLabel} />
                    <DetailRow label="Free margin" value={latestSnapshot ? money(latestSnapshot.free_margin) : '—'} />
                    <DetailRow label="Used margin" value={latestSnapshot ? money(latestSnapshot.margin) : '—'} />
                    <DetailRow label="Floating P&L" value={equity == null ? '—' : `${floatingPnl >= 0 ? '+' : ''}${money(floatingPnl)}`} tone={floatingPnl >= 0 ? 'positive' : 'negative'} />
                    <DetailRow label="Last heartbeat" value={shortTime(latestSnapshot?.captured_at)} />
                  </div>
                  <div className="mt-5 flex items-start gap-2 rounded-xl border border-[#28373a] bg-[#121b1d] p-3 text-[10px] leading-5 text-[#8d9b9d]">
                    <Bot className="mt-0.5 shrink-0 text-[#9acb6a]" size={14} />
                    <p>Account history is sampled by the trading engine every five minutes and refreshed here every 30 seconds.</p>
                  </div>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-1 gap-4 2xl:grid-cols-[minmax(0,1.65fr)_minmax(330px,0.85fr)]">
                <div id="trade-activity">
                  <TradesTable trades={dashboard.trades} />
                </div>
                <div id="ai-insights">
                  <AiLogFeed logs={dashboard.aiLogs} />
                </div>
              </div>
            </>
          )}

          <footer className="mt-8 flex flex-wrap items-center justify-between gap-2 border-t border-[#1c272c] pt-4 text-[9px] text-[#68777b]">
            <span className="flex items-center gap-1.5"><Command size={11} /> NORTHSTAR · PRIVATE TRADING WORKSPACE</span>
            <span className="flex items-center gap-1.5"><SlidersHorizontal size={11} /> Read-only dashboard · Auto-refresh 30s</span>
          </footer>
        </div>
      </main>
    </div>
  )
}

function DetailRow({ label, value, tone }) {
  const valueTone = tone === 'positive' ? 'text-[#b6f36b]' : tone === 'negative' ? 'text-[#ff8879]' : 'text-[#c8d2cf]'
  return (
    <div className="flex items-center justify-between gap-3 text-[11px]">
      <span className="text-[#7e8d90]">{label}</span>
      <span className={`mono truncate text-right ${valueTone}`}>{value}</span>
    </div>
  )
}
