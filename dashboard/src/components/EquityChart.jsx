import { useMemo } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { BarChart3, CircleHelp } from 'lucide-react'

function formatCurrency(value) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value)
}

function formatTime(value) {
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <p className="mb-2 text-[10px] tracking-wide text-[#829195]">{formatTime(label)}</p>
      {payload.map((item) => (
        <p className="mono flex items-center justify-between gap-6 py-0.5 text-xs" key={item.dataKey}>
          <span style={{ color: item.color }}>{item.name}</span>
          <span className="text-[#e7efec]">{formatCurrency(item.value)}</span>
        </p>
      ))}
    </div>
  )
}

export default function EquityChart({ snapshots }) {
  const data = useMemo(
    () =>
      snapshots.map((snapshot) => ({
        ...snapshot,
        timestamp: new Date(snapshot.recorded_at).getTime(),
        balance: Number(snapshot.balance),
        equity: Number(snapshot.equity),
      })),
    [snapshots],
  )
  const latest = data.at(-1)
  const first = data[0]
  const balanceChange = first && latest ? latest.balance - first.balance : null

  return (
    <section className="overflow-hidden rounded-2xl border border-[#202c32] bg-[#10171b]">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#202c32] px-5 py-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-[#29433f] bg-[#142522] text-[#73d9c0]">
              <BarChart3 size={16} />
            </span>
            <h2 className="text-sm font-semibold text-[#e8efec]">Balance & equity</h2>
          </div>
          <p className="mt-2 pl-10 text-[11px] text-[#718186]">Account snapshots · five-minute intervals</p>
        </div>
        <div className="flex items-center gap-4 pl-10 sm:pl-0">
          <Legend color="#b6f36b" label="Balance" />
          <Legend color="#64c8bb" label="Equity" />
          {balanceChange != null && (
            <span className={`mono text-xs ${balanceChange >= 0 ? 'text-[#b6f36b]' : 'text-[#ff8879]'}`}>
              {balanceChange >= 0 ? '+' : ''}{formatCurrency(balanceChange)}
            </span>
          )}
        </div>
      </div>
      {data.length < 2 ? (
        <div className="flex h-[360px] flex-col items-center justify-center px-6 text-center">
          <CircleHelp className="text-[#516167]" size={24} />
          <p className="mt-3 text-sm font-medium text-[#cbd5d4]">Building account history</p>
          <p className="mt-1 max-w-sm text-xs leading-5 text-[#78888d]">
            Equity snapshots are collected every five minutes after the database migration is applied.
          </p>
        </div>
      ) : (
        <div className="h-[360px] w-full px-2 pb-3 pt-5 sm:px-4">
          <ResponsiveContainer height="100%" width="100%">
            <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="balanceFill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#b6f36b" stopOpacity={0.14} />
                  <stop offset="95%" stopColor="#b6f36b" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="equityFill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#64c8bb" stopOpacity={0.09} />
                  <stop offset="95%" stopColor="#64c8bb" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#253138" strokeDasharray="3 5" vertical={false} />
              <XAxis
                axisLine={false}
                dataKey="timestamp"
                minTickGap={44}
                tick={{ fill: '#718186', fontSize: 10 }}
                tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                tickLine={false}
              />
              <YAxis
                axisLine={false}
                domain={['auto', 'auto']}
                tick={{ fill: '#718186', fontSize: 10 }}
                tickFormatter={formatCurrency}
                tickLine={false}
                width={64}
              />
              <Tooltip content={<ChartTooltip />} />
              <Area
                dataKey="balance"
                fill="url(#balanceFill)"
                name="Balance"
                stroke="#b6f36b"
                strokeWidth={2}
                type="monotone"
              />
              <Area
                dataKey="equity"
                fill="url(#equityFill)"
                name="Equity"
                stroke="#64c8bb"
                strokeWidth={1.7}
                type="monotone"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}

function Legend({ color, label }) {
  return (
    <span className="flex items-center gap-1.5 text-[10px] text-[#9ba9aa]">
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}
