import { Children, FormEvent, ReactNode, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  ArrowLeftRight,
  ArrowUp,
  BrainCircuit,
  ChevronDown,
  Cloud,
  Compass,
  Database,
  Download,
  FileText,
  Globe,
  GripVertical,
  History,
  ImageIcon,
  Loader2,
  Mic,
  MicOff,
  PanelRightClose,
  Route,
  Search,
  Sparkles,
  X,
  User,
  Wrench,
} from 'lucide-react'
import MapPanel, { type MapPanelHandle } from '../components/MapPanel'
import ItineraryCard from '../components/ItineraryCard'
import HistoryPanel from '../components/HistoryPanel'
import SourcesPanel from '../components/SourcesPanel'
import {
  type ConversationMeta,
  createConversation,
  deleteConversation,
  getActiveId,
  listConversations,
  loadConversation,
  saveConversation,
  setActiveId,
} from '../lib/conversationStore'
import { API_BASE, getAdminConfig, resumeChat, streamChat, uploadImage } from '../api'
import { createId } from '../lib/uuid'
import type { AgentRuntime, ChatMessage, ExportInfo, Itinerary, MapPayload, PendingInterrupt, ThinkingStep, ThinkingTrace, ThinkingTraceStep, WebSourceBundle } from '../types'

const DEFAULT_MAP_WIDTH = 420
const MIN_MAP_WIDTH = 340
const MAX_MAP_WIDTH = 720

const intro: ChatMessage = {
  id: 'intro',
  role: 'assistant',
  content:
    '你好，我是 **WanderBot 漫游指南**。告诉我目的地、天数、预算、同行人群和喜欢的节奏，我会帮你把旅行计划整理成清晰、舒服、可执行的版本。',
}

type PendingImageItem = {
  id: string
  ref: string
  preview: string
  name: string
  status: 'uploading' | 'ready' | 'error'
  error?: string
}

const MAX_IMAGES = 5
const MAX_IMAGE_SIZE_MB = 50
const MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

const suggestions = [
  '西安兵马俑 + 华清宫 2 天游，帮我用地图把景点、交通和顺路餐馆串起来',
  '黄山 3 天游，想看天气、缆车、徒步路线和下山后的返程安排',
  '成都到九寨沟 4 天游，帮我规划自驾路线、住宿停靠点和每日行程',
  '北京故宫、颐和园、什刹海 5 天游，按天拆分成一份很详细的旅行方案，帮我选好其他的目的地，再查查天气和交通，再生成每天的景点顺序、地图动线、午餐晚餐建议、预算和注意事项，最后把可执行版本完整输出并在系统的地图显示出来。',
]

