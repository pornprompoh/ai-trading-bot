import { ArrowDownRight, ArrowUpRight } from 'lucide-react'

export default function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
  accent = 'lime',
  trend,
}) {
  const accents = {
    lime: 'border-[#33432f] bg-[#19251a] text-[#b8f473]',
    teal: 'border-[#29433f] bg-[#142522] text-[#73d9c0]',
    blue: 'border-[#2b3c4b] bg-[#17222c] text-[#8ac5ed]',
    amber: 'border-[#463d2b] bg-[#242117] text-[#e2bd72]',
  }

  return (
    <article className="rounded-2xl border border-[#202c32] bg-[#10171b] p-4 transition hover:border-[#34443f] sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-semibold tracking-[0.12em] text-[#8b9a9e]">
          {label}
        </p>
        <span className={`flex h-8 w-8 items-center justify-center rounded-xl border ${accents[accent]}`}>
          <Icon size={16} strokeWidth={1.8} />
        </span>
      </div>
      <div className="mt-4 flex items-end justify-between gap-2">
        <p className="mono truncate text-[25px] font-medium tracking-[-0.06em] text-[#eef4f1] sm:text-[28px]">
          {value}
        </p>
        {trend != null && (
          <span
            className={`mb-1 inline-flex items-center gap-0.5 text-[11px] font-semibold ${
              trend >= 0 ? 'text-[#a9e46b]' : 'text-[#ff8879]'
            }`}
          >
            {trend >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
            {Math.abs(trend).toFixed(2)}%
          </span>
        )}
      </div>
      <p className="mt-2 text-[11px] text-[#718186]">{detail}</p>
    </article>
  )
}
