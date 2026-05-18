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
import AMapLoader from '@amap/amap-jsapi-loader'
import { Compass, Loader2, MapPin, Navigation, RefreshCcw, Sparkles } from 'lucide-react'
import type { MapPayload } from '../types'

const AMAP_JS_KEY = import.meta.env.VITE_AMAP_JS_KEY ?? ''
const AMAP_SECURITY_CODE = import.meta.env.VITE_AMAP_SECURITY_JS_CODE ?? ''
const AMAP_VERSION = '2.0'
const AMAP_PLUGINS = 'AMap.Polyline,AMap.Marker'
const OVERVIEW_COLOR = '#2F2A25'
const ROUTE_COLORS = ['#B98D68', '#65735D', '#5876A6', '#A86F7A', '#7D6CA8', '#B59B48']
const MAP_STYLE = 'amap://styles/whitesmoke'
const MAP_FEATURES = ['bg', 'road', 'point', 'building']

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

const MAP_PADDING: [number, number, number, number] = [60, 60, 60, 60]

const MapPanel = forwardRef<MapPanelHandle, MapPanelProps>(({ routes = [] }, ref) => {
  const [route, setRoute] = useState<MapPayload | null>(null)
  const [activeRouteIndex, setActiveRouteIndex] = useState(-1)
  const [amap, setAmap] = useState<AMapState>({ stage: 'idle' })
  const [mapNotice, setMapNotice] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const amapRef = useRef<any>(null)
  const mapInstanceRef = useRef<any>(null)
  const mapContainerRef = useRef<HTMLElement | null>(null)
  const baseLayerRef = useRef<any>(null)
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
    if (amapRef.current) {
      setAmap({ stage: 'ready' })
      return
    }
    setAmap({ stage: 'loading' })
    try {
      if (AMAP_SECURITY_CODE) {
        window._AMapSecurityConfig = { securityJsCode: AMAP_SECURITY_CODE }
      }
      amapRef.current = await AMapLoader.load({
        key: AMAP_JS_KEY,
        version: AMAP_VERSION,
        plugins: AMAP_PLUGINS.split(','),
      })
      setAmap({ stage: 'ready' })
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
    const container = containerRef.current
    if (!container || !route) return
    const AMap = amapRef.current || window.AMap
    if (!AMap) return
    if (!hasLayoutSize(container)) {
      const timer = window.setTimeout(() => setRoute((current) => (current ? { ...current } : current)), 40)
      return () => window.clearTimeout(timer)
    }

    if (mapInstanceRef.current && mapContainerRef.current !== container) {
      mapInstanceRef.current.destroy?.()
      mapInstanceRef.current = null
      baseLayerRef.current = null
      overlayRef.current = []
    }

    if (!mapInstanceRef.current) {
      baseLayerRef.current = AMap.createDefaultLayer({
        zooms: [3, 20],
        zIndex: 1,
        opacity: 1,
        visible: true,
      })
      mapInstanceRef.current = new AMap.Map(container, {
        zoom: 11,
        viewMode: '2D',
        layers: baseLayerRef.current ? [baseLayerRef.current] : undefined,
        mapStyle: MAP_STYLE,
        features: MAP_FEATURES,
      })
      mapContainerRef.current = container
      mapInstanceRef.current.on?.('complete', () => setMapNotice(null))
      mapInstanceRef.current.on?.('error', (event: unknown) => {
        console.error('[MapPanel] AMap map error', event)
        setMapNotice('高德底图资源加载失败，请检查 Web(JS API) Key、安全密钥和 Referer 白名单。')
      })
    }
    const map = mapInstanceRef.current
    map.setMapStyle?.(MAP_STYLE)
    map.setFeatures?.(MAP_FEATURES)
    if (baseLayerRef.current) {
      baseLayerRef.current.show?.()
      map.setLayers?.([baseLayerRef.current])
    }
    debugAmapLayerState(container, map, baseLayerRef.current)
    const noticeTimer = window.setTimeout(() => {
      if (hasVisibleBaseTexture(container)) return
      setMapNotice('路线已绘制，但底图纹理没有加载成功。通常是高德 Key / 安全密钥 / Referer 白名单或网络拦截导致。')
    }, 3500)
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

    fitRouteView(map, AMap, route, markers)
    const timers = [0, 80, 240].map((delay) =>
      window.setTimeout(() => fitRouteView(map, AMap, route, markers), delay),
    )
    return () => {
      window.clearTimeout(noticeTimer)
      timers.forEach((timer) => window.clearTimeout(timer))
    }
  }, [amap.stage, route, activeRouteIndex])

  useEffect(() => {
    if (route || !mapInstanceRef.current) return
    mapInstanceRef.current.destroy?.()
    mapInstanceRef.current = null
    baseLayerRef.current = null
    mapContainerRef.current = null
    overlayRef.current = []
  }, [route])

  useEffect(() => {
    if (amap.stage !== 'ready' || !mapInstanceRef.current) return
    const resize = () => {
      mapInstanceRef.current?.resize?.()
      if (route) fitRouteView(mapInstanceRef.current, window.AMap, route, overlayRef.current)
    }
    const observer = containerRef.current ? new ResizeObserver(() => requestAnimationFrame(resize)) : null
    if (containerRef.current && observer) observer.observe(containerRef.current)
    window.addEventListener('resize', resize)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', resize)
    }
  }, [amap.stage, route])

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
          <>
            <div ref={containerRef} className="amap-container absolute inset-0 h-full w-full" />
            {mapNotice && (
              <div className="absolute left-3 right-3 top-3 z-20 rounded-2xl border border-amber-200 bg-paper/95 px-3 py-2 text-xs leading-5 text-ink shadow-quiet backdrop-blur">
                {mapNotice}
              </div>
            )}
          </>
        )}

        {route && amap.stage === 'error' && <FallbackSvg route={route} reason={normalizeAmapError(amap.reason)} color={activeRouteIndex < 0 ? OVERVIEW_COLOR : ROUTE_COLORS[activeRouteIndex % ROUTE_COLORS.length]} />}
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
  const guideRoads = [
    `M 18 76 C 96 42, 154 104, 226 66 S 318 72, 348 42`,
    `M 28 252 C 86 214, 136 238, 190 196 S 276 168, 344 194`,
    `M 72 18 C 90 82, 74 142, 112 190 S 156 254, 144 308`,
    `M 250 24 C 232 92, 286 134, 260 202 S 272 276, 324 316`,
  ]
  const placeLabels = route.markers.slice(0, 6)

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
          <rect x="0" y="0" width={W} height={H} fill="#FCFBF8" />
          <defs>
            <pattern id="map-grid" width="32" height="32" patternUnits="userSpaceOnUse">
              <path d="M 32 0 L 0 0 0 32" fill="none" stroke="#E7E0D5" strokeWidth="0.8" opacity="0.55" />
            </pattern>
          </defs>
          <rect x="0" y="0" width={W} height={H} fill="url(#map-grid)" />
          {guideRoads.map((road, index) => (
            <path
              key={index}
              d={road}
              fill="none"
              stroke={index % 2 ? '#DCCAB8' : '#D4DDD0'}
              strokeWidth={index % 2 ? 7 : 9}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={0.55}
            />
          ))}
          {placeLabels.map((m, index) => {
            const px = 24 + ((index * 67) % 300)
            const py = 42 + ((index * 49) % 230)
            return (
              <text key={`${m.order}-label`} x={px} y={py} fontSize={10} fill="#9A8D7E" opacity={0.72}>
                {m.name}
              </text>
            )
          })}
          <path d={pathD} fill="none" stroke="#FCFBF8" strokeWidth={9} strokeLinecap="round" strokeLinejoin="round" opacity={0.9} />
          <path d={pathD} fill="none" stroke={color} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" opacity={0.82} />
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

