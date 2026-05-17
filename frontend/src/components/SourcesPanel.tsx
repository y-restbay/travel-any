/**
 * SourcesPanel:联网搜索的可点击来源卡。
 *
 * - 渲染在 AI 回答下方;每张卡 id="wb-src-<msgId>-<n>",
 *   答案正文里的 [n] 点击后由 App.tsx 滚动并高亮对应卡。
 * - status=failed/empty 时给一行降级提示,不渲染卡片。
 */
import { useEffect, useState } from 'react'
import { ChevronDown, ExternalLink, Globe } from 'lucide-react'
import type { WebSourceBundle } from '../types'

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

export default function SourcesPanel({
  messageId,
  bundle,
}: {
  messageId: string
  bundle: WebSourceBundle
}) {
  // 来源列表默认折叠,用户点标题栏才展开。
  const [expanded, setExpanded] = useState(false)

  // 正文里的 [n] 角标被点击时,scrollToCitation 派发此事件,
  // 命中本条消息则自动展开,保证引用能跳转到对应来源卡。
  useEffect(() => {
    function onJump(e: Event) {
      const detail = (e as CustomEvent<{ messageId: string }>).detail
      if (detail?.messageId === messageId) setExpanded(true)
    }
    window.addEventListener('wb-cite-jump', onJump)
    return () => window.removeEventListener('wb-cite-jump', onJump)
  }, [messageId])

  if (bundle.status !== 'success' || bundle.sources.length === 0) {
    return (
      <div className="mt-3 flex items-center gap-2 rounded-2xl border border-line/60 bg-canvas/40 px-3 py-2 text-[11px] text-muted">
        <Globe size={13} />
        {bundle.status === 'failed'
          ? `联网检索失败：${bundle.reason || '服务暂不可用'}，本回答基于已有知识。`
          : '本轮未检索到相关网页，回答基于已有知识。'}
      </div>
    )
  }

  return (
    <section className="mt-3 overflow-hidden rounded-2xl border border-line/60 bg-paper/70">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className={`flex w-full items-center gap-2 px-3 py-2 text-[12px] font-medium text-ink transition-colors hover:bg-canvas/40 ${
          expanded ? 'border-b border-line/50' : ''
        }`}
      >
        <Globe size={13} className="text-clayDeep" />
        联网来源 · {bundle.sources.length} 条
        <ChevronDown
          size={14}
          className={`ml-auto shrink-0 text-muted transition-transform ${expanded ? 'rotate-180' : ''}`}
        />
      </button>
      {expanded && (
        <ol className="divide-y divide-line/40">
          {bundle.sources.map((s) => (
          <li
            key={s.n}
            id={`wb-src-${messageId}-${s.n}`}
            className="scroll-mt-24 px-3 py-2.5 transition-colors"
          >
            <div className="flex items-start gap-2">
              <span className="mt-0.5 grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-clay/60 px-1 text-[11px] font-medium text-clayDeep">
                {s.n}
              </span>
              <div className="min-w-0 flex-1">
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[13px] font-medium text-ink hover:text-clayDeep"
                >
                  <span className="truncate">{s.title}</span>
                  <ExternalLink size={11} className="shrink-0 text-muted" />
                </a>
                <div className="mt-0.5 truncate text-[11px] text-muted/80">
                  {hostOf(s.url)}
                  {s.published && s.published !== '未知' ? ` · ${s.published}` : ''}
                </div>
                {s.snippet && (
                  <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-muted">{s.snippet}</p>
                )}
              </div>
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                title="点击打开原网页"
                className="ml-2 inline-flex shrink-0 items-center gap-1 self-start rounded-full bg-clay/50 px-2 py-0.5 text-[10px] font-medium text-clayDeep transition hover:bg-clay hover:text-ink"
              >
                引用 {s.n}
                <ExternalLink size={10} />
              </a>
            </div>
          </li>
        ))}
        </ol>
      )}
    </section>
  )
}
