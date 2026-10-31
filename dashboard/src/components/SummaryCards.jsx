import { Activity, BadgeDollarSign, Layers3, Target } from 'lucide-react'
import { money } from '../lib/format'
import MetricCard from './MetricCard'

export default function SummaryCards({ account, metrics, equity }) {
  const trades = Number(metrics.total_trades) || 0
  const closed = Number(metrics.closed_trades) || 0
  const winners = Number(metrics.winning_trades) || 0
  const winRate = closed ? (winners / closed) * 100 : null
  const grossProfit = Number(metrics.gross_profit) || 0
  const grossLoss = Number(metrics.gross_loss) || 0
  const profitFactor =
    grossLoss > 0 ? (grossProfit / grossLoss).toFixed(2) : grossProfit > 0 ? '∞' : '—'

  return (
    <section aria-label="Key performance metrics" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard
        accent="lime"
        detail={`Equity ${equity == null ? 'not yet reported' : money(equity)}`}
        icon={BadgeDollarSign}
        label="CURRENT BALANCE"
        value={money(account.balance)}
      />
      <MetricCard
        accent="blue"
        detail={`${Number(metrics.open_trades) || 0} currently open`}
        icon={Layers3}
        label="TOTAL TRADES"
        value={trades.toLocaleString('en-US')}
      />
      <MetricCard
        accent="teal"
        detail={closed ? `${winners} wins · ${closed - winners} losses` : 'No closed trades yet'}
        icon={Target}
        label="WIN RATE"
        value={winRate == null ? '—' : `${winRate.toFixed(1)}%`}
      />
      <MetricCard
        accent="amber"
        detail={`Realized ${money(metrics.realized_pnl)}`}
        icon={Activity}
        label="PROFIT FACTOR"
        value={profitFactor}
      />
    </section>
  )
}
