/**
 * LogsModule:系统运行日志查看。
 *
 * 数据来自后端进程内环形缓冲(GET /api/admin/logs):
 * - 提问 / 回答完成 / 回答异常(app.chat)
 * - 各工具的 warning / exception(联网、地图、天气、导出等)
 * 进程重启即清空,这是运行日志查看器而非审计库。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, Pause, Play, RefreshCw, ScrollText, Trash2 } from 'lucide-react'
import { clearSystemLogs, downloadSystemLogs, getSystemLogs } from '../../api'
import type { SystemLogEntry } from '../../types'
import { EmptyState, InlineNotice, LoadingState, ModuleCard, SoftButton } from './shared'

const LEVELS = ['ALL', 'INFO', 'WARNING', 'ERROR'] as const
const REFRESH_MS = 5000

const LEVEL_STYLE: Record<string, string> = {
  DEBUG: 'bg-[#F8F6F1] text-muted',
  INFO: 'bg-sage/40 text-moss',
  WARNING: 'bg-amber-100 text-amber-800',
  ERROR: 'bg-red-100 text-red-700',
  CRITICAL: 'bg-red-200 text-red-800',
}

function fmtTime(ts: number): string {
  const d = new Date(ts * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

export default function LogsModule() {
  const [logs, setLogs] = useState<SystemLogEntry[]>([])
  const [level, setLevel] = useState<string>('ALL')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(true)
  // 过滤条件用 ref 给定时器读取，避免把 interval 写进依赖反复重建。
  const filterRef = useRef({ level, query })
  filterRef.current = { level, query }

  const load = useCallback(async () => {
    try {
      const { level: lv, query: q } = filterRef.current
      const data = await getSystemLogs({ level: lv, q: q.trim(), limit: 300 })
      setLogs(data)
      setError('')
    } catch {
      setError('无法加载日志，请确认后端服务在线。')
    } finally {
      setLoading(false)
    }
  }, [])

  // 过滤条件变化:300ms 防抖后拉取。
  useEffect(() => {
    const t = window.setTimeout(load, 300)
    return () => window.clearTimeout(t)
  }, [level, query, load])

  // 自动刷新。
  useEffect(() => {
    if (!autoRefresh) return
    const timer = window.setInterval(load, REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [autoRefresh, load])

  async function handleExport() {
    const blob = await downloadSystemLogs({ level, q: query.trim() })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `wanderbot-logs-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '')}.log`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  async function handleClear() {
    if (!window.confirm('确定清空当前所有运行日志？此操作不可恢复。')) return
    try {
      await clearSystemLogs()
      await load()
    } catch {
      setError('清空失败，请重试。')
    }
  }

  return (
    <ModuleCard
      title="日志管理"
      desc="系统运行日志：用户提问、回答完成 / 异常，以及联网、地图、天气、导出等工具的报错。进程内最近 1000 条，重启清空。"
      icon={<ScrollText size={18} />}
      actions={
        <div className="flex gap-2">
          <SoftButton
            tone={autoRefresh ? 'success' : 'quiet'}
            onClick={() => setAutoRefresh((v) => !v)}
          >
            {autoRefresh ? <Pause size={15} /> : <Play size={15} />}
            {autoRefresh ? '自动刷新' : '已暂停'}
          </SoftButton>
          <SoftButton tone="quiet" onClick={load}>
            <RefreshCw size={15} />
            刷新
          </SoftButton>
          <SoftButton tone="quiet" onClick={handleExport}>
            <Download size={15} />
            导出
          </SoftButton>
          <SoftButton tone="danger" onClick={handleClear}>
            <Trash2 size={15} />
            清空
          </SoftButton>
        </div>
      }
    >
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="flex gap-1.5">
          {LEVELS.map((lv) => (
            <button
              key={lv}
              type="button"
              onClick={() => setLevel(lv)}
              className={`rounded-2xl px-3 py-1.5 text-xs font-medium transition ${
                level === lv
                  ? 'bg-ink text-paper shadow-quiet'
                  : 'bg-[#F8F6F1] text-muted hover:bg-clay/40 hover:text-ink'
              }`}
            >
              {lv === 'ALL' ? '全部' : lv}
            </button>
          ))}
        </div>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索消息或来源（如 amap、提问、导出失败）"
          className="input flex-1"
        />
      </div>

      {error && (
        <div className="mb-4">
          <InlineNotice tone="error">{error}</InlineNotice>
        </div>
      )}

      {loading ? (
        <LoadingState label="加载日志中..." />
      ) : logs.length === 0 ? (
        <EmptyState>暂无符合条件的日志。发起一次对话或调用工具后再回来看看。</EmptyState>
      ) : (
        <div className="soft-scrollbar max-h-[60vh] overflow-y-auto rounded-3xl border border-line/60 bg-[#FBFAF6]">
          <ul className="divide-y divide-line/40">
            {logs.map((log) => (
              <li key={log.id} className="px-4 py-2.5 text-xs">
                <div className="flex items-center gap-2">
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                      LEVEL_STYLE[log.level] ?? 'bg-[#F8F6F1] text-muted'
                    }`}
                  >
                    {log.level}
                  </span>
                  <span className="shrink-0 font-mono text-[11px] text-muted">{fmtTime(log.ts)}</span>
                  <span className="truncate font-mono text-[11px] text-muted/70" title={log.logger}>
                    {log.logger}
                  </span>
                </div>
                <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-ink">
                  {log.message}
                </pre>
              </li>
            ))}
          </ul>
        </div>
      )}
    </ModuleCard>
  )
}
