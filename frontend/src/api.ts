import type { AdminConfig, ChatMessage, TestResult, ToolItem, ToolPreset } from './types'

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
