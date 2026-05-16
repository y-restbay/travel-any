import { useEffect, useRef, useState } from 'react'
import {
  Activity,
  BarChart3,
  ExternalLink,
  Gauge,
  HeartPulse,
  Maximize2,
  Minimize2,
  PanelTop,
  ScanSearch,
  Table2,
} from 'lucide-react'
import { motion } from 'framer-motion'
import { SoftButton } from './shared'

const grafanaBaseUrl =
  import.meta.env.VITE_GRAFANA_DASHBOARD_URL ??
  'http://localhost:3000/d/travel-any-overview/travel-any-observability?orgId=1&refresh=10s&theme=light&kiosk=tv'

const prometheusUrl = import.meta.env.VITE_PROMETHEUS_URL ?? 'http://localhost:9090'

type PanelCard = {
  id: number
  title: string
  value: string
  detail: string
  icon: React.ReactNode
  tone: 'clay' | 'sage' | 'sand'
}

const panelCards: PanelCard[] = [
  {
    id: 1,
    title: '接口吞吐',
    value: 'req/s',
    detail: '看最近一分钟内各个接口的请求流量，适合判断高峰期是否异常放大。',
    icon: <HeartPulse size={17} />,
    tone: 'clay',
  },
  {
    id: 2,
    title: '接口延迟',
    value: 'p95 秒级',
    detail: '看 p95 响应耗时，比平均值更能反映大多数用户当下的真实体感。',
    icon: <Gauge size={17} />,
    tone: 'sage',
  },
  {
    id: 3,
    title: 'Token 消耗',
    value: '5 分钟增量',
    detail: '看 prompt / completion 的近期增量，判断当前会话是否出现异常消耗。',
    icon: <BarChart3 size={17} />,
    tone: 'sand',
  },
  {
    id: 4,
    title: '模型耗时',
    value: '平均时长',
    detail: '看每个模型最近 5 分钟的平均请求时长，方便对比不同运行时的稳定性。',
    icon: <ScanSearch size={17} />,
    tone: 'sage',
  },
  {
    id: 5,
    title: '模型请求速率',
    value: 'req/s',
    detail: '看不同模型或运行时的调用频率，帮助判断哪条链路在持续承压。',
    icon: <Activity size={17} />,
    tone: 'clay',
  },
]

const colorTone = {
  clay: 'bg-clay/35 text-clayDeep',
  sage: 'bg-sage text-moss',
  sand: 'bg-[#F2ECE2] text-ink',
}

const opsTableRows = [
  {
    metric: '接口错误率',
    promql: 'sum(rate(http_requests_total{status=~"5.."}[5m]))',
    threshold: '< 1%',
    action: '优先查看后端日志、最近一次发布和异常接口路径。',
  },
  {
    metric: '接口 p95 延迟',
    promql: 'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))',
    threshold: '< 2s',
    action: '排查慢工具、外部 API、数据库连接和 SSE 阻塞。',
  },
  {
    metric: 'LLM 请求耗时',
    promql: 'rate(wanderbot_llm_request_duration_seconds_sum[5m]) / rate(wanderbot_llm_request_duration_seconds_count[5m])',
    threshold: '< 20s',
    action: '确认模型供应商、上下文长度、工具轮次和流式返回状态。',
  },
  {
    metric: 'Token 消耗增量',
    promql: 'increase(wanderbot_llm_token_usage_total[5m])',
    threshold: '按预算波动',
    action: '检查提示词膨胀、历史上下文过长和工具结果是否被完整注入。',
  },
  {
    metric: '运行中请求数',
    promql: 'http_requests_inprogress',
    threshold: '无持续堆积',
    action: '如果持续上升，检查前端重试、SSE 断连和后端 worker 数量。',
  },
]

function buildPanelUrl(panelId: number) {
  const url = new URL(grafanaBaseUrl)
  const uid = url.pathname.split('/')[2] ?? 'travel-any-overview'
  const slug = url.pathname.split('/')[3] ?? 'travel-any-observability'
  const from = url.searchParams.get('from') ?? 'now-30m'
  const to = url.searchParams.get('to') ?? 'now'
  const refresh = url.searchParams.get('refresh') ?? '10s'
  const theme = url.searchParams.get('theme') ?? 'light'
  const orgId = url.searchParams.get('orgId') ?? '1'

  return `${url.origin}/d-solo/${uid}/${slug}?orgId=${orgId}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&refresh=${encodeURIComponent(refresh)}&theme=${encodeURIComponent(theme)}&panelId=${panelId}&kiosk=tv`
}

