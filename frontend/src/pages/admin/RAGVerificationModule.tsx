import { FormEvent, useMemo, useState } from 'react'
import { BrainCircuit, Check, GitMerge, Loader2, Route, Search, SlidersHorizontal } from 'lucide-react'
import { debugRag } from '../../api'
import type { RAGDebugResult, RetrievalCandidate, RAGTraceStep } from '../../types'
import { Field, InlineNotice, ModuleCard, SoftButton } from './shared'

const stepIcons = {
  step_1: BrainCircuit,
  step_2: Route,
  step_3: Search,
  step_4: GitMerge,
}

export default function RAGVerificationModule() {
  const [query, setQuery] = useState('第一次去冰岛，预算中等，想看自然风景')
  const [topK, setTopK] = useState(5)
  const [loading, setLoading] = useState(false)
  const [debugResult, setDebugResult] = useState<RAGDebugResult | null>(null)
  const [error, setError] = useState('')

  async function handleDebug(event: FormEvent) {
    event.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError('')
    try {
      setDebugResult(await debugRag(query, topK))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'RAG 验证失败')
    } finally {
      setLoading(false)
    }
  }

  const routeText = useMemo(() => {
    const routes = debugResult?.retrieve_result.analysis.routes ?? []
    return routes.length > 0 ? routes.join(' + ') : '尚未运行'
  }, [debugResult])

  const weightText = useMemo(() => {
    const weights = debugResult?.retrieve_result.analysis.route_weights ?? {}
    const entries = Object.entries(weights)
    return entries.length > 0 ? entries.map(([route, weight]) => `${route} ${Number(weight).toFixed(2)}`).join(' · ') : '尚未运行'
  }, [debugResult])

  return (
    <div className="space-y-6">
      <ModuleCard
        icon={<SlidersHorizontal size={20} />}
        title="RAG 验证"
        desc="只负责验证检索链路，不编辑模型、Prompt 或文件。输入查询后可以看到四步流水线是否被严格执行。"
      >
        <form onSubmit={handleDebug} className="grid gap-4">
          <Field label="测试 Query">
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="input min-h-[96px] resize-none leading-7"
              placeholder="例如：东京迪士尼门票是多少钱？旁边有什么酒店？"
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-end">
            <Field label="Top-K">
              <input
                type="number"
                min={1}
                max={20}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
                className="input"
              />
            </Field>
            <div className="flex justify-end">
              <SoftButton type="submit" tone="primary" disabled={loading || !query.trim()}>
                {loading ? <Loader2 className="animate-spin" size={16} /> : <Search size={16} />}
                运行四步验证
              </SoftButton>
            </div>
          </div>
        </form>

        <div className="mt-5 grid gap-3 sm:grid-cols-5">
          <Metric label="路由结果" value={routeText} />
          <Metric label="检索权重" value={weightText} />
          <Metric label="决策来源" value={debugResult?.retrieve_result.analysis.decision_source ?? '尚未运行'} />
          <Metric label="最终上下文" value={`${debugResult?.retrieve_result.contexts.length ?? 0}`} />
          <Metric label="注入状态" value={debugResult?.retrieve_result.context_block ? '已生成 context_block' : '无上下文'} />
        </div>

        {error && <div className="mt-4"><InlineNotice tone="error">{error}</InlineNotice></div>}
      </ModuleCard>

      {debugResult && (
        <ModuleCard icon={<Check size={20} />} title="四步 Trace" desc="后端 `/api/rag/debug` 返回的流水线记录，按 Step 1 到 Step 4 展示。">
          <div className="space-y-4">
            {debugResult.trace.map((step) => <TraceStep key={step.step} step={step} />)}
          </div>
        </ModuleCard>
      )}

      {debugResult && (
        <ModuleCard icon={<GitMerge size={20} />} title="最终传给大模型的 Top Context" desc="这里是合并与重排后的结果。聊天接口会把这些片段整理成上下文注入 System Prompt，而不是直接显示给用户。">
          {debugResult.retrieve_result.contexts.length === 0 ? (
            <InlineNotice>没有命中上下文。这通常是因为知识库为空，或者 reranker 过滤掉了低相关片段。</InlineNotice>
          ) : (
            <div className="space-y-3">
              {debugResult.retrieve_result.contexts.map((context, index) => (
                <div key={`${context.chunk_id}-${context.source}`} className="rounded-4xl bg-[#F8F6F1] p-4">
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                    <span className="rounded-full bg-ink px-2.5 py-1 text-paper">#{index + 1}</span>
                    <span className="rounded-full bg-paper px-2.5 py-1">{context.source}</span>
                    <span className="rounded-full bg-paper px-2.5 py-1">score {context.score.toFixed(3)}</span>
                    <span className="rounded-full bg-paper px-2.5 py-1">{String(context.metadata.filename ?? 'unknown')}</span>
                  </div>
                  <p className="text-sm leading-7 text-ink">{context.text}</p>
                </div>
              ))}
            </div>
          )}
        </ModuleCard>
      )}
    </div>
  )
}