type SpeechRecognitionCtor = new () => SpeechRecognitionLike
type SpeechRecognitionLike = {
  lang: string
  continuous: boolean
  interimResults: boolean
  onstart: (() => void) | null
  onend: (() => void) | null
  onerror: ((event: { error?: string }) => void) | null
  onresult: ((event: SpeechRecognitionResultEventLike) => void) | null
  start: () => void
  stop: () => void
}
type SpeechRecognitionResultEventLike = {
  resultIndex: number
  results: ArrayLike<{
    isFinal: boolean
    0: { transcript: string }
  }>
}

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null
  const speechWindow = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition ?? null
}

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([intro])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null)
  const [mapVisible, setMapVisible] = useState(false)
  const [mapWidth, setMapWidth] = useState(DEFAULT_MAP_WIDTH)
  const [latestMapPayloads, setLatestMapPayloads] = useState<MapPayload[]>([])
  const showThinkingDetails = false
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const autoScrollRef = useRef(true)
  const isComposingRef = useRef(false)
  const mapPanelRef = useRef<MapPanelHandle | null>(null)
  const conversationIdRef = useRef<string | null>(
    typeof window !== 'undefined' ? getActiveId() : null,
  )
  const [conversations, setConversations] = useState<ConversationMeta[]>([])
  const [activeConvId, setActiveConvId] = useState<string | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [runtime, setRuntime] = useState<AgentRuntime>('tools')
  const [deepThinking, setDeepThinking] = useState(false)
  const [knowledgeSource, setKnowledgeSource] = useState<'local' | 'cloud'>('local')
  const [webSearch, setWebSearch] = useState(false)
  // 看图识景点:多图上传管理
  const [pendingImages, setPendingImages] = useState<PendingImageItem[]>([])
  const pendingImagesRef = useRef(pendingImages)
  pendingImagesRef.current = pendingImages
  const [imageError, setImageError] = useState('')
  const imageInputRef = useRef<HTMLInputElement | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const dragCounterRef = useRef(0)
  const [isVoiceListening, setIsVoiceListening] = useState(false)
  const [voiceSupported, setVoiceSupported] = useState(true)
  const resizeRef = useRef({ startX: 0, startWidth: DEFAULT_MAP_WIDTH })
  const speechRecognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const voiceBaseInputRef = useRef('')

  // 始终指向最新 messages,供 debounce / beforeunload / 切换前 flush 读取。
  const messagesRef = useRef(messages)
  messagesRef.current = messages

  function persistNow() {
    if (conversationIdRef.current) {
      saveConversation(conversationIdRef.current, messagesRef.current)
      setConversations(listConversations())
    }
  }

  function resetTo(next: ChatMessage[], id: string) {
    conversationIdRef.current = id
    setActiveConvId(id)
    setActiveId(id)
    setMessages(next)
    setInput('')
    setDeepThinking(false)
    setWebSearch(false)
    setKnowledgeSource('local')
    mapPanelRef.current?.clear()
    setLatestMapPayloads([])
    setMapVisible(false)
  }

  function openConversation(id: string) {
    const stored = loadConversation(id)
    resetTo([intro, ...((stored ?? []) as ChatMessage[])], id)
  }

  function startFresh() {
    resetTo([intro], createConversation())
  }

  function handleSelectConversation(id: string) {
    persistNow()
    openConversation(id)
    setHistoryOpen(false)
  }

  function handleNewConversation() {
    persistNow()
    startFresh()
    setHistoryOpen(false)
  }

  function handleDeleteConversation(id: string) {
    const deletingActive = id === conversationIdRef.current
    if (!deletingActive) persistNow() // 保存当前会话,别碰被删的那条
    deleteConversation(id)
    const list = listConversations()
    setConversations(list)
    if (deletingActive) {
      if (list.length) openConversation(list[0].id)
      else startFresh()
    }
  }

  useEffect(() => {
    getAdminConfig()
      .then((cfg) => {
        setRuntime((cfg.llm_config.runtime as AgentRuntime) ?? 'tools')
      })
      .catch(() => {
        /* 后端没起来时静默 */
      })
  }, [])

  useEffect(() => {
    setVoiceSupported(Boolean(getSpeechRecognitionCtor()))
    return () => {
      speechRecognitionRef.current?.stop()
      speechRecognitionRef.current = null
    }
  }, [])

  // 挂载时恢复上次打开的会话(有内容才恢复,否则保持全新欢迎页)。
  useEffect(() => {
    setConversations(listConversations())
    const id = getActiveId()
    if (!id) return
    const stored = loadConversation(id)
    if (stored && stored.length) {
      conversationIdRef.current = id
      setActiveConvId(id)
      setMessages([intro, ...(stored as ChatMessage[])])
    }
  }, [])

  // messages 变化后防抖落盘(流式 delta 很密集,400ms 合并写一次)。
  useEffect(() => {
    const id = conversationIdRef.current
    if (!id) return
    const timer = window.setTimeout(() => {
      saveConversation(id, messagesRef.current)
      setConversations(listConversations())
    }, 400)
    return () => window.clearTimeout(timer)
  }, [messages, activeConvId])

  // 关闭/刷新标签页时兜底保存,防止流式进行中关页丢最后一段。
  useEffect(() => {
    const handler = () => {
      if (conversationIdRef.current) {
        saveConversation(conversationIdRef.current, messagesRef.current)
      }
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [])

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
    if (mapVisible && latestMapPayloads.length > 0) {
      mapPanelRef.current?.renderRoute(latestMapPayloads[0])
    }
  }, [mapVisible, latestMapPayloads])

  function revealMap(payloads: MapPayload[] | MapPayload) {
    const routes = Array.isArray(payloads) ? payloads : [payloads]
    setLatestMapPayloads(routes)
    setMapVisible(true)
  }

  function closeMap() {
    setMapVisible(false)
  }

  function handleMapResizeStart(event: React.PointerEvent<HTMLButtonElement>) {
    event.preventDefault()
    resizeRef.current = { startX: event.clientX, startWidth: mapWidth }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function handleMapResizeMove(event: React.PointerEvent<HTMLButtonElement>) {
    if (!(event.buttons & 1)) return
    const delta = resizeRef.current.startX - event.clientX
    const nextWidth = Math.min(MAX_MAP_WIDTH, Math.max(MIN_MAP_WIDTH, resizeRef.current.startWidth + delta))
    setMapWidth(nextWidth)
  }

  function handleInterruptDecision(messageId: string, decision: boolean) {
    let threadId: string | null = null
    setMessages((current) =>
      current.map((m) => {
        if (m.id !== messageId || !m.pendingInterrupt) return m
        threadId = m.pendingInterrupt.thread_id
        return {
          ...m,
          pendingInterrupt: { ...m.pendingInterrupt, status: decision ? 'approved' : 'rejected' },
        }
      }),
    )
    if (!threadId) return
    setIsStreaming(true)
    setStreamingMessageId(messageId)
    resumeChat(
      threadId,
      decision,
      buildStreamCallbacks(messageId, setMessages, conversationIdRef, setLatestMapPayloads),
    )
      .catch(() => {
        setMessages((current) =>
          current.map((m) =>
            m.id === messageId
              ? {
                  ...m,
                  content:
                    m.content +
                    '\n\n_(continue 失败:请确认后端的 supervisor 路径在线。)_',
                }
              : m,
          ),
        )
      })
      .finally(() => {
        setIsStreaming(false)
        setStreamingMessageId(null)
      })
  }

  async function submit(value = input) {
    // 没文本但带了图片时,默认填一个景点识别请求,避免后端 content 长度校验失败。
    const readyImages = pendingImages.filter((p) => p.status === 'ready')
    const hasImages = readyImages.length > 0
    let content = value.trim()
    if (!content && hasImages) {
      content = '请帮我识别这些图片中的景点。'
    }
    if ((!content || isStreaming) && !hasImages) return

    // 首条用户消息时才落地会话 id(避免空会话刷屏);后续沿用同一 id。
    if (!conversationIdRef.current) {
      const id = createConversation()
      conversationIdRef.current = id
      setActiveConvId(id)
    }

    // 多图:全部 image_ref 放入 image_refs;单图:兼容旧字段 image_ref
    const refs = readyImages.map((p) => p.ref)
    const previews = readyImages.map((p) => p.preview)
    const userMessage: ChatMessage = {
      id: createId(),
      role: 'user',
      content,
      ...(refs.length > 0
        ? { image_refs: refs, image_previews: previews }
        : {}),
      // 单图兼容
      ...(refs.length === 1
        ? { image_ref: refs[0], image_preview: previews[0] }
        : {}),
    }
    const assistantId = createId()
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      thinkingTrace: deepThinking || knowledgeSource === 'cloud' ? createPendingTrace(knowledgeSource) : undefined,
    }
    if (deepThinking && knowledgeSource !== 'cloud') {
      assistantMessage.thinkingSteps = []
    }
    const baseMessages = dropTransientAssistantStatus(dropTrailingDuplicateUserMessage(messages, content))
    const nextMessages = [...baseMessages, userMessage, assistantMessage]

    setMessages(nextMessages)
    setInput('')
    clearAllPendingImages()
    setIsStreaming(true)
    setStreamingMessageId(assistantId)

    try {
      await streamChat(
        nextMessages
          .filter((message) => message.id !== 'intro')
          .filter((message) => message.content.trim().length > 0)
          .map(({ role, content, image_ref, image_refs }) => ({
            role,
            content,
            ...(image_ref ? { image_ref } : {}),
            ...(image_refs && image_refs.length > 0 ? { image_refs } : {}),
          })),
        buildStreamCallbacks(assistantId, setMessages, conversationIdRef, setLatestMapPayloads),
        undefined,
        undefined,
        undefined,
        undefined,
        conversationIdRef.current ?? undefined,
        deepThinking ? 'deep_thinking' : undefined,
        knowledgeSource,
        webSearch,
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
      setStreamingMessageId(null)
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    void submit()
  }

  async function handlePickImage(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    if (files.length === 0) return

    const existingReady = pendingImagesRef.current.filter((p) => p.status === 'ready').length
    const totalAfterAdd = existingReady + files.length
    if (totalAfterAdd > MAX_IMAGES) {
      setImageError(`最多上传 ${MAX_IMAGES} 张图片，已有 ${existingReady} 张`)
      return
    }

    for (const file of files) {
      if (!file.type.startsWith('image/')) {
        setImageError(`"${file.name}" 不是图片文件，已跳过`)
        continue
      }
      if (file.size > MAX_IMAGE_SIZE_BYTES) {
        setImageError(
          `"${file.name}" 太大 (${(file.size / (1024 * 1024)).toFixed(1)}MB)，上限 ${MAX_IMAGE_SIZE_MB}MB，已跳过`,
        )
        continue
      }

      const itemId = createId()
      const preview = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result || ''))
        reader.onerror = () => reject(new Error('读取本地图片失败'))
        reader.readAsDataURL(file)
      })

      // 先加预览占位，再上传
      const placeholder: PendingImageItem = { id: itemId, ref: '', preview, name: file.name, status: 'uploading' }
      setPendingImages((prev) => [...prev, placeholder])

      // 上传
      try {
        const { image_ref } = await uploadImage(file)
        setPendingImages((prev) =>
          prev.map((p) => (p.id === itemId ? { ...p, ref: image_ref, status: 'ready' } : p)),
        )
      } catch (err) {
        setPendingImages((prev) =>
          prev.map((p) =>
            p.id === itemId
              ? { ...p, status: 'error', error: err instanceof Error ? err.message : '上传失败' }
              : p,
          ),
        )
      }
    }
  }

  function removePendingImage(id: string) {
    setPendingImages((prev) => prev.filter((p) => p.id !== id))
    setImageError('')
  }

  function retryUpload(item: PendingImageItem) {
    // 重新触发上传入口：快速方法是在 items 里把 status 重置为 uploading，但实际重试需要 file
    // 这里简化处理：删除该项，用户重新选图
    removePendingImage(item.id)
  }

  function clearAllPendingImages() {
    setPendingImages([])
    setImageError('')
    if (imageInputRef.current) imageInputRef.current.value = ''
  }

  // ---- 拖拽上传 ----
  function handleDragEnter(event: React.DragEvent) {
    event.preventDefault()
    event.stopPropagation()
    dragCounterRef.current += 1
    // 只检查是否有文件类型，不阻止非文件拖入
    setIsDragging(true)
  }

  function handleDragOver(event: React.DragEvent) {
    event.preventDefault()
    event.stopPropagation()
  }

  function handleDragLeave(event: React.DragEvent) {
    event.preventDefault()
    event.stopPropagation()
    dragCounterRef.current -= 1
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0
      setIsDragging(false)
    }
  }

  async function handleDrop(event: React.DragEvent) {
    event.preventDefault()
    event.stopPropagation()
    setIsDragging(false)
    dragCounterRef.current = 0

    const files = Array.from(event.dataTransfer.files).filter((f) => f.type.startsWith('image/'))
    if (files.length === 0) {
      setImageError('仅支持图片文件，已忽略非图片文件')
      return
    }
    await processImageFiles(files)
  }

  // ---- 粘贴上传 ----
  useEffect(() => {
    function handlePaste(event: ClipboardEvent) {
      if (isStreaming || !event.clipboardData) return
      const items = Array.from(event.clipboardData.items)
      const imageFiles = items
        .filter((item) => item.type.startsWith('image/'))
        .map((item) => item.getAsFile())
        .filter((f): f is File => f !== null)
      if (imageFiles.length === 0) return
      event.preventDefault()
      void processImageFiles(imageFiles)
    }
    window.addEventListener('paste', handlePaste)
    return () => window.removeEventListener('paste', handlePaste)
  }, [isStreaming])

  // ---- 通用图片文件处理 ----
  async function processImageFiles(files: File[]) {
    // 从 ref 读取最新 pendingImages，避免闭包过期
    const currentImages = pendingImagesRef.current
    const existingReady = currentImages.filter((p) => p.status === 'ready').length
    const totalAfterAdd = existingReady + files.length
    if (totalAfterAdd > MAX_IMAGES) {
      setImageError(`最多上传 ${MAX_IMAGES} 张图片，已有 ${existingReady} 张`)
      return
    }

    for (const file of files) {
      if (file.size > MAX_IMAGE_SIZE_BYTES) {
        setImageError(
          `"${file.name}" 太大 (${(file.size / (1024 * 1024)).toFixed(1)}MB)，上限 ${MAX_IMAGE_SIZE_MB}MB，已跳过`,
        )
        continue
      }

      const itemId = createId()
      const preview = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result || ''))
        reader.onerror = () => reject(new Error('读取本地图片失败'))
        reader.readAsDataURL(file)
      })

      const placeholder: PendingImageItem = { id: itemId, ref: '', preview, name: file.name, status: 'uploading' }
      setPendingImages((prev) => [...prev, placeholder])

      try {
        const { image_ref } = await uploadImage(file)
        setPendingImages((prev) =>
          prev.map((p) => (p.id === itemId ? { ...p, ref: image_ref, status: 'ready' } : p)),
        )
      } catch (err) {
        setPendingImages((prev) =>
          prev.map((p) =>
            p.id === itemId
              ? { ...p, status: 'error', error: err instanceof Error ? err.message : '上传失败' }
              : p,
          ),
        )
      }
    }
  }

  function toggleVoiceInput() {
    if (isStreaming) return
    const Recognition = getSpeechRecognitionCtor()
    if (!Recognition) {
      setVoiceSupported(false)
      return
    }

    if (isVoiceListening) {
      speechRecognitionRef.current?.stop()
      return
    }

    const recognition = new Recognition()
    recognition.lang = 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = true
    voiceBaseInputRef.current = input.trim()
    let finalTranscript = ''

    recognition.onstart = () => setIsVoiceListening(true)
    recognition.onend = () => {
      setIsVoiceListening(false)
      speechRecognitionRef.current = null
      textareaRef.current?.focus()
    }
    recognition.onerror = () => {
      setIsVoiceListening(false)
      speechRecognitionRef.current = null
      textareaRef.current?.focus()
    }
    recognition.onresult = (event) => {
      let interimTranscript = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]
        const transcript = result[0]?.transcript ?? ''
        if (result.isFinal) finalTranscript += transcript
        else interimTranscript += transcript
      }
      const spoken = `${finalTranscript}${interimTranscript}`.trim()
      const base = voiceBaseInputRef.current
      setInput([base, spoken].filter(Boolean).join(base && spoken ? ' ' : ''))
    }

    speechRecognitionRef.current = recognition
    recognition.start()
  }

  return (
    <main className="flex h-screen flex-col text-ink">
      <div className="flex flex-1 overflow-hidden">
        <HistoryPanel
          open={historyOpen}
          conversations={conversations}
          activeId={activeConvId}
          onSelect={handleSelectConversation}
          onNew={handleNewConversation}
          onDelete={handleDeleteConversation}
          onClose={() => setHistoryOpen(false)}
        />
        {/* ===== Chat Area ===== */}
        <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
          {!historyOpen && (
            <button
              type="button"
              onClick={() => setHistoryOpen(true)}
              className="absolute left-3 top-3 z-20 hidden h-9 items-center gap-1.5 rounded-3xl bg-paper/85 px-3 text-[12px] text-muted shadow-quiet transition hover:bg-paper hover:text-ink md:inline-flex"
              title="会话历史"
              aria-label="会话历史"
            >
              <History size={15} />
              历史
            </button>
          )}
          {/* Messages */}
          <section ref={scrollRef} onScroll={handleScroll} className="soft-scrollbar flex-1 overflow-y-auto px-4 pb-8 pt-6">
            <div className="mx-auto flex w-full max-w-5xl flex-col gap-7">
              {messages.map((message, index) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  index={index}
                  showThinkingDetails={showThinkingDetails}
                  isStreaming={isStreaming && message.id === streamingMessageId}
                  onShowMap={revealMap}
                  onInterruptDecision={(decision) => handleInterruptDecision(message.id, decision)}
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
          <div className="flex-shrink-0 bg-[#F4F1EC] px-4 pb-5 pt-3">
            <form onSubmit={handleSubmit} className="mx-auto w-full max-w-5xl">
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
              <div
                  className="relative rounded-[2rem] bg-paper/95 p-2.5 shadow-soft backdrop-blur-xl transition focus-within:shadow-focus"
                  onDragEnter={handleDragEnter}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                >
                {/* 拖拽遮罩 */}
                {isDragging && (
                  <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center rounded-[2rem] border-2 border-dashed border-moss bg-sage/30 backdrop-blur-sm">
                    <div className="flex flex-col items-center gap-2 text-moss">
                      <ImageIcon size={32} />
                      <span className="text-sm font-medium">拖放图片到这里</span>
                    </div>
                  </div>
                )}
                {/* 图片缩略图队列 */}
                {(pendingImages.length > 0 || imageError) && (
                  <div className="mx-1 mb-2 flex flex-wrap items-center gap-2">
                    {pendingImages.map((item) => (
                      <div key={item.id} className="group relative shrink-0">
                        <img
                          src={item.preview}
                          alt={item.name}
                          className={`h-14 w-14 rounded-2xl object-cover ${
                            item.status === 'error'
                              ? 'ring-2 ring-red-400 opacity-60'
                              : item.status === 'uploading'
                                ? 'opacity-70'
                                : ''
                          }`}
                        />
                        {item.status === 'uploading' && (
                          <div className="absolute inset-0 flex items-center justify-center rounded-2xl bg-black/30">
                            <Loader2 className="animate-spin text-paper" size={16} />
                          </div>
                        )}
                        {item.status === 'error' && (
                          <div className="absolute inset-0 flex items-center justify-center rounded-2xl bg-black/20">
                            <X size={16} className="text-red-500" />
                          </div>
                        )}
                        <button
                          type="button"
                          onClick={() => removePendingImage(item.id)}
                          className="absolute -right-1.5 -top-1.5 grid h-5 w-5 place-items-center rounded-full bg-paper text-muted opacity-0 shadow transition group-hover:opacity-100 hover:text-ink"
                          title="移除图片"
                          aria-label="移除图片"
                        >
                          <X size={11} />
                        </button>
                      </div>
                    ))}
                    {imageError && (
                      <span className="max-w-[200px] truncate text-[11px] text-red-600">{imageError}</span>
                    )}
                    {pendingImages.length > 0 && (
                      <button
                        type="button"
                        onClick={clearAllPendingImages}
                        className="shrink-0 rounded-2xl border border-line px-2.5 py-1 text-[11px] text-muted transition hover:bg-clay/30 hover:text-ink"
                      >
                        清空
                      </button>
                    )}
                  </div>
                )}
                <input
                  ref={imageInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  className="hidden"
                  onChange={handlePickImage}
                />
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onCompositionStart={() => {
                    isComposingRef.current = true
                  }}
                  onCompositionEnd={() => {
                    isComposingRef.current = false
                  }}
                  onKeyDown={(event) => {
                    const nativeEvent = event.nativeEvent as KeyboardEvent & {
                      isComposing?: boolean
                      keyCode?: number
                    }
                    const isComposing =
                      isComposingRef.current ||
                      nativeEvent.isComposing ||
                      nativeEvent.keyCode === 229
                    if (isComposing) return
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      void submit()
                    }
                  }}
                  rows={1}
                  placeholder="描述你的目的地、日期、预算和旅行偏好..."
                  className="max-h-36 min-h-[54px] w-full resize-none bg-transparent px-4 pb-0 pt-3 text-[15px] leading-6 text-ink outline-none placeholder:text-muted/70"
                />
                <div className="flex items-center justify-between gap-3 px-1 pb-0.5 pt-1">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => imageInputRef.current?.click()}
                      disabled={pendingImages.some((p) => p.status === 'uploading') || isStreaming}
                      className={[
                        'inline-flex h-9 shrink-0 items-center gap-1.5 rounded-3xl border px-3 text-[12px] font-medium transition',
                        pendingImages.some((p) => p.status === 'uploading') || isStreaming
                          ? 'cursor-not-allowed border-line bg-paper/50 text-muted/40'
                          : pendingImages.length > 0
                            ? 'border-clayDeep/35 bg-sage/45 text-moss shadow-quiet'
                            : 'border-line bg-paper/70 text-muted hover:border-clayDeep/30 hover:text-ink',
                      ].join(' ')}
                      aria-pressed={pendingImages.length > 0}
                      title={
                        pendingImages.length > 0
                          ? `已附带 ${pendingImages.length} 张图片，点击可继续选择`
                          : '上传图片（支持多选、拖拽、粘贴），让我识别其中的景点'
                      }
                    >
                      {pendingImages.some((p) => p.status === 'uploading') ? (
                        <Loader2 className="animate-spin" size={15} />
                      ) : (
                        <ImageIcon size={15} className={pendingImages.length > 0 ? 'text-moss' : ''} />
                      )}
                      <span>{pendingImages.length > 0 ? `已附图(${pendingImages.length})` : '识景点'}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeepThinking((prev) => !prev)}
                      className={[
                        'inline-flex h-9 shrink-0 items-center gap-1.5 rounded-3xl border px-3 text-[12px] font-medium transition',
                        deepThinking
                          ? 'border-clayDeep/35 bg-sage/45 text-moss shadow-quiet'
                          : 'border-line bg-paper/70 text-muted hover:border-clayDeep/30 hover:text-ink',
                      ].join(' ')}
                      aria-pressed={deepThinking}
                      title={deepThinking ? '深度思考已开启，模型会先推理再回答' : '开启深度思考，模型会先推理再回答'}
                    >
                      <Sparkles
                        size={15}
                        className={deepThinking ? 'text-moss' : ''}
                      />
                      <span>深度思考</span>
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setWebSearch((prev) => {
                          const next = !prev
                          if (next) setKnowledgeSource('local') // 与云知识库互斥
                          return next
                        })
                      }
                      disabled={knowledgeSource === 'cloud'}
                      className={[
                        'inline-flex h-9 shrink-0 items-center gap-1.5 rounded-3xl border px-3 text-[12px] font-medium transition',
                        knowledgeSource === 'cloud'
                          ? 'cursor-not-allowed border-line bg-paper/50 text-muted/40'
                          : webSearch
                            ? 'border-clayDeep/35 bg-sage/45 text-moss shadow-quiet'
                            : 'border-line bg-paper/70 text-muted hover:border-clayDeep/30 hover:text-ink',
                      ].join(' ')}
                      aria-pressed={webSearch}
                      title={
                        knowledgeSource === 'cloud'
                          ? '云知识库模式下不可用（与联网搜索互斥）'
                          : webSearch
                            ? '联网搜索已开启，每轮先用 Tavily 检索并把来源注入回答'
                            : '开启联网搜索，回答会引用最新网页并标注来源编号'
                      }
                    >
                      <Globe
                        size={15}
                        className={webSearch && knowledgeSource !== 'cloud' ? 'text-moss' : ''}
                      />
                      <span>联网搜索</span>
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setKnowledgeSource((prev) => {
                          const next = prev === 'local' ? 'cloud' : 'local'
                          if (next === 'cloud') setWebSearch(false) // 与联网搜索互斥
                          return next
                        })
                      }
                      className={[
                        'inline-flex h-9 shrink-0 items-center gap-1.5 rounded-3xl border px-3 text-[12px] font-medium transition',
                        knowledgeSource === 'cloud'
                          ? 'border-clayDeep/35 bg-clay/70 text-ink shadow-quiet'
                          : 'border-line bg-paper/70 text-muted hover:border-clayDeep/30 hover:text-ink',
                      ].join(' ')}
                      aria-pressed={knowledgeSource === 'cloud'}
                      title={
                        knowledgeSource === 'cloud'
                          ? '当前使用云知识库（阿里云百炼），点击切换回本地知识库'
                          : '当前使用本地知识库，点击切换到云知识库（阿里云百炼）'
                      }
                    >
                      {knowledgeSource === 'cloud' ? <Cloud size={15} /> : <Database size={15} />}
                      <span>{knowledgeSource === 'cloud' ? '云知识库' : '本地知识库'}</span>
                      <ArrowLeftRight size={12} className="text-muted/70" />
                    </button>
                    <button
                      type="button"
                      onClick={toggleVoiceInput}
                      disabled={!voiceSupported || isStreaming}
                      className={[
                        'inline-flex h-9 shrink-0 items-center gap-1.5 rounded-3xl border px-3 text-[12px] font-medium transition',
                        !voiceSupported || isStreaming
                          ? 'cursor-not-allowed border-line bg-paper/50 text-muted/40'
                          : isVoiceListening
                            ? 'border-clayDeep/35 bg-clay/70 text-ink shadow-quiet'
                            : 'border-line bg-paper/70 text-muted hover:border-clayDeep/30 hover:text-ink',
                      ].join(' ')}
                      aria-pressed={isVoiceListening}
                      title={
                        voiceSupported
                          ? isVoiceListening
                            ? '正在听写，点击结束语音输入'
                            : '点击开始语音输入'
                          : '当前浏览器不支持语音识别，请使用 Chrome 或 Edge'
                      }
                    >
                      {isVoiceListening ? (
                        <MicOff size={15} className="text-clayDeep" />
                      ) : (
                        <Mic size={15} />
                      )}
                      <span>{isVoiceListening ? '听写中' : '语音输入'}</span>
                    </button>
                  </div>
                  <button
                    type="submit"
                    disabled={(!input.trim() && pendingImages.filter((p) => p.status === 'ready').length === 0) || isStreaming}
                    className="grid h-11 w-11 shrink-0 place-items-center rounded-3xl bg-ink text-paper shadow-quiet transition hover:translate-y-[-1px] disabled:cursor-not-allowed disabled:bg-muted/40"
                    aria-label="发送"
                  >
                    {isStreaming ? <Loader2 className="animate-spin" size={18} /> : <ArrowUp size={18} />}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>

        {/* ===== Right Map Panel：由工具调用按需出现 ===== */}
        {mapVisible && (
          <aside
            className="group fixed inset-0 z-50 h-[100dvh] w-screen overflow-hidden bg-paper shadow-soft md:relative md:inset-auto md:z-auto md:h-full md:w-auto md:shrink-0 md:border-l md:border-line/60 md:bg-paper/35 md:backdrop-blur-sm md:transition-[width] md:duration-150 md:ease-out"
            style={{ width: typeof window !== 'undefined' && window.innerWidth >= 768 ? mapWidth : undefined }}
            aria-label="路线地图"
          >
            <button
              type="button"
              onPointerDown={handleMapResizeStart}
              onPointerMove={handleMapResizeMove}
              className="absolute left-0 top-0 z-20 hidden h-full w-4 -translate-x-1/2 cursor-col-resize place-items-center text-muted/45 outline-none transition hover:text-clayDeep focus-visible:text-clayDeep md:grid"
              title="拖动调整聊天与地图宽度"
              aria-label="拖动调整聊天与地图宽度"
            >
              <span className="grid h-16 w-3 place-items-center rounded-full bg-paper/90 shadow-quiet ring-1 ring-line/70">
                <GripVertical size={13} />
              </span>
            </button>
            <div className="relative flex h-full flex-col">
              <div className="absolute right-3 top-3 z-10 flex gap-2">
                <button
                  type="button"
                  onClick={closeMap}
                  className="grid h-8 w-8 place-items-center rounded-2xl bg-paper/85 text-muted shadow-quiet transition hover:bg-paper hover:text-ink"
                  title="隐藏地图"
                  aria-label="隐藏地图"
                >
                  <PanelRightClose size={15} />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    mapPanelRef.current?.clear()
                    setLatestMapPayloads([])
                    setMapVisible(false)
                  }}
                  className="grid h-8 w-8 place-items-center rounded-2xl bg-paper/85 text-muted shadow-quiet transition hover:bg-paper hover:text-ink"
                  title="清空并关闭地图"
                  aria-label="清空并关闭地图"
                >
                  <X size={14} />
                </button>
              </div>
              <MapPanel ref={mapPanelRef} routes={latestMapPayloads} />
            </div>
          </aside>
        )}
      </div>
    </main>
  )
}

