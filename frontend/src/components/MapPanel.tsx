/**
 * MapPanel：右侧地图区域，渲染 get_directions 推送的路线。
 *
 * 三档渲染：
 * 1. 没有数据：占位提示（带向导文字）
 * 2. 有 VITE_AMAP_JS_KEY：动态加载高德 JS API，渲染真实地图（marker + polyline + setBounds）
 * 3. 没有 JS Key：降级 SVG 草图，把 polyline / markers 缩放到画布里画出来
 *
 * 通过 useImperativeHandle 暴露 renderRoute(payload) 给父组件命令式调用，
 * 这样可以在 SSE 事件到达时立刻刷新地图，不必走 props/state 抖动。
 */
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import { Compass, Loader2, MapPin, Navigation, RefreshCcw, Sparkles } from 'lucide-react'
import type { MapPayload } from '../types'

const AMAP_JS_KEY = import.meta.env.VITE_AMAP_JS_KEY ?? ''
const AMAP_SECURITY_CODE = import.meta.env.VITE_AMAP_SECURITY_JS_CODE ?? ''
const AMAP_VERSION = '2.0'
const AMAP_PLUGINS = 'AMap.Polyline,AMap.Marker'
const OVERVIEW_COLOR = '#2F2A25'
const ROUTE_COLORS = ['#B98D68', '#65735D', '#5876A6', '#A86F7A', '#7D6CA8', '#B59B48']

export type MapPanelHandle = {
  renderRoute: (payload: MapPayload) => void
  clear: () => void
}

type MapPanelProps = {
  routes?: MapPayload[]
}

type AMapState =
  | { stage: 'idle' }
  | { stage: 'loading' }
  | { stage: 'ready' }
  | { stage: 'error'; reason: string }

