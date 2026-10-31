import { Activity, Clock3, TrendingDown, TrendingUp } from 'lucide-react'

const WATCHLIST = [
  { symbol: 'XAUUSD.iux', timeframe: 'M15' },
  { symbol: 'EURUSD.iux', timeframe: 'H1' },
  { symbol: 'USDJPY.iux', timeframe: 'H1' },
]

const STATUS_STYLES = {
  scanning: 'border-[#34464c] bg-[#182329] text-[#a9c5cb]',
  no_signal: 'border-[#3b4243] bg-[#202627] text-[#aeb9b8]',
  condition_met: 'border-[#59492f] bg-[#2b2519] text-[#ebca7a]',
  position_open: 'border-[#3d5732] bg-[#1d3024] text-[#b7ed83]',
  unavailable: 'border-[#604040] bg-[#302020] text-[#ffaaa0]',
  rejected: 'border-[#604040] bg-[#302020] text-[#ffaaa0]',
}

function price(value) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 5 })
}

function updatedAt(value) {
  if (!value) return 'Waiting for first scan'
  return new Date(value).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function signalLabel(value) {
  return (value ?? 'scanning').replaceAll('_', ' ').toUpperCase()
}

export default function LiveMarketScanner({ scans, now }) {
  const rows = WATCHLIST.map((item) => ({
    ...item,
    ...scans.find((scan) => scan.symbol === item.symbol),
  }))
  const nowMs = now?.getTime() ?? 0
  const allScansFresh = rows.every(
    (scan) => scan.updated_at && now && nowMs - new Date(scan.updated_at).getTime() < 150_000,
  )
  const hasScans = rows.every((scan) => scan.updated_at)

  return (
    <section className="overflow-hidden rounded-2xl border border-[#202c32] bg-[#10171b]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#202c32] px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-[#29433f] bg-[#142522] text-[#73d9c0]">
            <Activity size={17} />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-[#e8efec]">Live market scanner</h2>
            <p className="mt-1 text-[10px] text-[#718186]">Latest completed-candle analysis from the engine</p>
          </div>
        </div>
        <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[9px] font-semibold tracking-wide ${allScansFresh ? 'border-[#2d3b39] bg-[#14201b] text-[#b6f36b]' : 'border-[#59492f] bg-[#2b2519] text-[#ebca7a]'}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${allScansFresh ? 'animate-pulse bg-[#b6f36b]' : 'bg-[#d6a957]'}`} />
          {allScansFresh ? `SCANNER LIVE · ${rows.length} MARKETS` : hasScans ? 'SCANNER DATA STALE' : 'WAITING FOR ENGINE'}
        </span>
      </header>

      <div className="grid grid-cols-1 divide-y divide-[#202c32] md:grid-cols-3 md:divide-x md:divide-y-0">
        {rows.map((scan) => {
          const fresh = scan.updated_at && now && nowMs - new Date(scan.updated_at).getTime() < 150_000
          const status = fresh ? scan.signal_status : scan.updated_at ? 'unavailable' : 'scanning'
          const tone = STATUS_STYLES[status] ?? STATUS_STYLES.scanning
          const trendIcon = scan.ema_trend === 'bullish'
            ? <TrendingUp className="text-[#b6f36b]" size={15} />
            : scan.ema_trend === 'bearish'
              ? <TrendingDown className="text-[#ff988a]" size={15} />
              : null
          return (
            <article className="min-w-0 p-5" key={scan.symbol}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="mono text-xs font-semibold text-[#e1eae6]">{scan.symbol}</h3>
                  <p className="mt-1 text-[10px] text-[#718186]">Timeframe {scan.timeframe}</p>
                </div>
                <span className={`max-w-[145px] rounded-full border px-2 py-1 text-center text-[8px] font-bold tracking-wide ${tone}`}>
                  {signalLabel(status)}
                </span>
              </div>
              <div className="mt-5 grid grid-cols-3 gap-2">
                <Metric label="LAST PRICE" value={price(scan.last_price)} />
                <Metric label="RSI (14)" value={scan.rsi == null ? '—' : Number(scan.rsi).toFixed(1)} />
                <Metric label="EMA TREND" value={scan.ema_trend ?? '—'} icon={trendIcon} />
              </div>
              <p className="mt-4 min-h-10 rounded-lg border border-[#253137] bg-[#0c1216] px-3 py-2 text-[10px] leading-5 text-[#a6b3b0]">
                {fresh
                  ? scan.reason
                  : scan.updated_at
                    ? 'Last engine scan is stale; waiting for a fresh update'
                    : 'Waiting for the first engine scan'}
              </p>
              <p className="mt-3 flex items-center gap-1.5 text-[9px] text-[#66777b]">
                <Clock3 size={11} /> {updatedAt(scan.updated_at)}
              </p>
            </article>
          )
        })}
      </div>
    </section>
  )
}

function Metric({ label, value, icon }) {
  return (
    <div className="min-w-0">
      <p className="text-[8px] font-semibold tracking-[0.12em] text-[#637378]">{label}</p>
      <p className="mt-1 flex items-center gap-1 truncate text-[10px] font-medium capitalize text-[#c5d0cd]">
        {icon}{value}
      </p>
    </div>
  )
}
