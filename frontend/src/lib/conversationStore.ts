/**
 * 会话持久化存储层（Phase A：localStorage 实现）。
 *
 * 这是一个「接缝」模块:App.tsx 和 HistoryPanel 只依赖这里导出的函数签名。
 * Phase B 接后端时,只需把本文件内部实现换成 fetch 调用,接口不变,上层零改动。
 *
 * 持久化字段刻意只保留可序列化且对「恢复对话」有意义的部分:
 *   id / role / content / itinerary / mapPayload(s) / exports / thinkingSteps / thinkingTrace
 * 丢弃 pendingInterrupt(重启后无法 resume,是坏数据)与地图(ref 渲染,不在本期)。
 *
 * localStorage ~5MB,行程卡 JSON 每条几 KB,这里做最近 50 条软上限 + 手动删除,
 * 个人本地原型足够;真要无限历史/跨设备请走 Phase B 后端方案。
 */
import type { ChatMessage } from '../types'

const INDEX_KEY = 'wanderbot:conversations'
const ACTIVE_KEY = 'wanderbot:active_conv'
const CONV_PREFIX = 'wanderbot:conv:'
const MAX_CONVERSATIONS = 50
const TITLE_MAX = 24

export type ConversationMeta = {
  id: string
  title: string
  updatedAt: number
}

export type PersistedMessage = Pick<
  ChatMessage,
  'id' | 'role' | 'content' | 'itinerary' | 'mapPayload' | 'mapPayloads' | 'exports' | 'thinkingSteps' | 'thinkingTrace' | 'webSources'
>

function readJSON<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return fallback
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

function writeJSON(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* 配额满 / 隐私模式禁用 localStorage:静默放弃,绝不影响渲染 */
  }
}

function removeKey(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    /* 同上 */
  }
}

/** 只保留需要持久化的字段,顺带剔除 intro 占位消息。 */
function strip(messages: ChatMessage[]): PersistedMessage[] {
  return messages
    .filter((m) => m.id !== 'intro')
    .map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      itinerary: m.itinerary,
      mapPayload: m.mapPayload,
      mapPayloads: m.mapPayloads,
      exports: m.exports,
      thinkingSteps: m.thinkingSteps,
      thinkingTrace: m.thinkingTrace,
      webSources: m.webSources,
    }))
}

function deriveTitle(messages: ChatMessage[]): string {
  const firstUser = messages.find((m) => m.role === 'user' && m.content.trim())
  const text = firstUser?.content.trim().replace(/\s+/g, ' ') ?? ''
  if (!text) return '新对话'
  return text.length > TITLE_MAX ? `${text.slice(0, TITLE_MAX)}…` : text
}

export function listConversations(): ConversationMeta[] {
  const index = readJSON<ConversationMeta[]>(INDEX_KEY, [])
  return [...index].sort((a, b) => b.updatedAt - a.updatedAt)
}

export function getActiveId(): string | null {
  try {
    return window.localStorage.getItem(ACTIVE_KEY)
  } catch {
    return null
  }
}

export function setActiveId(id: string): void {
  try {
    window.localStorage.setItem(ACTIVE_KEY, id)
  } catch {
    /* 同上 */
  }
}

/** 生成新会话 id 并设为当前;此刻不写索引,等首条真实保存时再建条目,避免空会话刷屏。 */
export function createConversation(): string {
  const id = crypto.randomUUID()
  setActiveId(id)
  return id
}

export function loadConversation(id: string): PersistedMessage[] | null {
  const raw = readJSON<PersistedMessage[] | null>(CONV_PREFIX + id, null)
  return Array.isArray(raw) ? raw : null
}

/**
 * 保存会话。仅当至少有一条用户消息时才落盘并建/更新索引条目。
 * 同步执行,switch/new/delete 切换前可直接调用以「flush 当前会话」。
 */
export function saveConversation(id: string, messages: ChatMessage[]): void {
  const hasUser = messages.some((m) => m.role === 'user' && m.content.trim())
  if (!hasUser) return

  writeJSON(CONV_PREFIX + id, strip(messages))

  const index = readJSON<ConversationMeta[]>(INDEX_KEY, [])
  const meta: ConversationMeta = { id, title: deriveTitle(messages), updatedAt: Date.now() }
  const next = [meta, ...index.filter((c) => c.id !== id)].sort(
    (a, b) => b.updatedAt - a.updatedAt,
  )

  // 软上限:超出的最旧会话连同其消息一并清除。
  const kept = next.slice(0, MAX_CONVERSATIONS)
  for (const dropped of next.slice(MAX_CONVERSATIONS)) {
    removeKey(CONV_PREFIX + dropped.id)
  }
  writeJSON(INDEX_KEY, kept)
}

export function deleteConversation(id: string): void {
  const index = readJSON<ConversationMeta[]>(INDEX_KEY, [])
  writeJSON(
    INDEX_KEY,
    index.filter((c) => c.id !== id),
  )
  removeKey(CONV_PREFIX + id)
}
