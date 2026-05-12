export type Role = 'user' | 'assistant' | 'system'

export type ChatMessage = {
  id: string
  role: Role
  content: string
  thinkingTrace?: ThinkingTrace
}

export type ThinkingTraceStep = {
  id: string
  title: string
  status: 'pending' | 'active' | 'done' | 'error'
  detail: string
  data?: Record<string, unknown>
}

export type ThinkingTrace = {
  provider?: string
  model?: string
  runtime?: string
  summary?: string
  steps: ThinkingTraceStep[]
}

export type LLMConfig = {
  id: number
  provider: string
  model_name: string
  api_key: string
  base_url: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export type EmbeddingConfig = {
  id: number
  provider: string
  model_name: string
  api_key: string
  base_url: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export type SystemPrompt = {
  id: number
  name: string
  content: string
  knowledge_scope: string[]
  is_active: boolean
  created_at: string
  updated_at: string
}

export type AdminConfig = {
  llm_config: LLMConfig
  system_prompt: SystemPrompt
}

export type ToolItem = {
  id: number
  name: string
  label: string
  description: string
  tool_type: string
  config: Record<string, string>
  is_active: boolean
  created_at: string
  updated_at: string
}

export type ToolPreset = {
  name: string
  label: string
  description: string
  tool_type: string
  config: Record<string, string>
}

export type TestResult = {
  success: boolean
  latency_ms: number
  message: string
}

export type RAGDocumentSummary = {
  document_id: string
  filename: string
  chunk_count: number
  strategy?: 'long_form' | 'short_form'
  source?: string
  doc_type?: string
}

export type RAGStats = {
  chunk_count: number
  vector_count: number
  entity_count: number
  chroma_path: string
  collection_name?: string
  embedding_provider?: string
  embedding_model?: string
  is_real_embedding?: boolean
  bm25_path: string
  reindexed_chunks?: number
  documents?: RAGDocumentSummary[]
}

export type IngestResult = {
  document_id: string
  filename: string
  strategy: 'long_form' | 'short_form'
  chunk_count: number
  entity_count: number
}

export type QueryAnalysis = {
  routes: Array<'vector' | 'keyword' | 'graph'>
  reasoning: string
  route_weights: Partial<Record<'vector' | 'keyword' | 'graph', number>>
  decision_source: 'llm' | 'rules' | 'rules_fallback'
}

export type RetrievedContext = {
  chunk_id: string
  text: string
  metadata: Record<string, unknown>
  source: string
  score: number
}

export type RetrieveResult = {
  query: string
  analysis: QueryAnalysis
  contexts: RetrievedContext[]
  context_block: string
}

export type RetrievalCandidate = {
  chunk_id: string
  source: string
  score: number
  filename?: string | null
  preview: string
}

export type RAGTraceStep = {
  step: 'step_1' | 'step_2' | 'step_3' | 'step_4'
  title: string
  status: string
  detail: string
  data: Record<string, unknown>
}

export type RAGDebugResult = {
  query: string
  trace: RAGTraceStep[]
  retrieve_result: RetrieveResult
}
