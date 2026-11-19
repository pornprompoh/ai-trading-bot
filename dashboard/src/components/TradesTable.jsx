import { Fragment, useMemo, useState } from 'react'
import { ArrowDownLeft, ArrowUpRight, ChevronDown, ChevronUp, Search, Sparkles } from 'lucide-react'

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

function ExecutionSourceBadge({ source }) {
  const isManual = source === 'MANUAL'
  return (
    <span className={`inline-flex items-center rounded-full border px-1.5 py-0.5 text-[8px] font-bold tracking-wide ${
      isManual
        ? 'border-[#28545f] bg-[#122a31] text-[#7bd5e8]'
        : 'border-[#36583b] bg-[#19291d] text-[#b6e783]'
    }`}>
      {isManual ? 'MANUAL' : 'AI BOT'}
    </span>
  )
}

function TradeSection({
  title,
  description,
  trades,
  sortAscending,
  onToggleSort,
  reflectionsByTradeId,
}) {
  const [expandedTradeId, setExpandedTradeId] = useState(null)
  const showPostMortem = title === 'Closed history'
  return (
    <section className="overflow-hidden rounded-2xl border border-[#202c32] bg-[#10171b]">
      <div className="flex items-center justify-between border-b border-[#202c32] px-5 py-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-[#e8efec]">{title}</h2>
            <span className="mono rounded-full border border-[#2a373d] bg-[#172126] px-2 py-0.5 text-[10px] text-[#9caaaa]">
              {trades.length}
            </span>
          </div>
          <p className="mt-1 text-[11px] text-[#718186]">{description}</p>
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
              {showPostMortem && <th className="px-3 py-3 font-semibold">POST-MORTEM</th>}
              <th className="px-5 py-3 font-semibold">
                <button
                  className="inline-flex items-center gap-1 font-semibold tracking-[0.13em] hover:text-[#bdc8c8]"
                  onClick={onToggleSort}
                  type="button"
                >
                  OPEN TIME
                  {sortAscending ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade) => {
              const isBuy = trade.side === 'BUY'
              const pnl = Number(trade.profit_loss)
              const reflection = reflectionsByTradeId.get(String(trade.id))
              const isExpanded = expandedTradeId === String(trade.id)
              return (
                <Fragment key={trade.id}>
                <tr className="border-b border-[#1d282e] last:border-0 hover:bg-[#141d21]">
                  <td className="px-5 py-3.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <p className="mono text-[11px] text-[#dce6e2]">#{trade.ticket}</p>
                      <ExecutionSourceBadge source={trade.execution_source} />
                    </div>
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
                  {showPostMortem && (
                    <td className="px-3 py-3.5">
                      <button
                        aria-expanded={isExpanded}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-[#3b344f] bg-[#211b30] px-2.5 py-1.5 text-[9px] font-semibold text-[#c7a6ff] transition hover:border-[#5b4b78] hover:bg-[#29213a]"
                        onClick={() => setExpandedTradeId(isExpanded ? null : String(trade.id))}
                        type="button"
                      >
                        <Sparkles size={11} />
                        {isExpanded ? 'Hide critique' : 'Post-mortem'}
                      </button>
                    </td>
                  )}
                  <td className="px-5 py-3.5 text-[10px] text-[#869497]">{time(trade.opened_at)}</td>
                </tr>
                {showPostMortem && isExpanded && (
                  <tr className="border-b border-[#1d282e]">
                    <td className="px-5 py-4" colSpan={9}>
                      {reflection ? (
                        <div className="grid gap-3 rounded-xl border border-[#343044] bg-[#15131d] p-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <span className={`rounded-full border px-2.5 py-1 text-[9px] font-bold tracking-wide ${reflection.outcome === 'win' ? 'border-[#3e5833] bg-[#1d3024] text-[#b7ed83]' : reflection.outcome === 'loss' ? 'border-[#604040] bg-[#302020] text-[#ffaaa0]' : 'border-[#3a4444] bg-[#202929] text-[#aebcba]'}`}>
                                {String(reflection.outcome).toUpperCase()}
                              </span>
                              {reflection.category && (
                                <span className="rounded-md border border-[#3b344f] bg-[#211b30] px-2 py-1 text-[9px] font-semibold tracking-wide text-[#c7a6ff]">
                                  {String(reflection.category).replaceAll('_', ' ').toUpperCase()}
                                </span>
                              )}
                            </div>
                            <p className="mt-3 text-[9px] font-bold tracking-[0.14em] text-[#8b7aa8]">KEY LESSON</p>
                            <p className="mt-1 text-xs leading-5 text-[#d0c8dc]">{reflection.lesson}</p>
                          </div>
                          <div className="rounded-lg border border-[#2a2734] bg-[#100f16] p-3">
                            <p className="text-[9px] font-bold tracking-[0.14em] text-[#8b7aa8]">
                              {reflection.outcome === 'loss' ? 'MISSED WARNING / CRITIQUE' : 'SUCCESS FACTOR / CRITIQUE'}
                            </p>
                            <p className="mt-2 text-[10px] leading-5 text-[#b5adbf]">{reflection.lesson}</p>
                            {reflection.original_ai_reasoning && (
                              <div className="mt-3 border-t border-[#292632] pt-3">
                                <p className="text-[8px] font-bold tracking-[0.12em] text-[#716a7d]">ORIGINAL ENTRY REASONING</p>
                                <p className="mt-1 text-[10px] leading-5 text-[#928b9d]">{reflection.original_ai_reasoning}</p>
                              </div>
                            )}
                          </div>
                        </div>
                      ) : (
                        <div className="rounded-xl border border-[#343044] bg-[#15131d] px-4 py-3 text-[10px] text-[#948aa3]">
                          Post-mortem reflection is pending for this closed trade.
                        </div>
                      )}
                    </td>
                  </tr>
                )}
                </Fragment>
              )
            })}
            {!trades.length && (
              <tr>
                <td className="px-5 py-12 text-center text-xs text-[#77878b]" colSpan={showPostMortem ? 9 : 8}>
                  No trades in this section.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default function TradesTable({ trades, reflections = [] }) {
  const [search, setSearch] = useState('')
  const [sortAscending, setSortAscending] = useState(false)
  const [sourceFilter, setSourceFilter] = useState('ALL')

  const filteredTrades = useMemo(() => {
    const query = search.trim().toLowerCase()
    return trades
      .filter((trade) => {
        const matchesSearch = !query
          || `${trade.ticket} ${trade.symbol}`.toLowerCase().includes(query)
        const source = trade.execution_source === 'MANUAL' ? 'MANUAL' : 'BOT_SMC'
        const matchesSource = sourceFilter === 'ALL'
          || (sourceFilter === 'BOT_SMC' && source === 'BOT_SMC')
          || (sourceFilter === 'MANUAL' && source === 'MANUAL')
        return matchesSearch && matchesSource
      })
      .sort((a, b) => {
        const difference = new Date(a.opened_at).getTime() - new Date(b.opened_at).getTime()
        return sortAscending ? difference : -difference
      })
  }, [search, sortAscending, sourceFilter, trades])
  const openTrades = filteredTrades.filter((trade) => trade.status === 'open')
  const closedTrades = filteredTrades.filter((trade) => trade.status === 'closed')
  const reflectionsByTradeId = useMemo(
    () => new Map(reflections.map((reflection) => [String(reflection.trade_id), reflection])),
    [reflections],
  )
  const toggleSort = () => setSortAscending((value) => !value)

  return (
    <div className="space-y-4">
      <section className="flex flex-col gap-3 rounded-2xl border border-[#202c32] bg-[#10171b] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[9px] font-bold tracking-[0.18em] text-[#789078]">EXECUTION HISTORY</p>
          <h2 className="mt-1 text-lg font-semibold text-[#e8efec]">Trade activity</h2>
          <p className="mt-1 text-[11px] text-[#718186]">Open positions and completed trades, shown separately.</p>
        </div>
        <div className="flex flex-col gap-3 sm:items-end">
          <label className="relative min-w-[180px] sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#718186]" size={14} />
            <input
              aria-label="Search trades"
              className="h-10 w-full rounded-lg border border-[#27343a] bg-[#0b1115] pl-9 pr-3 text-xs text-[#e4ece9] outline-none placeholder:text-[#59686d] focus:border-[#536a54]"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search ticket or symbol"
              value={search}
            />
          </label>
          <div aria-label="Filter trades by execution source" className="flex items-center gap-1 rounded-lg border border-[#243037] bg-[#0b1115] p-1" role="group">
            {[
              { id: 'ALL', label: 'All', count: trades.length },
              { id: 'BOT_SMC', label: 'AI Bot', count: trades.filter((trade) => trade.execution_source !== 'MANUAL').length },
              { id: 'MANUAL', label: 'Manual', count: trades.filter((trade) => trade.execution_source === 'MANUAL').length },
            ].map((item) => {
              const selected = sourceFilter === item.id
              return (
                <button
                  aria-pressed={selected}
                  className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[9px] font-semibold transition ${
                    selected
                      ? item.id === 'MANUAL'
                        ? 'bg-[#17323a] text-[#8de0ee]'
                        : item.id === 'BOT_SMC'
                          ? 'bg-[#1d3024] text-[#b7ed83]'
                          : 'bg-[#263237] text-[#e3ece8]'
                      : 'text-[#78888b] hover:text-[#d4dfda]'
                  }`}
                  key={item.id}
                  onClick={() => setSourceFilter(item.id)}
                  type="button"
                >
                  {item.label}
                  <span className="mono opacity-70">{item.count}</span>
                </button>
              )
            })}
          </div>
        </div>
      </section>
      <TradeSection
        description="Positions currently open in the trading account"
        onToggleSort={toggleSort}
        sortAscending={sortAscending}
        title="Open positions"
        trades={openTrades}
        reflectionsByTradeId={reflectionsByTradeId}
      />
      <TradeSection
        description="Closed positions and realized results"
        onToggleSort={toggleSort}
        sortAscending={sortAscending}
        title="Closed history"
        trades={closedTrades}
        reflectionsByTradeId={reflectionsByTradeId}
      />
    </div>
  )
}