function MessageBubble({
  message,
  index,
  showThinkingDetails,
  isStreaming: parentIsStreaming,
  onShowMap,
  onInterruptDecision,
}: {
  message: ChatMessage
  index: number
  showThinkingDetails: boolean
  isStreaming: boolean
  onShowMap?: (payloads: MapPayload[] | MapPayload) => void
  onInterruptDecision?: (decision: boolean) => void
}) {
  const isUser = message.role === 'user'
  const parsedContent = isUser ? { answer: message.content, reasoning: '' } : splitReasoningContent(message.content)
  const displayAnswer = !isUser && !message.thinkingSteps ? stripSingleAgentProcessText(parsedContent.answer) : parsedContent.answer
  const displayTrace =
    !isUser && parsedContent.reasoning
      ? appendReasoningTextStep(message.thinkingTrace, parsedContent.reasoning)
      : message.thinkingTrace
  // 工具返回的卡片（网页/来源/行程/导出/地图入口）在流式输出期间会遮挡正文，
  // 推迟到本条消息流式结束后再渲染；数据本身仍照常在流式中写入 message。
  const showToolCards = !isUser && !parentIsStreaming

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
          'max-w-[92%] text-[15px] md:max-w-[86%] xl:max-w-[82%]',
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
        {!isUser && displayTrace && !message.thinkingSteps && (
          <ThinkingPanel trace={displayTrace} forceOpen={showThinkingDetails} />
        )}
        {!isUser && message.thinkingSteps && (parentIsStreaming || message.thinkingSteps.length > 0) && (
          <ReactThinkingBlock steps={message.thinkingSteps} isStreaming={parentIsStreaming} />
        )}
        {showToolCards &&
          message.webSources &&
          message.webSources.status === 'success' &&
          message.webSources.sources.length > 0 && (
            <WebSearchTrace bundle={message.webSources} />
          )}
        {isUser ? (
          <div>
            {/* 多图网格展示 */}
            {message.image_previews && message.image_previews.length > 1 && (
              <div className="mb-2 grid grid-cols-3 gap-2">
                {message.image_previews.map((preview, idx) => (
                  <a
                    key={idx}
                    href={preview}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block"
                  >
                    <img
                      src={preview}
                      alt={`用户上传图片 ${idx + 1}`}
                      className="h-24 w-full rounded-2xl object-cover shadow-quiet transition hover:opacity-80"
                    />
                  </a>
                ))}
              </div>
            )}
            {/* 单图展示 */}
            {message.image_preview && !(message.image_previews && message.image_previews.length > 1) && (
              <img
                src={message.image_preview}
                alt="用户上传的图片"
                className="mb-2 max-h-56 w-auto rounded-3xl object-cover shadow-quiet"
              />
            )}
            <p className="whitespace-pre-wrap leading-7">{message.content}</p>
          </div>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            className="markdown-body"
            components={citationMarkdownComponents(message.id)}
          >
            {withCitationLinks(displayAnswer || ' ', Boolean(message.webSources?.sources.length))}
          </ReactMarkdown>
        )}
        {showToolCards && getMessageMapRoutes(message).length > 0 && (
          <MapRevealButton payloads={getMessageMapRoutes(message)} onShowMap={onShowMap} />
        )}
        {showToolCards && message.itinerary && (
          <ItineraryCard itinerary={message.itinerary} />
        )}
        {showToolCards && message.exports && message.exports.length > 0 && (
          <ExportLinks exports={message.exports} />
        )}
        {showToolCards && message.webSources && (
          <SourcesPanel messageId={message.id} bundle={message.webSources} />
        )}
        {!isUser && message.pendingInterrupt && (
          <InterruptBar
            interrupt={message.pendingInterrupt}
            onDecision={(decision) => onInterruptDecision?.(decision)}
          />
        )}
      </div>
    </motion.article>
  )
}

