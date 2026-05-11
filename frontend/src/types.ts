export type Role = 'user' | 'assistant' | 'system'

export type ChatMessage = {
  id: string
  role: Role
  content: string
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

export type SystemPrompt = {
  id: number
  name: string
  content: string
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
