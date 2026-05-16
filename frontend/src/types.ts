export type Role = 'user' | 'assistant' | 'system'

export type ChatMessage = {
  id: string
  role: Role
  content: string
  thinkingTrace?: ThinkingTrace
  thinkingSteps?: ThinkingStep[]  // 深度思考模式
  itinerary?: Itinerary
  mapPayload?: MapPayload
  mapPayloads?: MapPayload[]
  exports?: ExportInfo[]
  pendingInterrupt?: PendingInterrupt
  webSources?: WebSourceBundle
}

export type WebSource = {
  n: number
  title: string
  url: string
  snippet: string
  published?: string
}

export type WebSourceBundle = {
  query: string
  status: 'success' | 'empty' | 'failed'
  sources: WebSource[]
  answer_summary?: string
  reason?: string
}

export type PendingInterrupt = {
  thread_id: string
  tool_name: string
  summary: string
  details: Record<string, unknown>
  status: 'pending' | 'approved' | 'rejected'
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

export type AgentRuntime = 'tools' | 'supervisor'
export type AgentMode = 'single' | 'deep_thinking'

export type ThinkingStep = {
  type: 'thought' | 'action' | 'observation'
  text?: string       // thought 内容
  tool?: string       // action/observation 的工具名
  args?: Record<string, unknown>  // action 参数
  tool_call_id?: string
  summary?: string    // observation 摘要
  step?: number
}

export type LLMConfig = {
  id: number
  provider: string
  model_name: string
  api_key: string
  base_url: string
  runtime: AgentRuntime
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

export type SystemLogEntry = {
  id: number
  ts: number
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'
  logger: string
  message: string
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
  routes: Array<'vector' | 'keyword' | 'graph' | 'cloud'>
  reasoning: string
  route_weights: Partial<Record<'vector' | 'keyword' | 'graph' | 'cloud', number>>
  decision_source: 'llm' | 'rules' | 'rules_fallback' | 'cloud'
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

// ---- Map / Directions ----
export type MapMarker = {
  name: string
  lng: number
  lat: number
  order: number
}

export type MapBounds = {
  sw: [number, number]
  ne: [number, number]
}

export type MapRouteSummary = {
  distance_km: number
  duration_min: number
  cost_yuan: number | null
}

export type MapPayload = {
  type: 'route'
  route_name: string
  mode: 'driving' | 'walking'
  markers: MapMarker[]
  polyline: Array<[number, number]>
  bounds: MapBounds | null
  summary: MapRouteSummary
}

// ---- Itinerary / Export ----
export type ItineraryMeta = {
  destination?: string
  people?: string
  budget?: string
  accommodation?: string
  preferences?: string
  transport_mode?: string
}

export type ItineraryWeatherEntry = {
  date?: string
  condition?: string
  temp?: string
  tip?: string
}

export type ItineraryScheduleItem = {
  time?: string
  type?: 'depart' | 'visit' | 'meal' | 'transit' | 'return' | string
  place?: string
  note?: string
  duration_min?: number
  cost?: number
  ticket?: number
  from?: string
  to?: string
  highlights?: string[]
  tips?: string
  cuisine?: string
  must_try?: string[]
}

export type ItineraryDayCost = {
  tickets?: number
  meals?: number
  transport?: number
  total?: number
}

export type ItineraryDay = {
  day_number: number
  title: string
  theme: string
  schedule: ItineraryScheduleItem[]
  day_cost: ItineraryDayCost
}

export type ItineraryTotalBudget = {
  tickets?: number
  meals?: number
  transport?: number
  accommodation?: number
  total?: number
}

export type Itinerary = {
  type: 'itinerary'
  itinerary_id: string
  trip_title: string
  trip_dates: string
  summary: string
  meta: ItineraryMeta
  weather_summary: ItineraryWeatherEntry[]
  days: ItineraryDay[]
  total_budget: ItineraryTotalBudget
  important_notes: string[]
}

export type ExportInfo = {
  type: 'export_ready'
  itinerary_id: string
  format: 'pdf' | 'docx'
  filename: string
  download_url: string
  size_bytes: number
  size_text: string
  trip_title: string
}