function InterruptBar({
  interrupt,
  onDecision,
}: {
  interrupt: PendingInterrupt
  onDecision: (decision: boolean) => void
}) {
  const disabled = interrupt.status !== 'pending'
  return (
    <div className="mt-3 rounded-3xl border border-clayDeep/30 bg-clay/30 px-4 py-3 shadow-quiet">
      <div className="mb-2 flex items-center gap-2 text-[12px] font-medium text-clayDeep">
        <Sparkles size={13} /> 需要你确认这个操作
      </div>
      <div className="text-sm text-ink">{interrupt.summary}</div>
      <details className="mt-1 text-xs text-muted">
        <summary className="cursor-pointer select-none">查看详情</summary>
        <pre className="mt-2 max-h-44 overflow-auto rounded-2xl bg-paper/80 p-3 text-[11px] leading-5 text-ink soft-scrollbar">
          {JSON.stringify(interrupt.details, null, 2)}
        </pre>
      </details>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onDecision(true)}
          className="rounded-2xl bg-ink px-4 py-1.5 text-[12px] text-paper shadow-quiet transition hover:bg-clayDeep disabled:cursor-not-allowed disabled:bg-muted/40"
        >
          {interrupt.status === 'approved' ? '已同意' : '同意,继续'}
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onDecision(false)}
          className="rounded-2xl border border-line bg-paper px-4 py-1.5 text-[12px] text-muted transition hover:bg-canvas disabled:cursor-not-allowed"
        >
          {interrupt.status === 'rejected' ? '已拒绝' : '取消'}
        </button>
      </div>
    </div>
  )
}

