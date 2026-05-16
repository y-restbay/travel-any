/**
 * ItineraryCard:渲染 generate_itinerary_summary 推送的结构化行程。
 *
 * 设计目标:
 * - 顶部一眼看到 trip_title + 日期 + 总预算
 * - 天气条:横向呈现每日天气
 * - 每天独立折叠面板,默认仅展开 Day 1,避免长行程一上来就刷屏
 * - schedule 用时间轴样式,左侧时间 + 类型 icon,右侧地点/详情
 * - 底部:总预算汇总 + 出行须知
 *
 * 不做卡片内编辑、不做拖拽排序,这些留给后续迭代。
 */
import { useState } from 'react'
import {
  CalendarDays,
  ChevronDown,
  Cloud,
  CloudRain,
  Compass,
  Footprints,
  Hotel,
  MapPin,
  Plane,
  Sparkles,
  Sun,
  Utensils,
  Wallet,
} from 'lucide-react'
import type {
  Itinerary,
  ItineraryDay,
  ItineraryScheduleItem,
  ItineraryWeatherEntry,
} from '../types'

const SCHEDULE_TYPE_META: Record<
  string,
  { label: string; icon: typeof MapPin; tint: string }
> = {
  depart: { label: '出发', icon: Plane, tint: 'bg-clay/60 text-clayDeep' },
  visit: { label: '游览', icon: MapPin, tint: 'bg-sage/55 text-moss' },
  meal: { label: '用餐', icon: Utensils, tint: 'bg-clay/40 text-clayDeep' },
  transit: { label: '中转', icon: Footprints, tint: 'bg-paper text-muted border border-line' },
  return: { label: '返程', icon: Plane, tint: 'bg-clay/60 text-clayDeep' },
}

export default function ItineraryCard({ itinerary }: { itinerary: Itinerary }) {
  const validWeatherEntries = getValidWeatherEntries(itinerary.weather_summary)
  const validDays = itinerary.days
    .map((day) => ({ ...day, schedule: getValidScheduleItems(day.schedule) }))
    .filter((day) => day.schedule.length > 0)

  if (validDays.length === 0) return null

  return (
    <section className="mt-3 overflow-hidden rounded-3xl border border-line/70 bg-paper/95 shadow-soft">
      <Header itinerary={itinerary} />
      <MetaRow itinerary={itinerary} />
      {validWeatherEntries.length > 0 && <WeatherStrip entries={validWeatherEntries} />}
      <div className="border-t border-line/60 px-5 py-4">
        {validDays.map((day, index) => (
          <DayPanel key={day.day_number} day={day} defaultOpen={index === 0} />
        ))}
      </div>
      <Footer itinerary={itinerary} />
    </section>
  )
}

function Header({ itinerary }: { itinerary: Itinerary }) {
  const total = itinerary.total_budget?.total
  return (
    <header className="flex items-start gap-3 border-b border-line/60 bg-gradient-to-br from-clay/40 to-paper px-5 py-4">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-paper text-clayDeep shadow-quiet">
        <Compass size={18} />
      </span>
      <div className="min-w-0 flex-1">
        <h3 className="truncate text-[15px] font-semibold text-ink">
          {itinerary.trip_title || '行程概览'}
        </h3>
        <p className="mt-0.5 truncate text-xs text-muted">
          {itinerary.trip_dates || '日期待定'}
        </p>
        {itinerary.summary && (
          <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted/90">{itinerary.summary}</p>
        )}
      </div>
      {total !== undefined && total !== null && (
        <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-ink px-3 py-1 text-[11px] text-paper">
          <Wallet size={12} />¥ {total}
        </span>
      )}
    </header>
  )
}