function hasLayoutSize(el: HTMLElement) {
  return el.clientWidth > 0 && el.clientHeight > 0
}

function fitRouteView(map: any, AMap: any, route: MapPayload, overlays: any[]) {
  if (!map || !AMap) return
  map.resize?.()
  if (route.bounds) {
    const sw = new AMap.LngLat(route.bounds.sw[0], route.bounds.sw[1])
    const ne = new AMap.LngLat(route.bounds.ne[0], route.bounds.ne[1])
    map.setBounds(new AMap.Bounds(sw, ne), false, MAP_PADDING)
    return
  }
  const markers = overlays.filter((overlay) => typeof overlay?.getPosition === 'function')
  if (markers.length > 0) {
    map.setFitView(markers, false, MAP_PADDING)
  }
}

function debugAmapLayerState(container: HTMLElement, map: any, baseLayer: any) {
  if (!import.meta.env.DEV) return
  window.setTimeout(() => {
    const rect = container.getBoundingClientRect()
    const canvasCount = container.querySelectorAll('canvas').length
    const imageCount = container.querySelectorAll('img').length
    const layerClasses = Array.from(container.querySelectorAll('[class*="amap"]'))
      .slice(0, 12)
      .map((el) => (el as HTMLElement).className)
    console.info('[MapPanel] AMap layer state', {
      rect: { width: rect.width, height: rect.height },
      zoom: map.getZoom?.(),
      center: map.getCenter?.()?.toString?.(),
      features: MAP_FEATURES,
      baseLayer: Boolean(baseLayer),
      canvasCount,
      imageCount,
      layerClasses,
    })
  }, 800)
}