// 把答案里的 [n] 转成 markdown 链接 [n](wb-cite:n)，由下面的自定义 a 组件渲染成可点击角标。
function withCitationLinks(text: string, hasSources: boolean): string {
  if (!hasSources) return text
  return text.replace(/\[(\d{1,2})\]/g, '[$1](wb-cite:$1)')
}

function scrollToCitation(messageId: string, n: string) {
  // 来源面板默认折叠:先请求展开,等卡片渲染出来(下一宏任务)再滚动高亮。
  window.dispatchEvent(new CustomEvent('wb-cite-jump', { detail: { messageId } }))
  setTimeout(() => {
    const el = document.getElementById(`wb-src-${messageId}-${n}`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.remove('wb-cite-flash')
    void el.offsetWidth // 触发重排以重启动画
    el.classList.add('wb-cite-flash')
  }, 0)
}

function citationMarkdownComponents(messageId: string): Components {
  return {
    p({ children }) {
      return <p>{highlightAssistantText(children)}</p>
    },
    li({ children }) {
      return <li>{highlightAssistantText(children)}</li>
    },
    td({ children }) {
      return <td>{highlightAssistantText(children)}</td>
    },
    th({ children }) {
      return <th>{highlightAssistantText(children)}</th>
    },
    a({ href, children, ...props }) {
      const h = typeof href === 'string' ? href : ''
      if (h.startsWith('wb-cite:')) {
        const n = h.slice('wb-cite:'.length)
        return (
          <sup>
            <button
              type="button"
              onClick={() => scrollToCitation(messageId, n)}
              className="mx-0.5 rounded bg-clay/60 px-1 text-[10px] font-semibold text-clayDeep transition hover:bg-clay"
              title={`查看来源 ${n}`}
            >
              {n}
            </button>
          </sup>
        )
      }
      return (
        <a href={h} target="_blank" rel="noopener noreferrer" {...props}>
          {children}
        </a>
      )
    },
  }
}

function highlightAssistantText(children: ReactNode): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child === 'string') return highlightKeyText(child)
    return child
  })
}

