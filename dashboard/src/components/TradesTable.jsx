import { useMemo, useState } from 'react'
import { ArrowDownLeft, ArrowUpRight, ChevronDown, ChevronUp, Search } from 'lucide-react'

function price(value) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 5 })
}

function time(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function TradesTable({ trades }) {
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [sortAscending, setSortAscending] = useState(false)

  const rows = useMemo(() => {
    const query = search.trim().toLowerCase()
    return trades
      .filter((trade) => filter === 'all' || trade.status === filter)
      .filter((trade) => !query || `${trade.ticket} ${trade.symbol}`.toLowerCase().includes(query))
      .sort((a, b) => {
        const difference = new Date(a.opened_at).getTime() - new Date(b.opened_at).getTime()
        return sortAscending ? difference : -difference
      })
  }, [filter, search, sortAscending, trades])

  return (
    <section className="overflow-hidden rounded-2xl border border-[#202c32] bg-[#10171b]">
      <div className="flex flex-col gap-3 border-b border-[#202c32] px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-[#e8efec]">Trade activity</h2>
            <span className="rounded-full border border-[#2a373d] bg-[#172126] px-2 py-0.5 text-[10px] text-[#8fa0a3]">
              {rows.length} shown
            </span>
          </div>
          <p className="mt-1 text-[11px] text-[#718186]">Latest executions and closed positions</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative min-w-[145px] flex-1 sm:flex-none">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#718186]" size={14} />
            <input
              aria-label="Search trades"
              className="h-9 w-full rounded-lg border border-[#27343a] bg-[#0b1115] pl-9 pr-3 text-xs text-[#e4ece9] outline-none placeholder:text-[#59686d] focus:border-[#536a54] sm:w-40"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Ticket or symbol"
              value={search}
            />
          </label>
          <select
            aria-label="Filter trade status"
            className="h-9 rounded-lg border border-[#27343a] bg-[#0b1115] px-3 text-xs text-[#b8c5c5] outline-none focus:border-[#536a54]"
            onChange={(event) => setFilter(event.target.value)}
            value={filter}
          >
            <option value="all">All trades</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
          </select>
        </div>
      </div>

      <div className="scrollbar-hidden overflow-x-auto">
        <table className="w-full min-w-[980px] border-collapse text-left">
          <thead>
            <tr className="border-b border-[#202c32] text-[9px] font-semibold tracking-[0.13em] text-[#718186]">
              <th className="px-5 py-3 font-semibold">TICKET / SYMBOL</th>
              <th className="px-3 py-3 font-semibold">TYPE</th>
              <th className="px-3 py-3 text-right font-semibold">VOLUME</th>
              <th className="px-3 py-3 text-right font-semibold">OPEN PRICE</th>
              <th className="px-3 py-3 text-right font-semibold">SL / TP</th>
              <th className="px-3 py-3 text-right font-semibold">P&amp;L</th>
              <th className="px-3 py-3 font-semibold">STATUS</th>
              <th className="px-5 py-3 font-semibold">
                <button
                  className="inline-flex items-center gap-1 font-semibold tracking-[0.13em] hover:text-[#bdc8c8]"
                  onClick={() => setSortAscending((value) => !value)}
                  type="button"
                >
                  OPEN TIME
                  {sortAscending ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((trade) => {
              const isBuy = trade.side === 'BUY'
              const pnl = Number(trade.profit_loss)
              return (
                <tr className="border-b border-[#1d282e] last:border-0 hover:bg-[#141d21]" key={trade.id}>
                  <td className="px-5 py-3.5">
                    <p className="mono text-[11px] text-[#dce6e2]">#{trade.ticket}</p>
                    <p className="mt-1 text-xs font-medium text-[#aebcba]">{trade.symbol}</p>
                  </td>
                  <td className="px-3 py-3.5">
                    <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-bold ${isBuy ? 'bg-[#1d3024] text-[#b7ed83]' : 'bg-[#352221] text-[#ff988a]'}`}>
                      {isBuy ? <ArrowUpRight size={12} /> : <ArrowDownLeft size={12} />}
                      {trade.side}
                    </span>
                  </td>
                  <td className="mono px-3 py-3.5 text-right text-xs text-[#c7d1ce]">{Number(trade.volume).toFixed(2)}</td>
                  <td className="mono px-3 py-3.5 text-right text-xs text-[#c7d1ce]">{price(trade.open_price)}</td>
                  <td className="mono px-3 py-3.5 text-right text-[10px] leading-5 text-[#95a4a4]">
                    <span className="text-[#ff9784]">{price(trade.stop_loss)}</span>
                    <br />
                    <span className="text-[#a9e178]">{price(trade.take_profit)}</span>
                  </td>
                  <td className={`mono px-3 py-3.5 text-right text-xs font-medium ${trade.profit_loss != null && Number.isFinite(pnl) ? pnl >= 0 ? 'text-[#b6f36b]' : 'text-[#ff8879]' : 'text-[#718186]'}`}>
                    {trade.profit_loss != null && Number.isFinite(pnl)
                      ? `${pnl >= 0 ? '+' : '-'}$${Math.abs(pnl).toFixed(2)}`
                      : '—'}
                  </td>
                  <td className="px-3 py-3.5">
                    <span className={`inline-flex items-center gap-1.5 text-[10px] font-semibold ${trade.status === 'open' ? 'text-[#b6f36b]' : 'text-[#839296]'}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${trade.status === 'open' ? 'bg-[#b6f36b]' : 'bg-[#647277]'}`} />
                      {trade.status}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-[10px] text-[#869497]">{time(trade.opened_at)}</td>
                </tr>
              )
            })}
            {!rows.length && (
              <tr>
                <td className="px-5 py-14 text-center text-xs text-[#77878b]" colSpan={8}>
                  No trades match this view.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
