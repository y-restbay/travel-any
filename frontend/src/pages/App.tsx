import { FormEvent, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  ArrowUp,
  BrainCircuit,
  ChevronDown,
  Compass,
  Database,
  FileText,
  Loader2,
  PanelLeft,
  PanelLeftClose,
  Route,
  Search,
  Sparkles,
  User,
  Wrench,
} from 'lucide-react'
import ShellNav from '../components/ShellNav'
import { streamChat } from '../api'
import type { ChatMessage, ThinkingTrace, ThinkingTraceStep } from '../types'

const intro: ChatMessage = {
  id: 'intro',
  role: 'assistant',
  content:
    '你好，我是 **WanderBot 漫游指南**。告诉我目的地、天数、预算、同行人群和喜欢的节奏，我会帮你把旅行计划整理成清晰、舒服、可执行的版本。',
}

const suggestions = ['带父母去京都 5 天，节奏慢一点', '第一次去冰岛，预算中等，想看自然风景', '上海出发，周末两天想找一个安静海边']

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([intro])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [showThinkingDetails, setShowThinkingDetails] = useState(false)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const autoScrollRef = useRef(true)

  useEffect(() => {
    if (!scrollRef.current || !autoScrollRef.current) return
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, isStreaming])

  function handleScroll() {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    autoScrollRef.current = scrollHeight - scrollTop - clientHeight < 60
  }

  useEffect(() => {
    if (!textareaRef.current) return
    textareaRef.current.style.height = '0px'
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`
  }, [input])

  useEffect(() => {
    if (sidebarOpen) {
      document.body.style.setProperty('--sidebar-width', '300px')
    } else {
      document.body.style.setProperty('--sidebar-width', '0px')
    }
  }, [sidebarOpen])

  async function submit(value = input) {
    const content = value.trim()
    if (!content || isStreaming) return

    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: 'user', content }
    const assistantId = crypto.randomUUID()
    const assistantMessage: ChatMessage = { id: assistantId, role: 'assistant', content: '', thinkingTrace: createPendingTrace() }
    const nextMessages = [...messages, userMessage, assistantMessage]

    setMessages(nextMessages)
    setInput('')
    setIsStreaming(true)

    try {
      await streamChat(
        nextMessages
          .filter((message) => message.id !== 'intro')
          .filter((message) => message.content.trim().length > 0)
          .map(({ role, content }) => ({ role, content })),
        (delta) => {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId ? { ...message, content: message.content + delta } : message,
            ),
          )
        },
        (meta) => {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? { ...message, thinkingTrace: updateThinkingTrace(message.thinkingTrace, meta) }
                : message,
            ),
          )
        },
      )
    } catch (error) {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                content:
                  '抱歉，流式连接暂时没有成功。请确认后端服务正在 http://127.0.0.1:6688 运行。',
              }
            : message,
        ),
      )
    } finally {
      setIsStreaming(false)
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    void submit()
  }

  return (
    <main className="flex h-screen flex-col text-ink">
      <ShellNav />
      <div className="flex flex-1 overflow-hidden pt-20">
        {/* ===== Left Sidebar ===== */}
        <aside
          className={`relative flex-shrink-0 overflow-hidden border-r border-line/50 bg-paper/30 backdrop-blur-sm transition-all duration-300 ${
            sidebarOpen ? 'w-[300px]' : 'w-0 md:w-12'
          }`}
        >
          <div className={`flex h-full flex-col ${sidebarOpen ? 'opacity-100' : 'opacity-0 md:opacity-100'} transition-opacity duration-200`}>
            {/* Sidebar header */}
            <div className="flex items-center justify-between px-4 py-3">
              {sidebarOpen && (
                <span className="text-sm font-medium text-muted">辅助面板</span>
              )}
              <button
                type="button"
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="grid h-8 w-8 place-items-center rounded-xl text-muted hover:bg-clay/30 hover:text-ink"
                title={sidebarOpen ? '收起侧栏' : '展开侧栏'}
              >
                {sidebarOpen ? <PanelLeftClose size={16} /> : <PanelLeft size={16} />}
              </button>
            </div>

            {/* Sidebar placeholder content */}
            <div className={`flex flex-1 flex-col items-center justify-center px-4 text-center ${sidebarOpen ? '' : 'hidden md:flex'}`}>
              <div className="rounded-3xl bg-sage/30 p-4">
                <Compass size={24} className="text-moss/60 avatar-spin" />
              </div>
              <p className="mt-4 text-sm leading-6 text-muted">
                地图与工具面板
              </p>
              <p className="mt-1 text-xs leading-5 text-muted/60">
                后续将集成地图浏览、知识库查询等辅助功能
              </p>
            </div>
          </div>
        </aside>

        {/* ===== Chat Area ===== */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Messages */}
          <section ref={scrollRef} onScroll={handleScroll} className="soft-scrollbar flex-1 overflow-y-auto px-4 pb-44 pt-6">
            <div className="mx-auto flex w-full max-w-3xl flex-col gap-7">
              {messages.map((message, index) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  index={index}
                  showThinkingDetails={showThinkingDetails}
                />
              ))}

              {isStreaming && (
                <div className="flex items-center gap-2 pl-1 text-sm text-muted">
                  <Loader2 className="animate-spin" size={16} />
                  WanderBot 正在整理路线
                </div>
              )}
            </div>
          </section>

          {/* Input area (no longer fixed) */}
          <div className="flex-shrink-0 bg-gradient-to-t from-[#F4F1EC] via-[#F4F1EC]/92 to-transparent px-4 pb-5 pt-16">
            <form onSubmit={handleSubmit} className="mx-auto w-full max-w-3xl">
              {messages.length === 1 && (
                <div className="mb-4 flex flex-wrap gap-2">
                  {suggestions.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => void submit(suggestion)}
                      className="rounded-3xl bg-paper/80 px-4 py-2 text-sm text-muted shadow-quiet transition hover:bg-paper hover:text-ink"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              )}
              <div className="flex items-end gap-3 rounded-4xl bg-paper/95 p-3 shadow-soft backdrop-blur-xl transition focus-within:shadow-focus">
                <button
                  type="button"
                  onClick={() => setShowThinkingDetails((value) => !value)}
                  className={[
                    'mb-1 grid h-10 w-10 shrink-0 place-items-center rounded-3xl border transition',
                    showThinkingDetails
                      ? 'border-clayDeep/35 bg-clay/70 text-ink shadow-quiet'
                      : 'border-line bg-paper/70 text-muted hover:border-clayDeep/30 hover:text-ink',
                  ].join(' ')}
                  aria-pressed={showThinkingDetails}
                  aria-label={showThinkingDetails ? '隐藏思考过程' : '展示思考过程'}
                  title={showThinkingDetails ? '隐藏思考过程' : '展示思考过程'}
                >
                  <BrainCircuit size={18} />
                </button>
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      void submit()
                    }
                  }}
                  rows={1}
                  placeholder="描述你的目的地、日期、预算和旅行偏好..."
                  className="max-h-44 min-h-[52px] flex-1 resize-none bg-transparent px-4 py-4 text-[15px] leading-6 text-ink outline-none placeholder:text-muted/70"
                />
                <button
                  type="submit"
                  disabled={!input.trim() || isStreaming}
                  className="grid h-12 w-12 shrink-0 place-items-center rounded-3xl bg-ink text-paper shadow-quiet transition hover:translate-y-[-1px] disabled:cursor-not-allowed disabled:bg-muted/40"
                  aria-label="发送"
                >
                  {isStreaming ? <Loader2 className="animate-spin" size={18} /> : <ArrowUp size={18} />}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </main>
  )
}

function MessageBubble({
  message,
  index,
  showThinkingDetails,
}: {
  message: ChatMessage
  index: number
  showThinkingDetails: boolean
}) {
  const isUser = message.role === 'user'
  const parsedContent = isUser ? { answer: message.content, reasoning: '' } : splitReasoningContent(message.content)
  const displayTrace =
    !isUser && parsedContent.reasoning
      ? appendReasoningTextStep(message.thinkingTrace, parsedContent.reasoning)
      : message.thinkingTrace

  return (
    <motion.article
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, delay: Math.min(index * 0.02, 0.12) }}
      className={`flex items-end gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
    >
      {/* Avatar */}
      <div
        className={`grid h-9 w-9 shrink-0 place-items-center rounded-full border-2 ${
          isUser
            ? 'border-clayDeep/30 bg-clay/60 avatar-breathe'
            : 'border-clayDeep/30 bg-paper avatar-spin'
        }`}
      >
        {isUser ? (
          <User size={15} className="text-clayDeep" />
        ) : (
          <Compass size={15} className="text-clayDeep" />
        )}
      </div>

      {/* Message content */}
      <div
        className={[
          'max-w-[80%] text-[15px] md:max-w-[70%]',
          isUser
            ? 'rounded-4xl bg-clay px-5 py-4 text-ink shadow-quiet'
            : 'rounded-3xl py-2 pr-3 text-ink',
        ].join(' ')}
      >
        {!isUser && index === 0 && (
          <div className="mb-3 flex items-center gap-2 text-sm text-clayDeep">
            <Sparkles size={15} />
            WanderBot
          </div>
        )}
        {!isUser && displayTrace && (
          <ThinkingPanel trace={displayTrace} forceOpen={showThinkingDetails} />
        )}
        {isUser ? (
          <p className="whitespace-pre-wrap leading-7">{message.content}</p>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]} className="markdown-body">
            {parsedContent.answer || ' '}
          </ReactMarkdown>
        )}
      </div>
    </motion.article>
  )
}