function highlightKeyText(text: string): ReactNode {
  const tokens = splitKeyText(text)
  if (tokens.length === 1 && !tokens[0].highlight) return text
  return tokens.map((token, index) =>
    token.highlight ? (
      <span key={`${token.text}-${index}`} className="wb-keymark">
        {token.text}
      </span>
    ) : (
      token.text
    ),
  )
}

function splitKeyText(text: string): Array<{ text: string; highlight: boolean }> {
  const keyPattern =
    /((?:¥|￥)?\d+(?:\.\d+)?\s*(?:[-–—~至到]\s*(?:¥|￥)?\d+(?:\.\d+)?)\s*(?:元|万元|km|公里|米|分钟|小时|天|晚|次|个地点|个停靠点|条|人|℃|°C|%|级)|(?:¥|￥)?\d+(?:\.\d+)?\s?(?:元|万元|km|公里|米|分钟|小时|天|晚|次|个地点|个停靠点|条|人|℃|°C|%|级)|(?:\d{1,2}:\d{2})|(?:\d{1,2}\s?[月]\s?\d{1,2}\s?(?:日|号)?)|(?:上午|下午|晚上|中午|早上)?\s?\d{1,2}\s?点(?:\d{1,2}\s?分)?|(?:预算|费用|门票|交通|住宿|餐饮|时间|距离|用时|天气|温度|开放时间|注意|建议|路线|地点|方案|结论|风险|推荐|重点)(?=[:：]))/gi
  const parts: Array<{ text: string; highlight: boolean }> = []
  let lastIndex = 0
  for (const match of text.matchAll(keyPattern)) {
    const value = match[0]
    const index = match.index ?? 0
    if (index > lastIndex) {
      parts.push({ text: text.slice(lastIndex, index), highlight: false })
    }
    parts.push({ text: value, highlight: true })
    lastIndex = index + value.length
  }
  if (lastIndex < text.length) {
    parts.push({ text: text.slice(lastIndex), highlight: false })
  }
  return parts
}