function MetaRow({ itinerary }: { itinerary: Itinerary }) {
  const items: Array<[string, string | undefined]> = [
    ['目的地', itinerary.meta?.destination],
    ['人数', itinerary.meta?.people],
    ['预算', itinerary.meta?.budget],
    ['出行', itinerary.meta?.transport_mode],
    ['住宿', itinerary.meta?.accommodation],
    ['偏好', itinerary.meta?.preferences],
  ].filter(([, value]) => Boolean(value)) as Array<[string, string]>
  if (items.length === 0) return null
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 border-b border-line/60 px-5 py-3 text-xs md:grid-cols-3">
      {items.map(([label, value]) => (
        <div key={label} className="flex items-center gap-2">
          <dt className="shrink-0 text-muted">{label}</dt>
          <dd className="truncate text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function WeatherStrip({ entries }: { entries: ItineraryWeatherEntry[] }) {
  return (
    <div className="flex gap-2 overflow-x-auto border-b border-line/60 bg-canvas/30 px-5 py-3 soft-scrollbar">
      {entries.map((entry, index) => (
        <div
          key={index}
          className="flex min-w-[110px] shrink-0 items-center gap-2 rounded-2xl bg-paper/90 px-3 py-2 shadow-quiet"
        >
          <span className="grid h-7 w-7 place-items-center rounded-full bg-sage/45 text-moss">
            {weatherIcon(entry.condition)}
          </span>
          <div className="min-w-0">
            {hasMeaningfulText(entry.date) && (
              <div className="truncate text-[11px] text-muted">{entry.date}</div>
            )}
            <div className="truncate text-xs font-medium text-ink">
              {[entry.condition, entry.temp].filter(hasMeaningfulText).join(' · ')}
            </div>
            {hasMeaningfulText(entry.tip) && (
              <div className="truncate text-[10px] text-muted/80">{entry.tip}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function weatherIcon(condition?: string) {
  if (!condition) return <Sun size={14} />
  if (/雨|雷|阵/.test(condition)) return <CloudRain size={14} />
  if (/云|阴/.test(condition)) return <Cloud size={14} />
  return <Sun size={14} />
}

function DayPanel({ day, defaultOpen }: { day: ItineraryDay; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  const schedule = getValidScheduleItems(day.schedule)
  if (schedule.length === 0) return null

  return (
    <div className="mb-3 overflow-hidden rounded-2xl border border-line/60 bg-paper/60 last:mb-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-clay/20"
        aria-expanded={open}
      >
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-2xl bg-clay/60 text-clayDeep">
          <CalendarDays size={15} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[13px] font-medium text-ink">
            Day {day.day_number}
            {day.title && <span className="text-muted">· {day.title}</span>}
          </div>
          {day.theme && (
            <div className="mt-0.5 truncate text-[11px] text-muted">{day.theme}</div>
          )}
        </div>
        {day.day_cost?.total !== undefined && day.day_cost?.total !== null && (
          <span className="shrink-0 rounded-full bg-canvas px-2 py-0.5 text-[11px] text-muted">
            ¥{day.day_cost.total}
          </span>
        )}
        <ChevronDown
          size={15}
          className={`shrink-0 text-muted transition ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div className="border-t border-line/60 px-4 py-3">
          <ol className="space-y-3">
            {schedule.map((item, index) => (
              <ScheduleItem key={index} item={item} />
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}

function ScheduleItem({ item }: { item: ItineraryScheduleItem }) {
  const meta = SCHEDULE_TYPE_META[(item.type ?? '').toLowerCase()] ?? {
    label: item.type ?? '',
    icon: Sparkles,
    tint: 'bg-paper text-muted border border-line',
  }
  const Icon = meta.icon
  const title = getScheduleTitle(item)
  const detailLines: string[] = []
  if (hasMeaningfulText(item.note)) detailLines.push(item.note)
  if (item.highlights?.length) detailLines.push(`亮点:${item.highlights.join('、')}`)
  if (item.must_try?.length) detailLines.push(`推荐:${item.must_try.join('、')}`)
  if (hasMeaningfulText(item.cuisine)) detailLines.push(`菜系:${item.cuisine}`)
  if (hasMeaningfulText(item.tips)) detailLines.push(`贴士:${item.tips}`)
  return (
    <li className="grid grid-cols-[28px_1fr_auto] items-start gap-3 text-xs">
      <span className={`mt-0.5 grid h-7 w-7 place-items-center rounded-full ${meta.tint}`}>
        <Icon size={13} />
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-2 text-ink">
          {hasMeaningfulText(item.time) && (
            <span className="rounded-full bg-canvas px-2 py-0.5 text-[10px] text-muted">
              {item.time}
            </span>
          )}
          <span className="font-medium">{title}</span>
          <span className="text-[10px] text-muted">{meta.label}</span>
        </div>
        {detailLines.length > 0 && (
          <p className="mt-1 whitespace-pre-wrap text-[11px] leading-5 text-muted">
            {detailLines.join('\n')}
          </p>
        )}
      </div>
      <span className="shrink-0 text-[11px] text-muted">
        {[
          item.duration_min ? `${item.duration_min} 分钟` : '',
          item.ticket ? `门票 ¥${item.ticket}` : '',
          item.cost ? `¥${item.cost}` : '',
        ]
          .filter(Boolean)
          .join(' / ')}
      </span>
    </li>
  )
}

const PLACEHOLDER_VALUES = new Set([
  '-',
  '--',
  '—',
  'n/a',
  'na',
  'none',
  'null',
  '无',
  '暂无',
  '待定',
  '未定',
  '未知',
  '不详',
])

function cleanText(value: unknown): string {
  if (value === undefined || value === null) return ''
  return String(value).trim()
}

function hasMeaningfulText(value: unknown): value is string {
  const text = cleanText(value)
  return text.length > 0 && !PLACEHOLDER_VALUES.has(text.toLowerCase())
}

function getValidWeatherEntries(entries?: ItineraryWeatherEntry[]) {
  if (!Array.isArray(entries)) return []
  return entries
    .map((entry) => ({
      ...entry,
      date: hasMeaningfulText(entry.date) ? cleanText(entry.date) : undefined,
      condition: hasMeaningfulText(entry.condition) ? cleanText(entry.condition) : undefined,
      temp: hasMeaningfulText(entry.temp) ? cleanText(entry.temp) : undefined,
      tip: hasMeaningfulText(entry.tip) ? cleanText(entry.tip) : undefined,
    }))
    .filter((entry) => hasMeaningfulText(entry.condition) || hasMeaningfulText(entry.temp))
}

function getValidScheduleItems(schedule?: ItineraryScheduleItem[]) {
  if (!Array.isArray(schedule)) return []
  return schedule
    .map((item) => ({
      ...item,
      time: hasMeaningfulText(item.time) ? cleanText(item.time) : undefined,
      type: hasMeaningfulText(item.type) ? cleanText(item.type) : undefined,
      place: hasMeaningfulText(item.place) ? cleanText(item.place) : undefined,
      note: hasMeaningfulText(item.note) ? cleanText(item.note) : undefined,
      from: hasMeaningfulText(item.from) ? cleanText(item.from) : undefined,
      to: hasMeaningfulText(item.to) ? cleanText(item.to) : undefined,
      tips: hasMeaningfulText(item.tips) ? cleanText(item.tips) : undefined,
      cuisine: hasMeaningfulText(item.cuisine) ? cleanText(item.cuisine) : undefined,
      highlights: item.highlights?.filter(hasMeaningfulText),
      must_try: item.must_try?.filter(hasMeaningfulText),
    }))
    .filter((item) => Boolean(getScheduleTitle(item)))
}

function getScheduleTitle(item: ItineraryScheduleItem) {
  if (hasMeaningfulText(item.place)) return cleanText(item.place)
  if (hasMeaningfulText(item.from) && hasMeaningfulText(item.to)) {
    return `${cleanText(item.from)} → ${cleanText(item.to)}`
  }
  if (hasMeaningfulText(item.note)) return cleanText(item.note)
  if (item.highlights?.length) return item.highlights.join('、')
  if (item.must_try?.length) return item.must_try.join('、')
  if (hasMeaningfulText(item.cuisine)) return cleanText(item.cuisine)
  if (hasMeaningfulText(item.tips)) return cleanText(item.tips)
  return ''
}

function Footer({ itinerary }: { itinerary: Itinerary }) {
  const budget = itinerary.total_budget || {}
  const notes = itinerary.important_notes || []
  const budgetEntries: Array<[string, number | undefined]> = [
    ['门票', budget.tickets],
    ['餐饮', budget.meals],
    ['交通', budget.transport],
    ['住宿', budget.accommodation],
  ]
  const hasBudget = budgetEntries.some(([, value]) => value !== undefined && value !== null)
  if (!hasBudget && notes.length === 0) return null
  return (
    <footer className="space-y-3 border-t border-line/60 bg-canvas/30 px-5 py-4">
      {hasBudget && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {budgetEntries.map(([label, value]) =>
            value === undefined || value === null ? null : (
              <div key={label} className="rounded-2xl bg-paper px-3 py-2 shadow-quiet">
                <div className="text-[10px] uppercase tracking-wider text-muted/70">{label}</div>
                <div className="mt-0.5 text-[13px] font-medium text-ink">¥ {value}</div>
              </div>
            ),
          )}
        </div>
      )}
      {notes.length > 0 && (
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs text-muted">
            <Hotel size={12} /> 出行须知
          </div>
          <ul className="space-y-1 text-[11px] leading-5 text-muted">
            {notes.map((note, index) => (
              <li key={index}>· {note}</li>
            ))}
          </ul>
        </div>
      )}
    </footer>
  )
}
