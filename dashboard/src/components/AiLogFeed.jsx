import { BrainCircuit, Check, Clock3, Lightbulb, Sparkles } from 'lucide-react'

function confidenceOf(log) {
  const value = Number(log.context?.ai_confidence ?? log.indicators?.ai_confidence)
  return Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : null
}

function timestamp(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function LearnedKnowledgeBase({ rules }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-[#29382f] bg-[#101814]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#26332b] px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-[#354935] bg-[#1a281d] text-[#c4ec8a]">
            <Lightbulb size={17} />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-[#e8efec]">Learned Knowledge Base</h2>
            <p className="mt-1 text-[10px] text-[#819087]">Symbol-specific lessons distilled from closed trades</p>
          </div>
        </div>
        <span className="rounded-full border border-[#344338] bg-[#1a251d] px-2.5 py-1 text-[9px] font-semibold tracking-wide text-[#b8d99a]">
          {rules.length} ACTIVE {rules.length === 1 ? 'RULE' : 'RULES'}
        </span>
      </header>

      {rules.length ? (
        <div className="grid grid-cols-1 gap-3 p-4 xl:grid-cols-2">
          {rules.map((rule) => {
            const sourceTone = rule.source_outcome === 'win'
              ? 'border-[#3c5836] bg-[#1d3024] text-[#b7ed83]'
              : rule.source_outcome === 'loss'
                ? 'border-[#60403a] bg-[#33211f] text-[#ffab96]'
                : 'border-[#3a4444] bg-[#202929] text-[#aebcba]'
            return (
              <article
                className="rounded-xl border border-[#26332d] bg-[#0c1210] p-4"
                key={rule.rule_id}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-md border border-[#34433a] bg-[#17211b] px-2 py-1 text-[9px] font-bold tracking-[0.1em] text-[#b8d89a]">
                    {String(rule.category).replaceAll('_', ' ').toUpperCase()}
                  </span>
                  <span className="mono text-[10px] text-[#8fa09a]">{rule.symbol}</span>
                  <span className={`ml-auto rounded-full border px-2 py-1 text-[8px] font-bold tracking-wide ${sourceTone}`}>
                    {rule.source_outcome ? `SOURCE · ${rule.source_outcome.toUpperCase()}` : 'SOURCE · REFLECTION'}
                  </span>
                </div>
                <p className="mt-3 text-xs leading-6 text-[#c5d0ca]">{rule.rule_text}</p>
                <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-[#202b24] pt-3 text-[9px] text-[#77877f]">
                  <span>
                    WEIGHT <strong className="mono ml-1 text-[#c5d49c]">
                      {Number.isFinite(Number(rule.confidence))
                        ? `${(Number(rule.confidence) * 100).toFixed(0)}%`
                        : '—'}
                    </strong>
                  </span>
                  <span>
                    REUSED <strong className="mono ml-1 text-[#aebbb2]">
                      {Number(rule.supporting_trades) || 0}
                    </strong>
                  </span>
                  <span className="ml-auto">Trade #{rule.source_trade_id}</span>
                </div>
              </article>
            )
          })}
        </div>
      ) : (
        <div className="flex min-h-[175px] flex-col items-center justify-center px-6 text-center">
          <Sparkles className="text-[#64745e]" size={22} />
          <p className="mt-3 text-xs font-medium text-[#c1ccca]">Knowledge base is warming up</p>
          <p className="mt-1 max-w-md text-[10px] leading-5 text-[#75857d]">
            Waiting for closed trades to generate reflections. Active, symbol-specific lessons will appear here.
          </p>
        </div>
      )}
    </section>
  )
}

export default function AiLogFeed({ logs, learnedRules = [] }) {
  return (
    <div className="space-y-4">
      <LearnedKnowledgeBase rules={learnedRules} />
      <section className="flex items-center justify-between gap-3 rounded-2xl border border-[#202c32] bg-[#10171b] px-5 py-4">
        <div>
          <p className="text-[9px] font-bold tracking-[0.18em] text-[#9b86c2]">GEMINI REVIEW</p>
          <h2 className="mt-1 text-lg font-semibold text-[#e8efec]">AI insights</h2>
          <p className="mt-1 text-[11px] text-[#718186]">Entry confirmations, confidence, and recorded reasoning.</p>
        </div>
        <span className="shrink-0 rounded-full border border-[#313141] bg-[#1d1b29] px-2.5 py-1 text-[9px] font-semibold tracking-wide text-[#b9a2df]">
          {logs.length} RECENT
        </span>
      </section>

      {logs.length ? (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {logs.map((log) => {
            const trade = log.trades
            const confidence = confidenceOf(log)
            const isBuy = trade?.side === 'BUY'
            const indicators = log.indicators ?? {}
            return (
              <article
                className="overflow-hidden rounded-2xl border border-[#2b3039] bg-[#10171b]"
                key={log.id}
              >
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#202c32] px-5 py-4">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[#3b344f] bg-[#211b30] text-[#c7a6ff]">
                      <BrainCircuit size={18} />
                    </span>
                    <div className="min-w-0">
                      <h3 className="truncate text-sm font-semibold text-[#e7efec]">
                        {log.symbol ?? trade?.symbol ?? 'Unknown symbol'}
                      </h3>
                      <p className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-[#738388]">
                        <span className="inline-flex items-center gap-1">
                          <Clock3 size={11} /> {timestamp(log.created_at)}
                        </span>
                        {log.timeframe && (
                          <span className="rounded bg-[#1b262b] px-1.5 py-0.5">{log.timeframe}</span>
                        )}
                        {log.market_session && (
                          <span className="rounded bg-[#1b262b] px-1.5 py-0.5">{log.market_session}</span>
                        )}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center gap-1 rounded-full border border-[#3e5833] bg-[#1d3024] px-2.5 py-1 text-[9px] font-bold tracking-wide text-[#b7ed83]">
                      <Check size={11} /> APPROVED
                    </span>
                    <span className={`rounded-full px-2.5 py-1 text-[9px] font-bold ${isBuy ? 'bg-[#1d3024] text-[#b7ed83]' : 'bg-[#352221] text-[#ff988a]'}`}>
                      {trade?.side ?? 'ENTRY'}
                    </span>
                  </div>
                </div>

                <div className="space-y-4 px-5 py-4">
                  <div>
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-[10px] font-semibold tracking-wide text-[#8e9b9d]">
                        CONFIDENCE
                      </span>
                      <span className={`mono rounded-md px-2 py-1 text-xs font-bold ${confidence != null && confidence >= 0.7 ? 'bg-[#1d3024] text-[#b7ed83]' : 'bg-[#342a1d] text-[#e8c276]'}`}>
                        {confidence == null ? '—' : `${(confidence * 100).toFixed(0)}%`}
                      </span>
                    </div>
                    {confidence != null && (
                      <div className="h-1.5 overflow-hidden rounded-full bg-[#253137]">
                        <div
                          className={`h-full rounded-full ${confidence >= 0.7 ? 'bg-[#9cdb5c]' : 'bg-[#d5a856]'}`}
                          style={{ width: `${confidence * 100}%` }}
                        />
                      </div>
                    )}
                  </div>

                  <div className="rounded-xl border border-[#263238] bg-[#0c1216] p-4">
                    <p className="text-[9px] font-bold tracking-[0.15em] text-[#76878b]">AI REASONING</p>
                    <p className="mt-2 whitespace-pre-wrap text-xs leading-6 text-[#c0ccca]">
                      {log.reasoning || 'No reasoning was saved for this decision.'}
                    </p>
                  </div>

                  {Object.keys(indicators).length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(indicators).map(([name, value]) => (
                        <span
                          className="rounded-lg border border-[#263238] bg-[#141d21] px-2.5 py-1.5 text-[10px] text-[#91a19f]"
                          key={name}
                        >
                          <span className="text-[#65767a]">{name.replaceAll('_', ' ')}</span>
                          <span className="mono ml-2 text-[#c2cfca]">
                            {typeof value === 'number' ? value.toFixed(3) : String(value)}
                          </span>
                        </span>
                      ))}
                    </div>
                  )}
                  <p className="text-[10px] text-[#68797d]">
                    Trade ticket <span className="mono text-[#9aa9a7]">#{trade?.ticket ?? '—'}</span>
                  </p>
                </div>
              </article>
            )
          })}
        </div>
      ) : (
        <div className="flex min-h-[260px] flex-col items-center justify-center rounded-2xl border border-[#202c32] bg-[#10171b] px-6 text-center">
          <BrainCircuit className="text-[#56636a]" size={25} />
          <p className="mt-3 text-sm font-medium text-[#c1ccca]">No AI decisions yet</p>
          <p className="mt-1 max-w-sm text-xs leading-5 text-[#75858a]">
            Approved entries and their recorded reasoning appear here after the bot logs a trade.
          </p>
        </div>
      )}
    </div>
  )
}
