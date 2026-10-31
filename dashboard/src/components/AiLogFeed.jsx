import { BrainCircuit, Check, ChevronRight, Clock3 } from 'lucide-react'

function confidenceOf(log) {
  const value = Number(log.context?.ai_confidence ?? log.indicators?.ai_confidence)
  return Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : null
}

function timestamp(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function AiLogFeed({ logs }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-[#202c32] bg-[#10171b]">
      <div className="flex items-center justify-between border-b border-[#202c32] px-5 py-4">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-[#3b344f] bg-[#211b30] text-[#c7a6ff]">
            <BrainCircuit size={16} />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-[#e8efec]">AI decision log</h2>
            <p className="mt-0.5 text-[10px] text-[#718186]">Gemini entry confirmations</p>
          </div>
        </div>
        <span className="rounded-full border border-[#313141] bg-[#1d1b29] px-2 py-1 text-[9px] font-semibold tracking-wide text-[#b9a2df]">
          {logs.length} RECENT
        </span>
      </div>

      <div className="divide-y divide-[#1e292f]">
        {logs.map((log) => {
          const trade = log.trades
          const confidence = confidenceOf(log)
          const isBuy = trade?.side === 'BUY'
          return (
            <article className="px-5 py-4 transition hover:bg-[#141c21]" key={log.id}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${isBuy ? 'bg-[#1d3024] text-[#b7ed83]' : 'bg-[#352221] text-[#ff988a]'}`}>
                    <Check size={14} />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold text-[#dce5e2]">
                      {trade?.symbol ?? 'Unknown symbol'}
                      <span className={`ml-2 text-[9px] font-bold ${isBuy ? 'text-[#b7ed83]' : 'text-[#ff988a]'}`}>
                        {trade?.side ?? '—'}
                      </span>
                    </p>
                    <p className="mt-1 flex items-center gap-1 text-[10px] text-[#738388]">
                      <Clock3 size={10} /> {timestamp(log.created_at)}
                      {log.timeframe && <span className="ml-1 rounded bg-[#1b262b] px-1.5 py-0.5">{log.timeframe}</span>}
                    </p>
                  </div>
                </div>
                {confidence != null ? (
                  <span className={`shrink-0 rounded-md px-2 py-1 text-[10px] font-bold ${confidence >= 0.7 ? 'bg-[#1d3024] text-[#b7ed83]' : 'bg-[#342a1d] text-[#e8c276]'}`}>
                    {(confidence * 100).toFixed(0)}%
                  </span>
                ) : (
                  <span className="shrink-0 rounded-md bg-[#202a2e] px-2 py-1 text-[10px] text-[#8c999b]">—</span>
                )}
              </div>
              <p className="mt-3 line-clamp-3 pl-9 text-[11px] leading-[1.65] text-[#95a2a3]">
                {log.reasoning || 'No reasoning was saved for this decision.'}
              </p>
              {confidence != null && (
                <div className="ml-9 mt-3 h-1 overflow-hidden rounded-full bg-[#253137]">
                  <div
                    className={`h-full rounded-full ${confidence >= 0.7 ? 'bg-[#9cdb5c]' : 'bg-[#d5a856]'}`}
                    style={{ width: `${confidence * 100}%` }}
                  />
                </div>
              )}
            </article>
          )
        })}
        {!logs.length && (
          <div className="flex min-h-[190px] flex-col items-center justify-center px-6 text-center">
            <BrainCircuit className="text-[#56636a]" size={23} />
            <p className="mt-3 text-xs font-medium text-[#c1ccca]">No AI decisions yet</p>
            <p className="mt-1 max-w-xs text-[10px] leading-5 text-[#75858a]">
              Approved entries and their reasoning will appear here after the bot records a trade.
            </p>
          </div>
        )}
      </div>
      {logs.length > 0 && (
        <a
          className="flex items-center justify-between border-t border-[#202c32] px-5 py-3 text-[10px] font-semibold text-[#98a9a8] transition hover:text-[#b6f36b]"
          href="#trade-activity"
        >
          View all trade activity <ChevronRight size={14} />
        </a>
      )}
    </section>
  )
}