function ThinkingPanel({ trace, forceOpen }: { trace: ThinkingTrace; forceOpen: boolean }) {
  const [expanded, setExpanded] = useState(forceOpen)
  const doneCount = trace.steps.filter((step) => step.status === 'done').length
  const activeStep = trace.steps.find((step) => step.status === 'active')

  useEffect(() => {
    setExpanded(forceOpen)
  }, [forceOpen])

  return (
    <div className="mb-3 overflow-hidden rounded-3xl border border-line/70 bg-paper/70 shadow-quiet">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition hover:bg-[#F8F6F1]"
        aria-expanded={expanded}
      >
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-2xl bg-sage/55 text-moss">
          <BrainCircuit size={16} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[13px] font-medium text-ink">思考过程</span>
          <span className="block truncate text-xs text-muted">
            {trace.summary || activeStep?.detail || `已完成 ${doneCount}/${trace.steps.length} 个步骤`}
          </span>
        </span>
        <ChevronDown
          size={16}
          className={`shrink-0 text-muted transition ${expanded ? 'rotate-180' : ''}`}
        />
      </button>

      {expanded && (
        <div className="border-t border-line/70 px-3 pb-3 pt-2">
          <div className="mb-2 flex flex-wrap gap-2 text-[11px] text-muted">
            {trace.model && <span className="rounded-full bg-[#F8F6F1] px-2 py-1">{trace.model}</span>}
            {trace.provider && <span className="rounded-full bg-[#F8F6F1] px-2 py-1">{trace.provider}</span>}
            {trace.runtime && <span className="rounded-full bg-[#F8F6F1] px-2 py-1">{trace.runtime}</span>}
          </div>
          <div className="space-y-2">
            {trace.steps.map((step) => (
              <TraceStepItem key={step.id} step={step} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function TraceStepItem({ step }: { step: ThinkingTraceStep }) {
  const iconClass = step.status === 'active' ? 'text-clayDeep' : step.status === 'error' ? 'text-red-700' : 'text-moss'

  return (
    <div className="grid grid-cols-[28px_1fr] gap-2 rounded-2xl px-1 py-1.5">
      <div className={`mt-0.5 grid h-7 w-7 place-items-center rounded-full bg-[#F8F6F1] ${iconClass}`}>
        {getTraceIcon(step.id)}
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-[13px] font-medium text-ink">{step.title}</p>
          <span className="rounded-full bg-[#F8F6F1] px-2 py-0.5 text-[10px] text-muted">{getStatusLabel(step.status)}</span>
        </div>
        <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-muted">{step.detail}</p>
        {step.data && Object.keys(step.data).length > 0 && (
          <pre className="mt-2 max-h-44 overflow-auto rounded-2xl bg-[#2F2A25] p-3 text-[11px] leading-5 text-[#F8F6F1] soft-scrollbar">
            {JSON.stringify(step.data, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}

function getTraceIcon(stepId: string) {
  if (stepId.includes('query')) return <Search size={14} />
  if (stepId.includes('route')) return <Route size={14} />
  if (stepId.includes('context')) return <Database size={14} />
  if (stepId.includes('prompt')) return <FileText size={14} />
  if (stepId.includes('tool')) return <Wrench size={14} />
  return <BrainCircuit size={14} />
}

function getStatusLabel(status: ThinkingTraceStep['status']) {
  if (status === 'active') return '进行中'
  if (status === 'done') return '完成'
  if (status === 'error') return '异常'
  return '等待'
}

function createPendingTrace(): ThinkingTrace {
  return {
    summary: '等待检索和路由信息',
    steps: [
      { id: 'query', title: '整理用户问题', status: 'active', detail: '正在合并本轮和最近几轮用户问题。' },
      { id: 'route', title: '选择检索路由', status: 'pending', detail: '等待后端返回向量、关键词或图谱检索策略。' },
      { id: 'context', title: '召回知识库资料', status: 'pending', detail: '等待检索结果。' },
      { id: 'prompt', title: '组装发送给大模型的上下文', status: 'pending', detail: '等待上下文注入结果。' },
    ],
  }
}

function updateThinkingTrace(existingTrace: ThinkingTrace | undefined, payload: unknown): ThinkingTrace {
  const trace = existingTrace ?? createPendingTrace()
  if (!isRecord(payload)) return trace

  if (isRecord(payload.tool_call)) {
    const toolCall = payload.tool_call
    const round = typeof toolCall.round === 'number' ? toolCall.round : 1
    const name = typeof toolCall.name === 'string' ? toolCall.name : 'tool'
    const status = toolCall.status === 'done' ? 'done' : 'active'
    const id = `tool-${round}-${name}`
    return upsertTraceStep(trace, {
      id,
      title: `调用工具：${name}`,
      status,
      detail: status === 'done' ? '工具已返回结果，准备交给大模型继续整理。' : '大模型选择调用外部工具获取实时信息。',
      data: compactRecord({
        round,
        args: toolCall.args,
        result_preview: toolCall.result_preview,
      }),
    })
  }

  const routes = asStringArray(payload.rag_routes)
  const contextCount = typeof payload.rag_context_count === 'number' ? payload.rag_context_count : 0
  const contextInjected = Boolean(payload.rag_context_injected)
  const model = typeof payload.model === 'string' ? payload.model : trace.model
  const provider = typeof payload.provider === 'string' ? payload.provider : trace.provider
  const runtime = typeof payload.runtime === 'string' ? payload.runtime : trace.runtime
  const query = typeof payload.rag_query === 'string' ? payload.rag_query : ''
  const reasoning = typeof payload.rag_reasoning === 'string' ? payload.rag_reasoning : ''

  return {
    ...trace,
    provider,
    model,
    runtime,
    summary: routes.length
      ? `已选择 ${routes.map(getRouteLabel).join('、')}，命中 ${contextCount} 条资料`
      : trace.summary,
    steps: [
      {
        id: 'query',
        title: '整理用户问题',
        status: 'done',
        detail: query || '已完成本轮问题整理。',
        data: query ? { rag_query: query } : undefined,
      },
      {
        id: 'route',
        title: '选择检索路由',
        status: routes.length ? 'done' : 'pending',
        detail: reasoning || '等待后端返回检索策略。',
        data: compactRecord({
          routes: routes.map(getRouteLabel),
          route_weights: payload.rag_route_weights,
          decision_source: payload.rag_decision_source,
        }),
      },
      {
        id: 'context',
        title: '召回知识库资料',
        status: routes.length ? 'done' : 'pending',
        detail: contextCount > 0 ? `已召回 ${contextCount} 条候选资料，并完成去重重排。` : '本轮没有命中可注入的知识库资料。',
        data: compactRecord({
          context_count: contextCount,
          sources: payload.rag_injected_contexts ?? payload.rag_sources,
        }),
      },
      {
        id: 'prompt',
        title: '组装发送给大模型的上下文',
        status: routes.length ? 'done' : 'pending',
        detail: contextInjected ? '已把重排后的知识库片段放入系统上下文，随后开始生成回答。' : '未注入知识库片段，直接使用系统提示词和对话历史生成回答。',
        data: compactRecord({
          context_injected: contextInjected,
          context_block_preview: payload.rag_context_block_preview,
        }),
      },
      ...trace.steps.filter((step) => step.id.startsWith('tool-')),
    ],
  }
}

function upsertTraceStep(trace: ThinkingTrace, step: ThinkingTraceStep): ThinkingTrace {
  const nextSteps = trace.steps.some((item) => item.id === step.id)
    ? trace.steps.map((item) => (item.id === step.id ? step : item))
    : [...trace.steps, step]
  return {
    ...trace,
    summary: step.status === 'done' ? `${step.title} 已完成` : step.detail,
    steps: nextSteps,
  }
}

function getRouteLabel(route: string) {
  if (route === 'vector') return '向量检索'
  if (route === 'keyword') return '关键词检索'
  if (route === 'graph') return '图谱检索'
  return route
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function compactRecord(record: Record<string, unknown>): Record<string, unknown> | undefined {
  const compacted = Object.fromEntries(
    Object.entries(record).filter(([, value]) => value !== undefined && value !== null && value !== ''),
  )
  return Object.keys(compacted).length > 0 ? compacted : undefined
}

function splitReasoningContent(content: string): { answer: string; reasoning: string } {
  const tagPairs = [
    ['<think>', '</think>'],
    ['<thinking>', '</thinking>'],
    ['<reason>', '</reason>'],
    ['<reasoning>', '</reasoning>'],
    ['<thought>', '</thought>'],
    ['<|begin_of_thought|>', '<|end_of_thought|>'],
  ] as const

  let answer = content
  const reasoningParts: string[] = []

  for (const [openTag, closeTag] of tagPairs) {
    const escapedOpen = escapeRegExp(openTag)
    const escapedClose = escapeRegExp(closeTag)
    const closedBlock = new RegExp(`${escapedOpen}([\\s\\S]*?)${escapedClose}`, 'gi')
    answer = answer.replace(closedBlock, (_match, reasoning: string) => {
      if (reasoning.trim()) reasoningParts.push(reasoning.trim())
      return ''
    })

    const openIndex = answer.toLowerCase().indexOf(openTag.toLowerCase())
    if (openIndex >= 0) {
      const reasoning = answer.slice(openIndex + openTag.length).trim()
      if (reasoning) reasoningParts.push(reasoning)
      answer = answer.slice(0, openIndex)
    }
  }

  return {
    answer: answer.trim(),
    reasoning: reasoningParts.join('\n\n'),
  }
}

function appendReasoningTextStep(trace: ThinkingTrace | undefined, reasoning: string): ThinkingTrace {
  const baseTrace = trace ?? createPendingTrace()
  return upsertTraceStep(baseTrace, {
    id: 'model-reasoning',
    title: '模型返回的思考片段',
    status: 'done',
    detail: '已从模型输出中识别 reasoning 标签，并从主回答中折叠展示。',
    data: { reasoning },
  })
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