function hasVisibleBaseTexture(container: HTMLElement) {
  const canvas = Array.from(container.querySelectorAll('canvas')).find((item) => {
    const rect = item.getBoundingClientRect()
    return rect.width > 64 && rect.height > 64
  })
  if (canvas && hasPaintedCanvas(canvas)) return true
  return Array.from(container.querySelectorAll('img')).some((img) => {
    const rect = img.getBoundingClientRect()
    const src = img.currentSrc || img.src
    return rect.width > 32 && rect.height > 32 && img.complete && img.naturalWidth > 0 && /amap|autonavi/i.test(src)
  })
}

function hasPaintedCanvas(canvas: HTMLCanvasElement) {
  if (canvas.width === 0 || canvas.height === 0) return false
  const sampleX = Math.floor(canvas.width / 2)
  const sampleY = Math.floor(canvas.height / 2)
  const twoDimensional = read2dCanvasPixel(canvas, sampleX, sampleY)
  if (twoDimensional) return true
  return readWebglCanvasPixel(canvas, sampleX, sampleY)
}

function read2dCanvasPixel(canvas: HTMLCanvasElement, x: number, y: number) {
  try {
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx) return false
    const data = ctx.getImageData(x, y, 1, 1).data
    return data[3] !== 0
  } catch {
    return false
  }
}

function readWebglCanvasPixel(canvas: HTMLCanvasElement, x: number, y: number) {
  const contexts = ['webgl2', 'webgl', 'experimental-webgl'] as const
  for (const name of contexts) {
    try {
      const gl = canvas.getContext(name, { preserveDrawingBuffer: true }) as WebGLRenderingContext | WebGL2RenderingContext | null
      if (!gl) continue
      const pixel = new Uint8Array(4)
      gl.readPixels(x, y, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel)
      if (pixel[3] !== 0) return true
    } catch {
      // AMap owns the WebGL context; keep trying the remaining context names.
    }
  }
  return false
}

function normalizeAmapError(reason: string) {
  if (!reason) return '高德地图脚本加载失败，使用草图模式'
  if (reason === 'no-key') return reason
  if (/security|jscode|key|invalid|permission|forbidden|unauthorized|403|401/i.test(reason)) {
    return `高德地图鉴权失败：${reason}`
  }
  return reason
}

function sumNullable(values: Array<number | null | undefined>) {
  const nums = values.filter((value): value is number => typeof value === 'number')
  if (nums.length === 0) return null
  return Number(nums.reduce((sum, value) => sum + value, 0).toFixed(2))
}