function TraceStep({ step }: { step: RAGTraceStep }) {
  const Icon = stepIcons[step.step]
  const routeData = isRecord(step.data.routes) ? step.data.routes : null
  const topContexts = Array.isArray(step.data.top_contexts) ? step.data.top_contexts : []

  return (
    <div className="rounded-4xl bg-[#F8F6F1] p-5">
      <div className="flex items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-3xl bg-paper text-moss">
          <Icon size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold">{step.title}</h3>
            <span className="rounded-full bg-sage px-2.5 py-1 text-[11px] text-moss">{step.status}</span>
          </div>
          <p className="mt-2 text-sm leading-7 text-muted">{step.detail}</p>
          {typeof step.data.decision_source === 'string' && (
            <span className="mt-3 inline-flex rounded-full bg-paper px-3 py-1.5 text-xs font-medium text-muted">
              decision: {step.data.decision_source}
            </span>
          )}
        </div>
      </div>

      {step.step === 'step_1' && (
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <Metric label="BM25 chunks" value={String(step.data.chunk_count ?? 0)} />
          <Metric label="Chroma vectors" value={String(step.data.vector_count ?? 0)} />
          <Metric label="Entity terms" value={String(step.data.entity_count ?? 0)} />
        </div>
      )}

      {step.step === 'step_2' && Array.isArray(step.data.routes) && (
        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap gap-2">
            {step.data.routes.map((route) => (
              <span key={String(route)} className="rounded-full bg-paper px-3 py-1.5 text-xs font-medium text-ink">
                {String(route)}
              </span>
            ))}
          </div>
          <WeightStrip weights={step.data.route_weights} />
        </div>
      )}

      {step.step === 'step_3' && routeData && (
        <div className="mt-4 space-y-3">
          {Object.entries(routeData).map(([route, rawCandidates]) => (
            <CandidateGroup key={route} title={`${route} 召回`} candidates={asCandidates(rawCandidates)} />
          ))}
        </div>
      )}

      {step.step === 'step_4' && (
        <div className="mt-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Metric label="重排后数量" value={String(step.data.reranked_count ?? 0)} />
            <Metric label="是否注入上下文" value={step.data.context_injected ? '是' : '否'} />
          </div>
          <WeightStrip weights={step.data.route_weights} />
          <CandidateGroup title="Top contexts" candidates={asCandidates(topContexts)} />
        </div>
      )}
    </div>
  )
}

function WeightStrip({ weights }: { weights: unknown }) {
  if (!isRecord(weights)) return null
  const entries = Object.entries(weights).filter(([, value]) => typeof value === 'number')
  if (entries.length === 0) return null
  return (
    <div className="grid gap-2 sm:grid-cols-3">
      {entries.map(([route, value]) => (
        <div key={route} className="rounded-3xl bg-paper/80 px-4 py-3">
          <div className="mb-2 flex items-center justify-between text-xs text-muted">
            <span>{route}</span>
            <span>{Number(value).toFixed(2)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full bg-moss" style={{ width: `${Math.min(100, Math.max(0, Number(value) * 100))}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}

function CandidateGroup({ title, candidates }: { title: string; candidates: RetrievalCandidate[] }) {
  return (
    <div className="rounded-3xl bg-paper/75 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-sm font-semibold">{title}</h4>
        <span className="rounded-full bg-[#F8F6F1] px-2.5 py-1 text-xs text-muted">{candidates.length} 条</span>
      </div>
      {candidates.length === 0 ? (
        <p className="text-sm text-muted">没有候选片段。</p>
      ) : (
        <div className="space-y-2">
          {candidates.map((candidate) => (
            <div key={`${candidate.chunk_id}-${candidate.source}`} className="rounded-3xl bg-[#F8F6F1] px-4 py-3">
              <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-muted">
                <span>{candidate.filename ?? 'unknown'}</span>
                <span>{candidate.source}</span>
                <span>score {candidate.score.toFixed(3)}</span>
              </div>
              <p className="text-sm leading-6 text-ink">{candidate.preview}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-3xl bg-[#F8F6F1] px-4 py-3">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 truncate text-sm font-semibold text-ink">{value}</p>
    </div>
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function asCandidates(value: unknown): RetrievalCandidate[] {
  if (!Array.isArray(value)) return []
  return value.filter(isRetrievalCandidate)
}

function isRetrievalCandidate(value: unknown): value is RetrievalCandidate {
  if (!isRecord(value)) return false
  return (
    typeof value.chunk_id === 'string' &&
    typeof value.source === 'string' &&
    typeof value.score === 'number' &&
    typeof value.preview === 'string'
  )
}
