import type {
  AdminConfig,
  ChatMessage,
  EmbeddingConfig,
  ExportInfo,
  IngestResult,
  Itinerary,
  LLMConfig,
  MapPayload,
  RAGDebugResult,
  RAGStats,
  SystemLogEntry,
  SystemPrompt,
  TestResult,
  ToolItem,
  ToolPreset,
  WebSourceBundle,
} from './types'

const DEFAULT_API_BASE = import.meta.env.PROD ? '/api' : 'http://127.0.0.1:6688/api'
export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE).replace(/\/$/, '')
export const ADMIN_TOKEN_STORAGE_KEY = 'wanderbot:admin-token'

export function resolveApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) {
    return path
  }
  if (path.startsWith('/api/')) {
    return API_BASE.endsWith('/api') ? `${API_BASE}${path.slice(4)}` : path
  }
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

export function setAdminToken(token: string) {
  window.sessionStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, token)
}

export function clearAdminToken() {
  window.sessionStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY)
}

export function getAdminToken() {
  return window.sessionStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) ?? ''
}

function adminHeaders(extra?: HeadersInit): HeadersInit {
  const token = getAdminToken()
  return {
    ...(extra ?? {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

async function adminFetch(path: string, init: RequestInit = {}) {
  return fetch(resolveApiUrl(path), {
    ...init,
    headers: adminHeaders(init.headers),
  })
}

export async function loginAdmin(username: string, password: string): Promise<{ token: string; username: string }> {
  const response = await fetch(resolveApiUrl('/admin/login'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!response.ok) throw new Error('账号或密码不正确')
  const data = await response.json()
  setAdminToken(data.token)
  return data
}

export async function getAdminConfig(): Promise<AdminConfig> {
  const response = await fetch(resolveApiUrl('/admin/config'))
  if (!response.ok) {
    throw new Error('Unable to load admin config')
  }
  return response.json()
}

export async function saveAdminConfig(payload: {
  llm_config: Partial<AdminConfig['llm_config']>
  system_prompt: Partial<AdminConfig['system_prompt']>
}): Promise<AdminConfig> {
  const response = await adminFetch('/admin/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error('Unable to save admin config')
  }
  return response.json()
}

export async function testLLMConfig(params: {
  provider: string
  model_name: string
  api_key: string
  base_url: string
}): Promise<TestResult> {
  const response = await adminFetch('/admin/config/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!response.ok) {
    throw new Error('Test connection failed')
  }
  return response.json()
}

// ---- LLM Config Management ----

export async function listLLMConfigs(): Promise<LLMConfig[]> {
  const response = await adminFetch('/admin/config/llm')
  if (!response.ok) throw new Error('Unable to load LLM configs')
  return response.json()
}

export async function createLLMConfig(payload: {
  provider: string
  model_name: string
  api_key?: string
  base_url?: string
  is_active?: boolean
}): Promise<LLMConfig> {
  const response = await adminFetch('/admin/config/llm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Unable to create LLM config')
  return response.json()
}

export async function updateLLMConfig(
  id: number,
  payload: Partial<{
    provider: string
    model_name: string
    api_key: string
    base_url: string
    runtime: 'tools' | 'supervisor'
    is_active: boolean
  }>,
): Promise<LLMConfig> {
  const response = await adminFetch(`/admin/config/llm/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Unable to update LLM config')
  return response.json()
}

export async function deleteLLMConfig(id: number): Promise<void> {
  const response = await adminFetch(`/admin/config/llm/${id}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Unable to delete LLM config')
}

// ---- Embedding Config Management ----

export async function listEmbeddingConfigs(): Promise<EmbeddingConfig[]> {
  const response = await adminFetch('/admin/config/embeddings')
  if (!response.ok) throw new Error('Unable to load embedding configs')
  return response.json()
}

export async function createEmbeddingConfig(payload: {
  provider: string
  model_name: string
  api_key?: string
  base_url?: string
  is_active?: boolean
}): Promise<EmbeddingConfig> {
  const response = await adminFetch('/admin/config/embeddings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Unable to create embedding config')
  return response.json()
}

export async function updateEmbeddingConfig(
  id: number,
  payload: Partial<{
    provider: string
    model_name: string
    api_key: string
    base_url: string
    is_active: boolean
  }>,
): Promise<EmbeddingConfig> {
  const response = await adminFetch(`/admin/config/embeddings/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Unable to update embedding config')
  return response.json()
}

export async function deleteEmbeddingConfig(id: number): Promise<void> {
  const response = await adminFetch(`/admin/config/embeddings/${id}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Unable to delete embedding config')
}

export async function testEmbeddingConfig(params: {
  provider: string
  model_name: string
  api_key: string
  base_url: string
}): Promise<TestResult> {
  const response = await adminFetch('/admin/config/embeddings/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!response.ok) throw new Error('Embedding test failed')
  return response.json()
}

// ---- System Prompt Management ----

export async function listSystemPrompts(): Promise<SystemPrompt[]> {
  const response = await adminFetch('/admin/config/prompts')
  if (!response.ok) throw new Error('Unable to load system prompts')
  return response.json()
}

export async function createSystemPrompt(payload: {
  name: string
  content: string
  knowledge_scope?: string[]
  is_active?: boolean
}): Promise<SystemPrompt> {
  const response = await adminFetch('/admin/config/prompts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Unable to create system prompt')
  return response.json()
}

export async function updateSystemPrompt(
  id: number,
  payload: Partial<{
    name: string
    content: string
    knowledge_scope: string[]
    is_active: boolean
  }>,
): Promise<SystemPrompt> {
  const response = await adminFetch(`/admin/config/prompts/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Unable to update system prompt')
  return response.json()
}

export async function deleteSystemPrompt(id: number): Promise<void> {
  const response = await adminFetch(`/admin/config/prompts/${id}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Unable to delete system prompt')
}

// ---- Tools ----

export async function listTools(): Promise<ToolItem[]> {
  const response = await adminFetch('/admin/tools')
  if (!response.ok) throw new Error('Unable to load tools')
  return response.json()
}

export async function getToolPresets(): Promise<ToolPreset[]> {
  const response = await adminFetch('/admin/tools/presets')
  if (!response.ok) throw new Error('Unable to load tool presets')
  return response.json()
}

export async function createTool(payload: {
  name: string
  label: string
  description: string
  tool_type: string
  config: Record<string, string>
  is_active?: boolean
}): Promise<ToolItem> {
  const response = await adminFetch('/admin/tools', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Unable to create tool')
  return response.json()
}

export async function updateTool(
  id: number,
  payload: Partial<{
    name: string
    label: string
    description: string
    tool_type: string
    config: Record<string, string>
    is_active: boolean
  }>,
): Promise<ToolItem> {
  const response = await adminFetch(`/admin/tools/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Unable to update tool')
  return response.json()
}

export async function deleteTool(id: number): Promise<void> {
  const response = await adminFetch(`/admin/tools/${id}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Unable to delete tool')
}

// ---- RAG Knowledge Base ----

export async function getRagStats(): Promise<RAGStats> {
  const response = await adminFetch('/rag/stats')
  if (!response.ok) throw new Error('Unable to load RAG stats')
  return response.json()
}

export async function rebuildRagVectorIndex(): Promise<RAGStats> {
  const response = await adminFetch('/rag/rebuild-vector-index', { method: 'POST' })
  if (!response.ok) throw new Error('Unable to rebuild vector index')
  return response.json()
}

export async function ingestText(payload: {
  text: string
  filename?: string
  doc_type?: string
  source?: string
  metadata?: Record<string, unknown>
}): Promise<IngestResult> {
  const response = await adminFetch('/rag/ingest/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Unable to ingest text')
  return response.json()
}

export async function uploadRagFile(
  file: File,
  options: { doc_type?: string; source?: string; metadata?: Record<string, unknown> } = {},
): Promise<IngestResult> {
  const form = new FormData()
  form.append('file', file)
  if (options.doc_type) form.append('doc_type', options.doc_type)
  if (options.source) form.append('source', options.source)
  if (options.metadata && Object.keys(options.metadata).length > 0) {
    form.append('metadata_json', JSON.stringify(options.metadata))
  }

  const response = await adminFetch('/rag/ingest/upload', {
    method: 'POST',
    body: form,
  })
  if (!response.ok) throw new Error('Unable to upload RAG file')
  return response.json()
}

export async function debugRag(query: string, top_k = 5): Promise<RAGDebugResult> {
  const response = await adminFetch('/rag/debug', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, top_k }),
  })
  if (!response.ok) throw new Error('Unable to run RAG debug')
  return response.json()
}

type ChatStreamCallbacks = {
  onDelta: (content: string) => void
  onError?: (message: string) => void
  onMeta?: (payload: unknown) => void
  onStatus?: (payload: { detail?: string }) => void
  onMapData?: (payload: MapPayload) => void
  onItinerary?: (payload: Itinerary) => void
  onExport?: (payload: ExportInfo) => void
  onInterrupt?: (payload: { thread_id: string; payload: Record<string, unknown> }) => void
  onThreadId?: (threadId: string) => void
  // 深度思考模式事件
  onThinkingStart?: () => void
  onThought?: (text: string, step: number) => void
  onAction?: (payload: { tool: string; args: Record<string, unknown>; tool_call_id: string; step: number }) => void
  onObservation?: (payload: { tool: string; summary: string; detail?: string; tool_call_id: string }) => void
  onThinkingEnd?: (payload: { duration_ms: number; steps: number; summary: string }) => void
  onAnswerChunk?: (text: string) => void
  onWebSources?: (payload: WebSourceBundle) => void
}

export async function streamChat(
  messages: Pick<ChatMessage, 'role' | 'content'>[],
  callbacksOrOnDelta:
    | ((content: string) => void)
    | ChatStreamCallbacks,
  legacyOnMeta?: (payload: unknown) => void,
  legacyOnMapData?: (payload: MapPayload) => void,
  legacyOnItinerary?: (payload: Itinerary) => void,
  legacyOnExport?: (payload: ExportInfo) => void,
  conversationId?: string,
  mode?: 'single' | 'deep_thinking',
  knowledgeSource?: 'local' | 'cloud',
  webSearch?: boolean,
) {
  // 兼容老式分散参数 + 新式 callback 对象两种调用形式
  const callbacks: ChatStreamCallbacks =
    typeof callbacksOrOnDelta === 'function'
      ? {
          onDelta: callbacksOrOnDelta,
          onMeta: legacyOnMeta,
          onMapData: legacyOnMapData,
          onItinerary: legacyOnItinerary,
          onExport: legacyOnExport,
        }
      : callbacksOrOnDelta

  const body: Record<string, unknown> = { messages }
  if (conversationId) body.conversation_id = conversationId
  if (mode) body.mode = mode
  if (knowledgeSource) body.knowledge_source = knowledgeSource
  if (webSearch) body.web_search = true

  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
  })

  if (!response.ok || !response.body) {
    throw new Error('Chat stream failed')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''

    for (const frame of frames) {
      const lines = frame.split('\n')
      const event = lines.find((line) => line.startsWith('event: '))?.slice(7)
      const dataLine = lines.find((line) => line.startsWith('data: '))?.slice(6)
      if (!event || !dataLine) continue

      const payload = JSON.parse(dataLine)
      if (event === 'status') callbacks.onStatus?.(payload as { detail?: string })
      if (event === 'error') {
        callbacks.onError?.(String(payload.message ?? '回答生成失败，请稍后重试'))
        return
      }
      if (event === 'delta') callbacks.onDelta(payload.content ?? '')
      if (event === 'answer_chunk') callbacks.onAnswerChunk?.(payload.text ?? '')
      if (event === 'thought') callbacks.onThought?.(payload.text ?? '', payload.step ?? 0)
      if (event === 'action') callbacks.onAction?.(payload as { tool: string; args: Record<string, unknown>; tool_call_id: string; step: number })
      if (event === 'observation') callbacks.onObservation?.(payload as { tool: string; summary: string; detail?: string; tool_call_id: string })
      if (event === 'thinking_start') callbacks.onThinkingStart?.()
      if (event === 'thinking_end') callbacks.onThinkingEnd?.(payload as { duration_ms: number; steps: number; summary: string })
      if (event === 'meta') {
        callbacks.onMeta?.(payload)
        if (payload && typeof payload === 'object' && typeof (payload as any).thread_id === 'string') {
          callbacks.onThreadId?.((payload as any).thread_id)
        }
      }
      if (event === 'web_sources') callbacks.onWebSources?.(payload as WebSourceBundle)
      if (event === 'map_data') callbacks.onMapData?.(payload as MapPayload)
      if (event === 'itinerary_data') callbacks.onItinerary?.(payload as Itinerary)
      if (event === 'export_ready') callbacks.onExport?.(payload as ExportInfo)
      if (event === 'interrupt') callbacks.onInterrupt?.(payload as { thread_id: string; payload: Record<string, unknown> })
      if (event === 'done') return
    }
  }
}

export async function resumeChat(
  conversationId: string,
  decision: boolean | string | Record<string, unknown>,
  callbacks: Omit<ChatStreamCallbacks, 'onThreadId'>,
) {
  const response = await fetch(`${API_BASE}/chat/resume`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ conversation_id: conversationId, decision }),
  })
  if (!response.ok || !response.body) {
    throw new Error('Resume chat failed')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const lines = frame.split('\n')
      const event = lines.find((line) => line.startsWith('event: '))?.slice(7)
      const dataLine = lines.find((line) => line.startsWith('data: '))?.slice(6)
      if (!event || !dataLine) continue
      const payload = JSON.parse(dataLine)
      if (event === 'status') callbacks.onStatus?.(payload as { detail?: string })
      if (event === 'error') {
        callbacks.onError?.(String(payload.message ?? '回答生成失败，请稍后重试'))
        return
      }
      if (event === 'delta') callbacks.onDelta(payload.content ?? '')
      if (event === 'meta') callbacks.onMeta?.(payload)
      if (event === 'map_data') callbacks.onMapData?.(payload as MapPayload)
      if (event === 'itinerary_data') callbacks.onItinerary?.(payload as Itinerary)
      if (event === 'export_ready') callbacks.onExport?.(payload as ExportInfo)
      if (event === 'interrupt') callbacks.onInterrupt?.(payload as { thread_id: string; payload: Record<string, unknown> })
      if (event === 'done') return
    }
  }
}

export async function getSystemLogs(params: {
  level?: string
  q?: string
  limit?: number
}): Promise<SystemLogEntry[]> {
  const qs = new URLSearchParams()
  if (params.level) qs.set('level', params.level)
  if (params.q) qs.set('q', params.q)
  if (params.limit) qs.set('limit', String(params.limit))
  const response = await adminFetch(`/admin/logs?${qs.toString()}`)
  if (!response.ok) throw new Error('Unable to load system logs')
  return response.json()
}

export async function clearSystemLogs(): Promise<void> {
  const response = await adminFetch('/admin/logs', { method: 'DELETE' })
  if (!response.ok) throw new Error('Unable to clear system logs')
}

export async function downloadSystemLogs(params: { level?: string; q?: string }): Promise<Blob> {
  const qs = new URLSearchParams()
  if (params.level) qs.set('level', params.level)
  if (params.q) qs.set('q', params.q)
  const response = await adminFetch(`/admin/logs/export?${qs.toString()}`)
  if (!response.ok) throw new Error('Unable to export system logs')
  return response.blob()
}
