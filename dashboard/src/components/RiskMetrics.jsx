import { Activity, Gauge, ShieldAlert, Wallet } from 'lucide-react'
import MetricCard from './MetricCard'
import { money } from '../lib/format'

export default function RiskMetrics({ riskMetrics, exposure }) {
  const marginLevel = riskMetrics?.margin_level == null
    ? Number.NaN
    : Number(riskMetrics.margin_level)
  const drawdown = riskMetrics?.daily_drawdown_percent == null
    ? Number.NaN
    : Number(riskMetrics.daily_drawdown_percent)
  const dailyTrades = Number(riskMetrics?.daily_trade_count) || 0

  return (
    <section className="rounded-2xl border border-[#202c32] bg-[#10171b] p-5">
      <div className="mb-4 flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-[#463d2b] bg-[#242117] text-[#e2bd72]">
          <ShieldAlert size={17} />
        </span>
        <div>
          <h2 className="text-sm font-semibold text-[#e8efec]">Risk &amp; exposure</h2>
          <p className="mt-1 text-[10px] text-[#718186]">Live margin and account-level trade exposure</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          accent="blue"
          detail="Available funds"
          icon={Wallet}
          label="FREE MARGIN"
          value={riskMetrics?.free_margin == null ? '—' : money(riskMetrics.free_margin)}
        />
        <MetricCard
          accent="teal"
          detail="Equity ÷ used margin"
          icon={Gauge}
          label="MARGIN LEVEL"
          value={Number.isFinite(marginLevel) ? `${marginLevel.toFixed(1)}%` : '—'}
        />
        <MetricCard
          accent="amber"
          detail={`Max equity peak ${riskMetrics?.max_equity_peak == null ? '—' : money(riskMetrics.max_equity_peak)}`}
          icon={Activity}
          label="DAILY DRAWDOWN"
          value={Number.isFinite(drawdown) ? `${drawdown.toFixed(2)}%` : '—'}
        />
        <MetricCard
          accent="lime"
          detail="Trades opened today (UTC)"
          icon={Activity}
          label="DAILY TRADE COUNT"
          value={dailyTrades.toLocaleString('en-US')}
        />
      </div>

      <div className="mt-4 rounded-xl border border-[#263238] bg-[#0c1216] p-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-[10px] font-semibold tracking-wide text-[#aab8b5]">OPEN EXPOSURE BY SYMBOL</h3>
          <span className="text-[9px] text-[#66777b]">Open volume · lots</span>
        </div>
        {exposure.length ? (
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
            {exposure.map((item) => (
              <div className="flex items-center justify-between gap-3 rounded-lg bg-[#151e22] px-3 py-2" key={item.symbol}>
                <div>
                  <p className="mono text-[10px] font-medium text-[#c7d2ce]">{item.symbol}</p>
                  <p className="mt-0.5 text-[9px] text-[#718186]">{item.open_positions} position(s)</p>
                </div>
                <span className="mono text-xs text-[#b6f36b]">{Number(item.total_volume).toFixed(2)}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-3 text-[10px] text-[#718186]">No open symbol exposure.</p>
        )}
      </div>
    </section>
  )
}