// 思考过程里的「联网检索」块:两种模式都展示网页 URL（满足硬性要求）。
function WebSearchTrace({ bundle }: { bundle: WebSourceBundle }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="mb-3 overflow-hidden rounded-3xl border border-sage/50 bg-[#F4F8F1] shadow-quiet">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition hover:bg-[#E8F0E0]"
        aria-expanded={open}
      >
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-2xl bg-sage/55 text-moss">
          <Globe size={16} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[13px] font-medium text-ink">联网检索</span>
          <span className="block truncate text-xs text-muted">
            “{bundle.query}” · 命中 {bundle.sources.length} 个网页
          </span>
        </span>
        <ChevronDown
          size={16}
          className={`shrink-0 text-muted transition ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <ol className="space-y-1.5 border-t border-sage/30 px-3 py-2">
          {bundle.sources.map((s) => (
            <li key={s.n} className="flex gap-2 text-xs leading-5">
              <span className="shrink-0 font-medium text-moss">[{s.n}]</span>
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="min-w-0 break-all text-muted hover:text-clayDeep"
                title={s.title}
              >
                {s.url}
              </a>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function ExportLinks({ exports }: { exports: ExportInfo[] }) {
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {exports.map((info) => (
        <a
          key={`${info.itinerary_id}-${info.format}`}
          href={resolveDownloadUrl(info.download_url)}
          download={info.filename}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-2xl bg-ink px-3 py-1.5 text-[12px] text-paper shadow-quiet transition hover:translate-y-[-1px] hover:bg-clayDeep"
        >
          <Download size={12} />
          下载 {info.format.toUpperCase()} · {info.size_text}
        </a>
      ))}
    </div>
  )
}

function MapRevealButton({
  payloads,
  onShowMap,
}: {
  payloads: MapPayload[]
  onShowMap?: (payloads: MapPayload[]) => void
}) {
  const stopCount = payloads.reduce((sum, item) => sum + item.markers.length, 0)
  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => onShowMap?.(payloads)}
        className="inline-flex items-center gap-2 rounded-3xl border border-clayDeep/20 bg-paper/90 px-4 py-2 text-[12px] font-medium text-ink shadow-quiet transition hover:-translate-y-0.5 hover:border-clayDeep/35 hover:bg-[#F8F6F1]"
      >
        <Compass size={14} className="text-clayDeep" />
        {payloads.length > 1 ? '查看每日路线地图' : '查看路线地图'}
        <span className="rounded-full bg-clay/45 px-2 py-0.5 text-[10px] text-clayDeep">
          {payloads.length > 1 ? `${payloads.length} 天` : `${stopCount} 个地点`}
        </span>
      </button>
    </div>
  )
}

function getMessageMapRoutes(message: ChatMessage): MapPayload[] {
  if (message.mapPayloads?.length) return message.mapPayloads
  return message.mapPayload ? [message.mapPayload] : []
}

function appendMapRouteToMessage(message: ChatMessage, route: MapPayload): ChatMessage {
  const nextRoutes = upsertMapRoute(getMessageMapRoutes(message), route)

  return {
    ...message,
    mapPayload: nextRoutes[0],
    mapPayloads: nextRoutes,
    thinkingTrace: upsertMapTraceStep(
      message.thinkingTrace,
      route.route_name,
      route.markers.length,
    ),
  }
}

function upsertMapRoute(routes: MapPayload[], route: MapPayload): MapPayload[] {
  const routeKey = getMapRouteKey(route)
  return routes.some((item) => getMapRouteKey(item) === routeKey)
    ? routes.map((item) => (getMapRouteKey(item) === routeKey ? route : item))
    : [...routes, route]
}

function getMapRouteKey(route: MapPayload) {
  return `${route.route_name || 'route'}:${route.markers.map((marker) => marker.name).join('>')}`
}

function dropTrailingDuplicateUserMessage(messages: ChatMessage[], content: string) {
  const last = messages[messages.length - 1]
  if (last?.role === 'user' && last.content.trim() === content) {
    return messages.slice(0, -1)
  }
  return messages
}

function dropTransientAssistantStatus(messages: ChatMessage[]) {
  const cleaned = [...messages]
  while (cleaned.length > 0) {
    const last = cleaned[cleaned.length - 1]
    if (
      last.role === 'assistant' &&
      last.content.includes('已收到问题，正在连接模型') &&
      !last.itinerary &&
      !last.mapPayload &&
      !last.mapPayloads?.length &&
      !last.exports?.length &&
      !last.webSources &&
      !last.pendingInterrupt &&
      !(last.thinkingSteps?.length)
    ) {
      cleaned.pop()
      continue
    }
    break
  }
  return cleaned
}

function buildStreamCallbacks(
  assistantId: string,
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>,
  conversationIdRef: React.MutableRefObject<string | null>,
  setLatestMapPayloads?: React.Dispatch<React.SetStateAction<MapPayload[]>>,
) {
  return {
    onDelta: (delta: string) => {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? { ...message, content: stripToolMarkup(message.content + delta, false) }
            : message,
        ),
      )
    },
    onAnswerChunk: (text: string) => {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? { ...message, content: stripToolMarkup(message.content + text, false) }
            : message,
        ),
      )
    },
    onStatus: (payload: { detail?: string }) => {
      const detail = payload.detail?.trim()
      if (!detail) return
      setMessages((current) =>
        current.map((message) => {
          if (message.id !== assistantId) return message
          if (message.thinkingSteps) {
            const steps = message.thinkingSteps.length
              ? message.thinkingSteps
              : [{ type: 'thought' as const, text: detail, step: 0 }]
            return { ...message, thinkingSteps: steps }
          }
          return message
        }),
      )
    },
    onError: (message: string) => {
      const visibleMessage = message.replace(/^深度思考出错:\s*/u, '').trim()
      setMessages((current) =>
        current.map((item) =>
          item.id === assistantId
            ? {
                ...item,
                content:
                  item.content.trim() ||
                  `抱歉，这次回答在生成过程中中断了。\n\n${visibleMessage || '请稍后重试。'}`,
              }
            : item,
        ),
      )
    },
    onThinkingStart: () => {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId ? { ...message, thinkingSteps: [] } : message,
        ),
      )
    },
    onThought: (text: string, step: number) => {
      setMessages((current) =>
        current.map((message) => {
          if (message.id !== assistantId) return message
          const steps = [...(message.thinkingSteps ?? [])]
          const last = steps[steps.length - 1]
          // 流式追加到同一步的 thought
          if (last && last.type === 'thought' && last.step === step) {
            steps[steps.length - 1] = { ...last, text: (last.text ?? '') + text }
          } else {
            steps.push({ type: 'thought', text, step })
          }
          return { ...message, thinkingSteps: steps }
        }),
      )
    },
    onAction: (payload: { tool: string; args: Record<string, unknown>; tool_call_id: string; step: number }) => {
      setMessages((current) =>
        current.map((message) => {
          if (message.id !== assistantId) return message
          const steps = [...(message.thinkingSteps ?? [])]
          steps.push({
            type: 'action',
            tool: payload.tool,
            args: payload.args,
            tool_call_id: payload.tool_call_id,
            step: payload.step,
          })
          return { ...message, thinkingSteps: steps }
        }),
      )
    },
    onObservation: (payload: { tool: string; summary: string; detail?: string; tool_call_id: string }) => {
      setMessages((current) =>
        current.map((message) => {
          if (message.id !== assistantId) return message
          const steps = [...(message.thinkingSteps ?? [])]
          steps.push({
            type: 'observation',
            tool: payload.tool,
            summary: payload.summary,
            detail: payload.detail,
            tool_call_id: payload.tool_call_id,
          })
          return { ...message, thinkingSteps: steps }
        }),
      )
    },
    onThinkingEnd: (payload: { duration_ms: number; steps: number; summary: string }) => {
      // 可以留作后续使用,暂时只更新 thinkingTrace summary
      setMessages((current) =>
        current.map((message) => {
          if (message.id !== assistantId) return message
          const trace = message.thinkingTrace
            ? { ...message.thinkingTrace, summary: payload.summary || `思考完成 (${(payload.duration_ms / 1000).toFixed(1)}s)` }
            : message.thinkingTrace
          return { ...message, thinkingTrace: trace }
        }),
      )
    },
    onMeta: (meta: unknown) => {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? shouldHideRagTrace(message.thinkingTrace, meta)
              ? message
              : { ...message, thinkingTrace: updateThinkingTrace(message.thinkingTrace, meta) }
            : message,
        ),
      )
    },
    onMapData: (mapPayload: MapPayload) => {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId ? appendMapRouteToMessage(message, mapPayload) : message,
        ),
      )
      setLatestMapPayloads?.((current) => upsertMapRoute(current, mapPayload))
    },
    onItinerary: (itinerary: Itinerary) => {
      setMessages((current) =>
        current.map((message) => (message.id === assistantId ? { ...message, itinerary } : message)),
      )
    },
    onWebSources: (bundle: WebSourceBundle) => {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId ? { ...message, webSources: bundle } : message,
        ),
      )
    },
    onExport: (info: ExportInfo) => {
      setMessages((current) =>
        current.map((message) => {
          if (message.id !== assistantId) return message
          const existing = message.exports ?? []
          const next = existing.filter(
            (item) =>
              !(item.itinerary_id === info.itinerary_id && item.format === info.format),
          )
          next.push(info)
          return { ...message, exports: next }
        }),
      )
    },
    onInterrupt: (payload: { thread_id: string; payload: Record<string, unknown> }) => {
      const value = payload.payload as Record<string, any>
      const interrupt: PendingInterrupt = {
        thread_id: payload.thread_id,
        tool_name: String(value.tool_name ?? ''),
        summary: String(value.summary ?? '需要你确认这一步操作'),
        details: (value.details ?? {}) as Record<string, unknown>,
        status: 'pending',
      }
      setMessages((current) =>
        current.map((m) => (m.id === assistantId ? { ...m, pendingInterrupt: interrupt } : m)),
      )
    },
    onThreadId: (threadId: string) => {
      // 我们已客户端生成并下发 conversation_id,后端通常原样回传;
      // 仍同步一次,确保 active 会话指向它。
      conversationIdRef.current = threadId
      setActiveId(threadId)
    },
  }
}

function resolveDownloadUrl(path: string): string {
  // 后端返回的是 '/api/exports/xxx'。生产环境 API_BASE 是相对路径时，直接交给 Nginx 反代。
  if (API_BASE.startsWith('/')) {
    return path
  }
  const origin = API_BASE.replace(/\/api\/?$/, '')
  return origin + path
}

function ReactThinkingBlock({ steps, isStreaming }: { steps: ThinkingStep[]; isStreaming: boolean }) {
  const [expanded, setExpanded] = useState(isStreaming)
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const wasStreamingRef = useRef(isStreaming)

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [steps, autoScroll])

  useEffect(() => {
    if (isStreaming && !wasStreamingRef.current) {
      setExpanded(true)
    } else if (wasStreamingRef.current && !isStreaming) {
      setExpanded(false)
    }
    wasStreamingRef.current = isStreaming
  }, [isStreaming])

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.target as HTMLDivElement
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 50)
  }

  const isThinking = isStreaming
  const lastThought = steps.filter((s) => s.type === 'thought').pop()

  return (
    <div className="mb-3 animate-in fade-in overflow-hidden rounded-3xl border border-sage/50 bg-[#F4F8F1] shadow-quiet duration-300">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition hover:bg-[#E8F0E0]"
        aria-expanded={expanded}
      >
        <span className="relative grid h-8 w-8 shrink-0 place-items-center rounded-2xl bg-sage/55 text-moss">
          {isThinking && (
            <span className="absolute right-0 top-0 h-2 w-2 rounded-full bg-moss animate-ping" />
          )}
          <BrainCircuit size={16} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[13px] font-medium text-ink">深度思考</span>
          <span className="block truncate text-xs text-muted">
            {isThinking ? '正在推理中…' : `已完成推理（${steps.length} 步）`}
          </span>
        </span>
        <ChevronDown
          size={16}
          className={`shrink-0 text-muted transition ${expanded ? 'rotate-180' : ''}`}
        />
      </button>

      {expanded && (
        <div
          ref={containerRef}
          onScroll={handleScroll}
          className="soft-scrollbar max-h-[320px] overflow-y-auto border-t border-sage/30 px-3 pb-3 pt-2"
        >
          <div className="space-y-1.5">
            {steps.map((s, idx) => (
              <ReactStepItem key={idx} step={s} isLast={idx === steps.length - 1} isStreaming={isThinking} />
            ))}
          </div>
          {isThinking && (
            <div className="mt-2 flex items-center gap-1.5 px-1 text-xs text-muted">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-moss" />
              思考中
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ReactStepItem({ step, isLast, isStreaming }: { step: ThinkingStep; isLast: boolean; isStreaming: boolean }) {
  const [showArgs, setShowArgs] = useState(false)

  if (step.type === 'thought') {
    return (
      <div className="flex gap-2 rounded-2xl px-2 py-1.5">
        <span className="mt-0.5 shrink-0 text-sm" aria-label="思考">💭</span>
        <p className="text-xs leading-6 text-ink">
          {step.text}
          {isLast && isStreaming && (
            <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-moss" />
          )}
        </p>
      </div>
    )
  }

  if (step.type === 'action') {
    return (
      <div className="flex gap-2 rounded-2xl px-2 py-1.5">
        <span className="mt-0.5 shrink-0 text-sm" aria-label="工具调用">🔧</span>
        <div className="min-w-0">
          <span className="text-xs font-medium text-ink">{step.tool}</span>
          <button
            type="button"
            onClick={() => setShowArgs((v) => !v)}
            className="ml-1.5 rounded-full bg-sage/30 px-2 py-0.5 text-[10px] text-moss transition hover:bg-sage/50"
          >
            {showArgs ? '收起参数' : '参数'}
          </button>
          {showArgs && step.args && (
            <pre className="mt-1 max-h-32 overflow-auto rounded-2xl bg-paper/80 p-2 text-[10px] leading-4 text-muted soft-scrollbar">
              {JSON.stringify(step.args, null, 2)}
            </pre>
          )}
        </div>
      </div>
    )
  }

  if (step.type === 'observation') {
    return (
      <div className="flex gap-2 rounded-2xl px-2 py-1.5">
        <span className="mt-0.5 shrink-0 text-sm" aria-label="工具结果">📊</span>
        <div className="min-w-0">
          <p className="whitespace-pre-wrap text-xs leading-6 text-muted">{step.summary || '已获取结果'}</p>
          {step.detail && (
            <pre className="mt-1 whitespace-pre-wrap rounded-2xl bg-paper/80 px-2.5 py-1.5 text-[11px] leading-5 text-ink soft-scrollbar">
              {step.detail}
            </pre>
          )}
        </div>
      </div>
    )
  }

  return null
}

function ThinkingPanel({ trace, forceOpen }: { trace: ThinkingTrace; forceOpen: boolean }) {
  const [expanded, setExpanded] = useState(forceOpen)
  const doneCount = trace.steps.filter((step) => step.status === 'done').length
  const activeStep = trace.steps.find((step) => step.status === 'active')
  const title = getTracePanelTitle(trace)

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
          <span className="block text-[13px] font-medium text-ink">{title}</span>
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

function getTracePanelTitle(trace: ThinkingTrace) {
  if (trace.runtime === 'react' && trace.steps.some((step) => step.id === 'reasoning-text')) return '深度思考'
  if (trace.runtime === 'bailian_app') return '云端检索'
  if (trace.steps.some((step) => step.id.startsWith('tool-'))) return '任务进度'
  return '检索过程'
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

function createPendingTrace(knowledgeSource: 'local' | 'cloud' = 'local'): ThinkingTrace {
  if (knowledgeSource === 'cloud') {
    return {
      provider: 'bailian_app',
      runtime: 'bailian_app',
      summary: '等待百炼应用返回回答流程',
      steps: [
        {
          id: 'query',
          title: '整理用户问题',
          status: 'active',
          detail: '正在把本轮问题整理为百炼应用可接收的输入。',
        },
        {
          id: 'route',
          title: '调用百炼云知识库应用',
          status: 'pending',
          detail: '等待后端携带 API Key、业务空间和应用 ID 调用百炼应用。',
        },
        {
          id: 'context',
          title: '云端检索与生成',
          status: 'pending',
          detail: '百炼应用会在云端自行选择知识库、检索资料并生成回答；本地系统无法读取其内部召回片段。',
        },
        {
          id: 'prompt',
          title: '接收百炼应用回答',
          status: 'pending',
          detail: '等待百炼应用的流式输出接入本地对话窗口。',
        },
      ],
    }
  }

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

  if (payload.rag_trace_visible === false) {
    return trace
  }

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
  const cloudMode = payload.rag_cloud_mode === 'bailian_app'

  if (cloudMode) {
    return {
      ...trace,
      provider,
      model,
      runtime,
      summary: '已交由百炼应用完成知识库检索与回答生成',
      steps: [
        {
          id: 'query',
          title: '整理用户问题',
          status: 'done',
          detail: query || '已把本轮问题发送给百炼应用。',
          data: query ? { rag_query: query } : undefined,
        },
        {
          id: 'route',
          title: '调用百炼云知识库应用',
          status: 'done',
          detail: reasoning || '百炼应用会根据自身配置选择模型、知识库和回答流程。',
          data: compactRecord({
            cloud_mode: '百炼应用',
            app_id: model,
            workspace: '由后端配置',
            internal_trace_available: false,
          }),
        },
        {
          id: 'context',
          title: '云端检索与生成',
          status: 'done',
          detail: '云知识库的检索路由、召回片段和上下文注入发生在百炼应用内部，当前接口不会返回这些明细。',
          data: compactRecord({
            visible_to_local_system: false,
            note: '前端仅展示百炼应用返回的最终回答。',
          }),
        },
        {
          id: 'prompt',
          title: '接收百炼应用回答',
          status: 'done',
          detail: '系统已接入百炼应用的流式输出，并把回答按本地 SSE 协议展示给用户。',
          data: compactRecord({
            stream_bridge: 'DashScope SSE -> WanderBot SSE',
          }),
        },
        ...trace.steps.filter((step) => step.id.startsWith('tool-')),
      ],
    }
  }

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

function shouldHideRagTrace(existingTrace: ThinkingTrace | undefined, payload: unknown): boolean {
  if (!isRecord(payload)) return false
  if (payload.rag_trace_visible !== false) return false
  return !existingTrace
}

function upsertMapTraceStep(
  trace: ThinkingTrace | undefined,
  routeName: string,
  stopCount: number,
): ThinkingTrace {
  const baseTrace = trace ?? createPendingTrace()
  return upsertTraceStep(baseTrace, {
    id: 'map-data',
    title: '路线地图已准备',
    status: 'done',
    detail: `已准备"${routeName}"路线地图，共 ${stopCount} 个停靠点。回答完成后可点击按钮查看。`,
    data: { route_name: routeName, stops: stopCount },
  })
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

  let answer = stripToolMarkup(content)
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
    answer: stripToolMarkup(answer).trim(),
    reasoning: reasoningParts.join('\n\n'),
  }
}

const DSML_TOOL_MARKUP_RE =
  /&lt;\s*\|\s*\|\s*DSML[\s\S]*?(?:tool_calls?&gt;|$)|<\s*\|\s*\|\s*DSML\s*\|\s*\|\s*tool_calls?\b[\s\S]*?<\/\s*\|\s*\|\s*DSML\s*\|\s*\|\s*tool_calls?\s*>|<\s*\|\s*\|\s*DSML[\s\S]*?(?:tool_calls?>|\|\s*\|\s*tool_calls?\s*>|$)|<\/?\s*(?:\|\s*\|\s*DSML\s*\|\s*\||｜\s*｜\s*DSML\s*｜\s*｜)\s*(?:tool_calls?|invoke|parameter|function_calls?)\b[^>]*>|<[^>]*｜[^>]*>|<\/?\s*｜?｜?\s*DSML\s*｜?｜?[^>]*>|<\/?\s*(?:invoke|parameter|tool_calls?|function_calls?)\b[^>]*>|｜+\s*DSML\s*｜+|\|\s*\|\s*DSML\s*\|\s*\|/gi
const DSML_PARTIAL_MARKUP_RE =
  /<\s*\|\s*\|\s*DSML[\s\S]*$|&lt;\s*\|\s*\|\s*DSML[\s\S]*$|<\s*｜\s*｜\s*DSML[\s\S]*$/i

function stripToolMarkup(text: string, trim = true) {
  if (!text) return text
  const cleaned = text
    .replace(DSML_TOOL_MARKUP_RE, '')
    .replace(DSML_PARTIAL_MARKUP_RE, '')
    .replace(
      /(?:让我先查实时信息。|让我们先查实时信息。|我先查实时信息。)?\s*(?:\{["']?状态["']?\s*:\s*["']?(?:success|failed)[\s\S]*?["']?使用提示["']?\s*:\s*["'][^"']*["']\s*\})+/gi,
      '',
    )
    .replace(
      /(?:\{["']?status["']?\s*:\s*["']?(?:success|failed)[\s\S]*?["']?results?["']?\s*:\s*\[[\s\S]*?\]\s*\})+/gi,
      '',
    )
    .replace(/�/g, '')
  return trim ? cleaned.trim() : cleaned
}

function stripSingleAgentProcessText(text: string) {
  if (!text) return text
  return text
    .replace(/(?:第[一二三四五六七八九十]+轮|第一轮|第二轮|第三轮|第四轮|第五轮)[^。！？\n]{0,40}[。！？\n]?/g, '')
    .replace(/(?:我先|先查|接下来|然后我会|我会先|我先把|我先查)[^。！？\n]{0,80}[。！？\n]?/g, '')
    .replace(/(?:正在|准备|开始|继续)[^。！？\n]{0,30}[。！？\n]?/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
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