const MapPanel = forwardRef<MapPanelHandle, MapPanelProps>(({ routes = [] }, ref) => {
  const [route, setRoute] = useState<MapPayload | null>(null)
  const [activeRouteIndex, setActiveRouteIndex] = useState(-1)
  const [amap, setAmap] = useState<AMapState>({ stage: 'idle' })
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapInstanceRef = useRef<any>(null)
  const overlayRef = useRef<any[]>([])

  // ---- 命令式 API ----
  useImperativeHandle(
    ref,
    () => ({
      renderRoute: (payload) => {
        setRoute(payload)
        const index = routes.findIndex((item) => item === payload || item.route_name === payload.route_name)
        setActiveRouteIndex(routes.length > 1 ? -1 : index >= 0 ? index : 0)
      },
      clear: () => {
        setRoute(null)
        setActiveRouteIndex(-1)
      },
    }),
    [routes],
  )

  useEffect(() => {
    if (routes.length === 0) return
    if (routes.length > 1 && activeRouteIndex < 0) {
      setRoute(buildOverviewRoute(routes))
      return
    }
    const nextIndex = Math.min(Math.max(activeRouteIndex, 0), routes.length - 1)
    setActiveRouteIndex(nextIndex)
    setRoute(routes[nextIndex])
  }, [routes])

  function selectRoute(index: number) {
    if (index < 0) {
      setActiveRouteIndex(-1)
      setRoute(buildOverviewRoute(routes))
      return
    }
    const next = routes[index]
    if (!next) return
    setActiveRouteIndex(index)
    setRoute(next)
  }

  // ---- 加载高德 JS API（首次需要时） ----
  const loadAmap = useCallback(async () => {
    if (!AMAP_JS_KEY) {
      setAmap({ stage: 'error', reason: 'no-key' })
      return
    }
    if (typeof window !== 'undefined' && window.AMap) {
      setAmap({ stage: 'ready' })
      return
    }
    setAmap({ stage: 'loading' })
    try {
      if (AMAP_SECURITY_CODE) {
        window._AMapSecurityConfig = { securityJsCode: AMAP_SECURITY_CODE }
      }
      await injectScript(
        `https://webapi.amap.com/maps?v=${AMAP_VERSION}&key=${encodeURIComponent(AMAP_JS_KEY)}&plugin=${AMAP_PLUGINS}`,
      )
      if (typeof window !== 'undefined' && window.AMap) {
        setAmap({ stage: 'ready' })
      } else {
        setAmap({ stage: 'error', reason: 'script-missing' })
      }
    } catch (err) {
      setAmap({ stage: 'error', reason: (err as Error).message || 'load-failed' })
    }
  }, [])

  // 第一次有路线数据时再加载脚本，不浪费首屏
  useEffect(() => {
    if (route && amap.stage === 'idle') {
      void loadAmap()
    }
  }, [route, amap.stage, loadAmap])

  // ---- 真实高德地图渲染 ----
  useEffect(() => {
    if (amap.stage !== 'ready') return
    if (!containerRef.current || !route) return
    const AMap = window.AMap
    if (!AMap) return

    if (!mapInstanceRef.current) {
      mapInstanceRef.current = new AMap.Map(containerRef.current, {
        zoom: 11,
        viewMode: '2D',
        // Claude 风格：暖色为主的地图样式 ID（高德通用样式）
        mapStyle: 'amap://styles/whitesmoke',
      })
    }
    const map = mapInstanceRef.current
    const routeColor = activeRouteIndex < 0 ? OVERVIEW_COLOR : ROUTE_COLORS[activeRouteIndex % ROUTE_COLORS.length]

    // 清掉上一次的覆盖物
    overlayRef.current.forEach((o) => map.remove(o))
    overlayRef.current = []

    const markers = route.markers.map((m, idx) => {
      const isFirst = idx === 0
      const isLast = idx === route.markers.length - 1
      const color = isFirst ? '#65735D' : isLast ? routeColor : '#2F2A25'
      return new AMap.Marker({
        position: [m.lng, m.lat],
        title: m.name,
        // 内置默认 marker 即可；自定义 content 在 mock 时不一定有 css 加载完成
        label: { content: `<span style="background:${color};color:#fff;padding:2px 8px;border-radius:999px;font-size:11px;box-shadow:0 8px 20px rgba(47,42,37,.14);">${m.order}. ${m.name}</span>`, direction: 'top' },
      })
    })
    markers.forEach((mk: any) => map.add(mk))
    overlayRef.current.push(...markers)

    if (route.polyline.length >= 2) {
      const path = route.polyline.map(([lng, lat]) => [lng, lat])
      const polyline = new AMap.Polyline({
        path,
        strokeColor: routeColor,
        strokeWeight: 6,
        strokeOpacity: 0.72,
        lineJoin: 'round',
        lineCap: 'round',
      })
      map.add(polyline)
      overlayRef.current.push(polyline)
    }

    if (route.bounds) {
      const sw = new AMap.LngLat(route.bounds.sw[0], route.bounds.sw[1])
      const ne = new AMap.LngLat(route.bounds.ne[0], route.bounds.ne[1])
      map.setBounds(new AMap.Bounds(sw, ne), false, [60, 60, 60, 60])
    } else if (markers.length > 0) {
      map.setFitView(markers, false, [60, 60, 60, 60])
    }
  }, [amap.stage, route, activeRouteIndex])

  // ---- 渲染 ----
  return (
    <div className="flex h-full flex-col bg-gradient-to-b from-paper/60 to-canvas/40">
      {/* Panel Header — Claude 风格的卡片化标题 */}
      <div className="flex-shrink-0 border-b border-line/60 bg-paper/80 px-5 py-4 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-2xl bg-clay/60 text-clayDeep">
            <Compass size={18} />
          </span>
          <div className="min-w-0 flex-1" />
          {route && (
            <button
              type="button"
              onClick={() => setRoute(null)}
              className="grid h-7 w-7 place-items-center rounded-xl text-muted hover:bg-clay/30 hover:text-ink"
              title="清空地图"
            >
              <RefreshCcw size={13} />
            </button>
          )}
        </div>
        {routes.length > 1 && (
          <div className="soft-scrollbar mt-3 flex gap-2 overflow-x-auto pb-0.5">
            <button
              type="button"
              onClick={() => selectRoute(-1)}
              className={`shrink-0 rounded-3xl px-3 py-1.5 text-[12px] font-medium transition ${
                activeRouteIndex < 0
                  ? 'bg-ink text-paper shadow-quiet'
                  : 'bg-[#F8F6F1] text-muted hover:bg-clay/35 hover:text-ink'
              }`}
              title="查看全部天数的总路线"
            >
              <span
                className="mr-1 inline-block h-2 w-2 rounded-full align-middle"
                style={{ backgroundColor: OVERVIEW_COLOR }}
              />
              总路线
            </button>
            {routes.map((item, index) => {
              const active = index === activeRouteIndex
              const color = ROUTE_COLORS[index % ROUTE_COLORS.length]
              return (
                <button
                  key={`${item.route_name}-${index}`}
                  type="button"
                  onClick={() => selectRoute(index)}
                  className={`shrink-0 rounded-3xl px-3 py-1.5 text-[12px] font-medium transition ${
                    active
                      ? 'bg-ink text-paper shadow-quiet'
                      : 'bg-[#F8F6F1] text-muted hover:bg-clay/35 hover:text-ink'
                  }`}
                  title={item.route_name}
                >
                  <span
                    className="mr-1 inline-block h-2 w-2 rounded-full align-middle"
                    style={{ backgroundColor: color }}
                  />
                  {getRouteTabLabel(item, index)}
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Panel Body */}
      <div className="relative flex-1 overflow-hidden">
        {!route && <EmptyState />}

        {route && amap.stage === 'loading' && (
          <div className="absolute inset-0 grid place-items-center text-sm text-muted">
            <div className="flex items-center gap-2">
              <Loader2 className="animate-spin" size={16} /> 正在加载地图组件…
            </div>
          </div>
        )}

        {route && amap.stage === 'ready' && (
          <div ref={containerRef} className="absolute inset-0" />
        )}

        {route && amap.stage === 'error' && <FallbackSvg route={route} reason={amap.reason} color={activeRouteIndex < 0 ? OVERVIEW_COLOR : ROUTE_COLORS[activeRouteIndex % ROUTE_COLORS.length]} />}
      </div>

      {/* Panel Footer — 路线摘要 */}
      {route && <RouteSummary route={route} color={activeRouteIndex < 0 ? OVERVIEW_COLOR : ROUTE_COLORS[activeRouteIndex % ROUTE_COLORS.length]} />}
    </div>
  )
})

MapPanel.displayName = 'MapPanel'

export default MapPanel

// --------------------------------------------------------------------- 子组件
function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="rounded-3xl bg-sage/30 p-5">
        <Navigation size={28} className="text-moss/60" />
      </div>
      <p className="mt-4 text-sm font-medium text-ink/80">地图区域</p>
      <p className="mt-2 max-w-[230px] text-xs leading-5 text-muted">
        当 WanderBot 调用路线规划工具时，行程动线会自动出现在这里。
        试试问它 “苏州一日游怎么安排” 或 “从外滩到迪士尼怎么走”。
      </p>
    </div>
  )
}

function RouteSummary({ route, color }: { route: MapPayload; color: string }) {
  const { distance_km, duration_min, cost_yuan } = route.summary
  return (
    <div className="flex-shrink-0 border-t border-line/60 bg-paper/80 px-5 py-3 text-xs text-muted backdrop-blur-sm">
      <div className="mb-2 h-1 rounded-full" style={{ backgroundColor: color }} />
      <div className="grid grid-cols-3 gap-2">
        <SummaryCell label="里程" value={`${distance_km} km`} />
        <SummaryCell label={route.mode === 'walking' ? '步行' : '驾车'} value={`${duration_min} 分钟`} />
        <SummaryCell
          label="过路费"
          value={cost_yuan === null || cost_yuan === undefined ? '—' : `¥ ${cost_yuan}`}
        />
      </div>
    </div>
  )
}

function SummaryCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-canvas/60 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-muted/70">{label}</div>
      <div className="mt-0.5 text-[13px] font-medium text-ink">{value}</div>
    </div>
  )
}

function FallbackSvg({ route, reason, color }: { route: MapPayload; reason: string; color: string }) {
  // 没 JS Key 时的降级渲染：把 polyline 等比缩放到 SVG viewBox 里画一条草图
  const PADDING = 24
  const W = 360
  const H = 320
  const points = route.polyline.length >= 2 ? route.polyline : route.markers.map((m) => [m.lng, m.lat] as [number, number])
  if (points.length === 0) {
    return <EmptyState />
  }
  const lngs = points.map((p) => p[0])
  const lats = points.map((p) => p[1])
  const minLng = Math.min(...lngs)
  const maxLng = Math.max(...lngs)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const spanLng = maxLng - minLng || 1
  const spanLat = maxLat - minLat || 1
  const projX = (lng: number) => PADDING + ((lng - minLng) / spanLng) * (W - PADDING * 2)
  const projY = (lat: number) => H - PADDING - ((lat - minLat) / spanLat) * (H - PADDING * 2) // y 反向

  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${projX(p[0]).toFixed(1)} ${projY(p[1]).toFixed(1)}`).join(' ')

  return (
    <div className="absolute inset-0 flex flex-col items-stretch overflow-hidden">
      <div className="flex items-center gap-2 bg-clay/40 px-4 py-2 text-[11px] text-ink/70">
        <Sparkles size={12} />
        <span className="truncate">
          {reason === 'no-key' ? '未配置 VITE_AMAP_JS_KEY，使用草图模式' : '高德地图脚本加载失败，使用草图模式'}
        </span>
      </div>
      <div className="flex flex-1 items-center justify-center">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full max-h-[420px]">
          {/* 背景纸张纹理 */}
          <rect x="0" y="0" width={W} height={H} fill="#FCFBF8" />
          <path d={pathD} fill="none" stroke={color} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" opacity={0.72} />
          {route.markers.map((m) => {
            const cx = projX(m.lng)
            const cy = projY(m.lat)
            const isFirst = m.order === 1
            const isLast = m.order === route.markers.length
            const fill = isFirst ? '#65735D' : isLast ? color : '#2F2A25'
            return (
              <g key={m.order}>
                <circle cx={cx} cy={cy} r={6} fill={fill} stroke="#FCFBF8" strokeWidth={2} />
                <text x={cx} y={cy - 12} textAnchor="middle" fontSize={11} fill="#2F2A25">
                  {m.order}. {m.name}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
      <div className="flex flex-wrap gap-2 px-4 pb-3 text-[11px] text-muted">
        {route.markers.map((m) => (
          <span key={m.order} className="inline-flex items-center gap-1 rounded-full bg-paper px-2 py-1 shadow-quiet">
            <MapPin size={10} className="text-clayDeep" />
            {m.order}. {m.name}
          </span>
        ))}
      </div>
    </div>
  )
}

// --------------------------------------------------------------------- helpers
function formatRouteHint(route: MapPayload) {
  const tag = route.mode === 'walking' ? '步行' : '驾车'
  const stops = route.markers.length
  return `${tag} · ${stops} 个停靠点 · ${route.summary.distance_km} km`
}

function getRouteTabLabel(route: MapPayload, index: number) {
  const matched = route.route_name.match(/day\s*(\d+)|第\s*(\d+)\s*天|D\s*(\d+)/i)
  const dayNumber = matched?.[1] || matched?.[2] || matched?.[3]
  if (dayNumber) return `Day ${dayNumber}`
  if (route.route_name && route.route_name.length <= 8) return route.route_name
  return `路线 ${index + 1}`
}

function buildOverviewRoute(routes: MapPayload[]): MapPayload {
  const markers = routes.flatMap((route, routeIndex) =>
    route.markers.map((marker) => ({
      ...marker,
      name: `${getRouteTabLabel(route, routeIndex)} · ${marker.name}`,
    })),
  ).map((marker, index) => ({ ...marker, order: index + 1 }))

  const polyline = routes.flatMap((route) => route.polyline)
  const points = [
    ...polyline,
    ...markers.map((marker) => [marker.lng, marker.lat] as [number, number]),
  ]

  return {
    type: 'route',
    route_name: '总路线',
    mode: routes[0]?.mode ?? 'driving',
    markers,
    polyline,
    bounds: computeBounds(points),
    summary: {
      distance_km: Number(routes.reduce((sum, route) => sum + (route.summary.distance_km || 0), 0).toFixed(2)),
      duration_min: routes.reduce((sum, route) => sum + (route.summary.duration_min || 0), 0),
      cost_yuan: sumNullable(routes.map((route) => route.summary.cost_yuan)),
    },
  }
}

function computeBounds(points: Array<[number, number]>): MapPayload['bounds'] {
  if (points.length === 0) return null
  const lngs = points.map((point) => point[0])
  const lats = points.map((point) => point[1])
  return {
    sw: [Math.min(...lngs), Math.min(...lats)],
    ne: [Math.max(...lngs), Math.max(...lats)],
  }
}

function sumNullable(values: Array<number | null | undefined>) {
  const nums = values.filter((value): value is number => typeof value === 'number')
  if (nums.length === 0) return null
  return Number(nums.reduce((sum, value) => sum + value, 0).toFixed(2))
}

function injectScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`) as HTMLScriptElement | null
    if (existing) {
      if (existing.dataset.loaded === 'true') {
        resolve()
        return
      }
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('script load failed')))
      return
    }
    const el = document.createElement('script')
    el.src = src
    el.async = true
    el.dataset.loaded = 'false'
    el.addEventListener('load', () => {
      el.dataset.loaded = 'true'
      resolve()
    })
    el.addEventListener('error', () => reject(new Error('script load failed')))
    document.head.appendChild(el)
  })
}
