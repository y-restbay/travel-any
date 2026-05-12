import type {
  AdminConfig,
  ChatMessage,
  EmbeddingConfig,
  IngestResult,
  LLMConfig,
  RAGDebugResult,
  RAGStats,
  SystemPrompt,
  TestResult,
  ToolItem,
  ToolPreset,
} from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:6688/api'

export async function getAdminConfig(): Promise<AdminConfig> {
  const response = await fetch(`${API_BASE}/admin/config`)
  if (!response.ok) {
    throw new Error('Unable to load admin config')
  }
  return response.json()
}

export async function saveAdminConfig(payload: {
  llm_config: Partial<AdminConfig['llm_config']>
  system_prompt: Partial<AdminConfig['system_prompt']>
}): Promise<AdminConfig> {
  const response = await fetch(`${API_BASE}/admin/config`, {
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
  const response = await fetch(`${API_BASE}/admin/config/test`, {
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
  const response = await fetch(`${API_BASE}/admin/config/llm`)
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
  const response = await fetch(`${API_BASE}/admin/config/llm`, {
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
    is_active: boolean
  }>,
): Promise<LLMConfig> {
  const response = await fetch(`${API_BASE}/admin/config/llm/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Unable to update LLM config')
  return response.json()
}

export async function deleteLLMConfig(id: number): Promise<void> {
  const response = await fetch(`${API_BASE}/admin/config/llm/${id}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Unable to delete LLM config')
}

// ---- Embedding Config Management ----

export async function listEmbeddingConfigs(): Promise<EmbeddingConfig[]> {
  const response = await fetch(`${API_BASE}/admin/config/embeddings`)
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
  const response = await fetch(`${API_BASE}/admin/config/embeddings`, {
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
  const response = await fetch(`${API_BASE}/admin/config/embeddings/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Unable to update embedding config')
  return response.json()
}

export async function deleteEmbeddingConfig(id: number): Promise<void> {
  const response = await fetch(`${API_BASE}/admin/config/embeddings/${id}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Unable to delete embedding config')
}

export async function testEmbeddingConfig(params: {
  provider: string
  model_name: string
  api_key: string
  base_url: string
}): Promise<TestResult> {
  const response = await fetch(`${API_BASE}/admin/config/embeddings/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!response.ok) throw new Error('Embedding test failed')
  return response.json()
}

// ---- System Prompt Management ----

export async function listSystemPrompts(): Promise<SystemPrompt[]> {
  const response = await fetch(`${API_BASE}/admin/config/prompts`)
  if (!response.ok) throw new Error('Unable to load system prompts')
  return response.json()
}

export async function createSystemPrompt(payload: {
  name: string
  content: string
  knowledge_scope?: string[]
  is_active?: boolean
}): Promise<SystemPrompt> {
  const response = await fetch(`${API_BASE}/admin/config/prompts`, {
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
  const response = await fetch(`${API_BASE}/admin/config/prompts/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Unable to update system prompt')
  return response.json()
}

export async function deleteSystemPrompt(id: number): Promise<void> {
  const response = await fetch(`${API_BASE}/admin/config/prompts/${id}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Unable to delete system prompt')
}

// ---- Tools ----

export async function listTools(): Promise<ToolItem[]> {
  const response = await fetch(`${API_BASE}/admin/tools`)
  if (!response.ok) throw new Error('Unable to load tools')
  return response.json()
}

export async function getToolPresets(): Promise<ToolPreset[]> {
  const response = await fetch(`${API_BASE}/admin/tools/presets`)
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
  const response = await fetch(`${API_BASE}/admin/tools`, {
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
  const response = await fetch(`${API_BASE}/admin/tools/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Unable to update tool')
  return response.json()
}

export async function deleteTool(id: number): Promise<void> {
  const response = await fetch(`${API_BASE}/admin/tools/${id}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Unable to delete tool')
}

// ---- RAG Knowledge Base ----

export async function getRagStats(): Promise<RAGStats> {
  const response = await fetch(`${API_BASE}/rag/stats`)
  if (!response.ok) throw new Error('Unable to load RAG stats')
  return response.json()
}

export async function rebuildRagVectorIndex(): Promise<RAGStats> {
  const response = await fetch(`${API_BASE}/rag/rebuild-vector-index`, { method: 'POST' })
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
  const response = await fetch(`${API_BASE}/rag/ingest/text`, {
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

  const response = await fetch(`${API_BASE}/rag/ingest/upload`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) throw new Error('Unable to upload RAG file')
  return response.json()
}

export async function debugRag(query: string, top_k = 5): Promise<RAGDebugResult> {
  const response = await fetch(`${API_BASE}/rag/debug`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, top_k }),
  })
  if (!response.ok) throw new Error('Unable to run RAG debug')
  return response.json()
}

export async function streamChat(
  messages: Pick<ChatMessage, 'role' | 'content'>[],
  onDelta: (content: string) => void,
  onMeta?: (payload: unknown) => void,
) {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ messages }),
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
      if (event === 'delta') onDelta(payload.content ?? '')
      if (event === 'meta') onMeta?.(payload)
      if (event === 'done') return
    }
  }
}
