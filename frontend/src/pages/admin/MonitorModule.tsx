import { Activity, BarChart3, ExternalLink, Gauge, HeartPulse } from 'lucide-react'
import { ModuleCard, SoftButton } from './shared'

const grafanaUrl =
  import.meta.env.VITE_GRAFANA_DASHBOARD_URL ??
  'http://localhost:3000/d/travel-any-overview/travel-any-observability?orgId=1&refresh=10s&theme=light&kiosk=tv'

const prometheusUrl = import.meta.env.VITE_PROMETHEUS_URL ?? 'http://localhost:9090'

export default function MonitorModule() {
  return (
    <ModuleCard
      title="监控大盘"
      desc="把 FastAPI 健康度、HTTP 延迟、请求吞吐和大模型 Token 消耗收拢在同一块运维视图里。"
      icon={<Activity size={20} />}
      actions={
        <div className="flex flex-wrap gap-2">
          <SoftButton onClick={() => window.open(prometheusUrl, '_blank', 'noopener,noreferrer')}>
            <ExternalLink size={15} />
            Prometheus
          </SoftButton>
          <SoftButton tone="primary" onClick={() => window.open(grafanaUrl, '_blank', 'noopener,noreferrer')}>
            <ExternalLink size={15} />
            Grafana
          </SoftButton>
        </div>
      }
    >
      <div className="grid gap-3 md:grid-cols-3">
        <MetricPill icon={<HeartPulse size={16} />} label="API Health" value="/metrics" />
        <MetricPill icon={<Gauge size={16} />} label="Latency" value="p50 / p95 / p99" />
        <MetricPill icon={<BarChart3 size={16} />} label="LLM Tokens" value="prompt / completion" />
      </div>

      <section className="mt-5 overflow-hidden rounded-4xl border border-line/70 bg-[#F8F6F1] p-2 shadow-quiet">
        <div className="overflow-hidden rounded-[1.65rem] bg-paper">
          <iframe
            title="Grafana 监控大盘"
            src={grafanaUrl}
            className="h-[720px] w-full border-0 bg-paper"
            loading="lazy"
            referrerPolicy="no-referrer"
          />
        </div>
      </section>

      <p className="mt-4 rounded-3xl bg-[#F8F6F1] px-4 py-3 text-xs leading-5 text-muted">
        默认嵌入地址可通过 <code>VITE_GRAFANA_DASHBOARD_URL</code> 覆盖；当前 URL 已带 <code>kiosk=tv</code> 和 light theme，
        用于隐藏 Grafana 顶栏/侧栏并保持与控制台视觉一致。
      </p>
    </ModuleCard>
  )
}

function MetricPill({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-3xl bg-[#F8F6F1] px-4 py-3">
      <div className="mb-2 flex items-center gap-2 text-muted">
        {icon}
        <span className="text-xs font-medium uppercase tracking-[0.08em]">{label}</span>
      </div>
      <p className="truncate text-sm font-semibold text-ink">{value}</p>
    </div>
  )
}