export default function MonitorModule() {
  const shellRef = useRef<HTMLDivElement | null>(null)
  const [focusedPanelId, setFocusedPanelId] = useState<number | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)

  useEffect(() => {
    function handleFullscreenChange() {
      setIsFullscreen(document.fullscreenElement === shellRef.current)
    }

    document.addEventListener('fullscreenchange', handleFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange)
  }, [])

  async function toggleFullscreen() {
    if (!document.fullscreenEnabled || !shellRef.current) return

    if (document.fullscreenElement === shellRef.current) {
      await document.exitFullscreen()
      return
    }

    await shellRef.current.requestFullscreen()
  }

  const activePanel = panelCards.find((item) => item.id === focusedPanelId) ?? null
  const visiblePanels = activePanel ? [activePanel] : panelCards

  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22 }}
      data-testid="monitor-module"
      className="w-full max-w-none rounded-[2rem] bg-paper/90 p-3 shadow-soft backdrop-blur md:p-4"
    >
      <div className="mb-4 flex flex-col gap-4 px-1 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-3xl bg-sage text-moss">
            <Activity size={20} />
          </span>
          <div>
            <h2 className="text-lg font-semibold">监控大盘</h2>
            <p className="mt-1 max-w-5xl text-sm leading-6 text-muted">
              把接口稳定性、模型吞吐和 Token 消耗收拢在一个运维视图里，当前页面已使用全宽布局，方便查看坐标轴和曲线细节。
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <SoftButton onClick={() => window.open(prometheusUrl, '_blank', 'noopener,noreferrer')}>
            <ExternalLink size={15} />
            Prometheus
          </SoftButton>
          <SoftButton onClick={() => window.open(grafanaBaseUrl, '_blank', 'noopener,noreferrer')}>
            <ExternalLink size={15} />
            打开 Grafana
          </SoftButton>
          <SoftButton tone="primary" onClick={() => void toggleFullscreen()}>
            {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
            {isFullscreen ? '退出全屏' : '全屏查看'}
          </SoftButton>
        </div>
      </div>

      <div className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3">
          <MetricPill
            icon={<HeartPulse size={16} />}
            label="监控入口"
            value="/metrics"
            desc="FastAPI 已暴露 Prometheus 指标端点。"
          />
          <MetricPill
            icon={<Gauge size={16} />}
            label="刷新频率"
            value="10 秒"
            desc="Grafana 大盘默认每 10 秒刷新一次。"
          />
          <MetricPill
            icon={<BarChart3 size={16} />}
            label="当前视图"
            value={activePanel ? activePanel.title : '总览模式'}
            desc={activePanel ? '当前只放大一个图表，便于排查细节。' : '当前展示完整运维总览。'}
          />
        </div>

        <div className="rounded-[1.8rem] border border-line/70 bg-[#F8F6F1] p-2 shadow-quiet md:p-3">
          <div
            ref={shellRef}
            data-testid="monitor-shell"
            className={`max-w-none overflow-hidden bg-paper ${
              isFullscreen
                ? 'fixed inset-0 z-[300] h-screen w-screen rounded-none border-0'
                : 'rounded-[1.7rem] border border-line/70'
            }`}
          >
            <div className="flex min-h-[72px] flex-wrap items-center justify-between gap-3 border-b border-line/60 bg-[#FBF8F3] px-4 py-3 md:px-5">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-medium text-ink">
                  <PanelTop size={16} />
                  {activePanel ? `单图聚焦：${activePanel.title}` : '运维总览'}
                </div>
                <p className="mt-1 max-w-4xl text-xs leading-5 text-muted">
                  {activePanel
                    ? `${activePanel.detail} 点击“查看总览”返回全部面板。`
                    : '管理端以 Grafana 单面板方式展示，避免完整 Grafana 导航栏占用空间；全屏时会保留同一套面板网格。'}
                </p>
              </div>

              <div className="flex flex-wrap gap-2">
                {activePanel && (
                  <SoftButton onClick={() => setFocusedPanelId(null)}>
                    <PanelTop size={15} />
                    查看总览
                  </SoftButton>
                )}
                <SoftButton onClick={() => void toggleFullscreen()} tone={isFullscreen ? 'quiet' : 'primary'}>
                  {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
                  {isFullscreen ? '退出全屏' : '放大大盘'}
                </SoftButton>
              </div>
            </div>

            <div
              className={`soft-scrollbar bg-paper ${
                isFullscreen ? 'h-[calc(100vh-72px)] overflow-y-auto px-3 py-3 md:px-5 md:py-4' : 'p-2 md:p-3'
              }`}
            >
              <div
                className={
                  activePanel
                    ? 'grid w-full max-w-none gap-3'
                    : isFullscreen
                      ? 'grid w-full max-w-none grid-cols-1 gap-4 xl:grid-cols-2'
                      : 'grid w-full max-w-none grid-cols-1 gap-4 xl:grid-cols-2'
                }
              >
                {visiblePanels.map((panel) => (
                  <GrafanaPanel
                    key={panel.id}
                    panel={panel}
                    focused={Boolean(activePanel)}
                    fullscreen={isFullscreen}
                    onFocus={() => setFocusedPanelId(panel.id)}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
          {panelCards.map((item) => {
            const active = item.id === focusedPanelId
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setFocusedPanelId(active ? null : item.id)}
                className={`w-full rounded-3xl border px-3 py-3 text-left transition ${
                  active
                    ? 'border-ink/10 bg-paper shadow-soft'
                    : 'border-line/70 bg-[#F8F6F1] hover:border-clay/60 hover:bg-paper'
                }`}
              >
                <div className="flex items-start gap-2.5">
                  <span className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-2xl ${colorTone[item.tone]}`}>
                    {item.icon}
                  </span>
                  <div className="min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold text-ink">{item.title}</h3>
                      <span className="shrink-0 rounded-full bg-[#F4EFE7] px-2 py-0.5 text-[10px] font-medium text-muted">
                        Panel {item.id}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-muted">{item.value}</p>
                    <p className="mt-1 text-[11px] leading-4 text-muted">{item.detail}</p>
                  </div>
                </div>
              </button>
            )
          })}

          <div className="rounded-3xl border border-line/70 bg-[#F8F6F1] px-4 py-3 md:col-span-2 xl:col-span-5">
            <p className="text-sm font-medium text-ink">读图建议</p>
            <div className="mt-2 grid gap-2 text-[11px] leading-4 text-muted md:grid-cols-3">
              <p>接口吞吐用于看访问量是否突然抬升，尤其适合排查工具调用风暴。</p>
              <p>接口延迟建议优先看 p95，而不是只看平均值。</p>
              <p>Token 消耗能快速发现提示词膨胀、上下文过长或模型切换后的成本变化。</p>
            </div>
          </div>
        </div>

        <section className="overflow-hidden rounded-[1.8rem] border border-line/70 bg-paper shadow-quiet">
          <div className="flex flex-col gap-2 border-b border-line/60 bg-[#FBF8F3] px-4 py-3 md:flex-row md:items-center md:justify-between md:px-5">
            <div className="flex items-center gap-2">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-2xl bg-sage text-moss">
                <Table2 size={17} />
              </span>
              <div>
                <h3 className="text-sm font-semibold text-ink">运维指标速查表</h3>
                <p className="mt-0.5 text-xs text-muted">把常用 PromQL、健康阈值和排查动作放在一起，方便值班时快速定位。</p>
              </div>
            </div>
            <span className="w-fit rounded-full bg-[#F4EFE7] px-3 py-1 text-[11px] font-medium text-muted">
              SRE Runbook
            </span>
          </div>

          <div className="soft-scrollbar overflow-x-auto">
            <table className="min-w-[920px] w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-line/60 bg-[#F8F6F1] text-xs font-medium text-muted">
                  <th className="px-5 py-3">指标</th>
                  <th className="px-5 py-3">PromQL</th>
                  <th className="px-5 py-3">健康阈值</th>
                  <th className="px-5 py-3">异常排查动作</th>
                </tr>
              </thead>
              <tbody>
                {opsTableRows.map((row) => (
                  <tr key={row.metric} className="border-b border-line/50 last:border-0">
                    <td className="whitespace-nowrap px-5 py-4 font-medium text-ink">{row.metric}</td>
                    <td className="px-5 py-4">
                      <code className="rounded-2xl bg-[#F8F6F1] px-2 py-1 text-[11px] leading-5 text-muted">
                        {row.promql}
                      </code>
                    </td>
                    <td className="whitespace-nowrap px-5 py-4 text-ink">{row.threshold}</td>
                    <td className="px-5 py-4 text-sm leading-6 text-muted">{row.action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </motion.section>
  )
}

function GrafanaPanel({
  panel,
  focused,
  fullscreen,
  onFocus,
}: {
  panel: PanelCard
  focused: boolean
  fullscreen: boolean
  onFocus: () => void
}) {
  const heightClass = focused
    ? fullscreen
      ? 'h-[calc(100vh-132px)]'
      : 'h-[720px]'
    : fullscreen
      ? 'h-[420px]'
      : panel.id === 5
        ? 'h-[440px]'
        : 'h-[420px]'

  return (
    <section className="min-w-0 overflow-hidden rounded-3xl border border-line/70 bg-paper">
      <div className="flex items-center justify-between gap-3 border-b border-line/60 bg-[#FBF8F3] px-4 py-2.5">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{panel.title}</p>
          <p className="truncate text-[11px] text-muted">{panel.value}</p>
        </div>
        {!focused && (
          <button
            type="button"
            onClick={onFocus}
            className="shrink-0 rounded-2xl bg-[#F4EFE7] px-3 py-1.5 text-xs font-medium text-muted transition hover:bg-clay/35 hover:text-ink"
          >
            聚焦
          </button>
        )}
      </div>
      <iframe
        title={`${panel.title} 图表`}
        data-testid="grafana-panel-frame"
        src={buildPanelUrl(panel.id)}
        className={`w-full border-0 bg-paper ${heightClass}`}
        loading="lazy"
        referrerPolicy="no-referrer"
        allow="fullscreen"
      />
    </section>
  )
}

function MetricPill({
  icon,
  label,
  value,
  desc,
}: {
  icon: React.ReactNode
  label: string
  value: string
  desc: string
}) {
  return (
    <div className="rounded-3xl border border-line/70 bg-[#F8F6F1] px-4 py-4">
      <div className="mb-2 flex items-center gap-2 text-muted">
        {icon}
        <span className="text-xs font-medium tracking-[0.08em]">{label}</span>
      </div>
      <p className="text-base font-semibold text-ink">{value}</p>
      <p className="mt-2 text-xs leading-5 text-muted">{desc}</p>
    </div>
  )
}
