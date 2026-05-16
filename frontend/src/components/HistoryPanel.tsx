/**
 * HistoryPanel:左侧会话历史抽屉。
 *
 * 纯展示组件,不碰 localStorage——数据与动作全部由 App.tsx 经 props 注入,
 * 这样 Phase B 换后端时本组件零改动。
 */
import { History, MessageSquarePlus, Trash2, X } from 'lucide-react'
import type { ConversationMeta } from '../lib/conversationStore'

function relativeTime(ts: number): string {
  const diff = Date.now() - ts
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小时前`
  const day = Math.floor(hr / 24)
  if (day < 30) return `${day} 天前`
  return new Date(ts).toLocaleDateString()
}

export default function HistoryPanel({
  open,
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onClose,
}: {
  open: boolean
  conversations: ConversationMeta[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  onClose: () => void
}) {
  if (!open) return null
  return (
    <aside
      className="hidden h-full w-72 shrink-0 flex-col overflow-hidden border-r border-line/60 bg-paper/40 backdrop-blur-sm md:flex"
      aria-label="会话历史"
    >
      <div className="flex items-center justify-between border-b border-line/60 px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-medium text-ink">
          <History size={16} className="text-clayDeep" />
          会话历史
        </div>
        <button
          type="button"
          onClick={onClose}
          className="grid h-7 w-7 place-items-center rounded-2xl bg-paper/85 text-muted shadow-quiet transition hover:bg-paper hover:text-ink"
          title="收起历史"
          aria-label="收起历史"
        >
          <X size={14} />
        </button>
      </div>

      <div className="px-3 py-3">
        <button
          type="button"
          onClick={onNew}
          className="flex w-full items-center gap-2 rounded-3xl bg-ink px-4 py-2.5 text-sm text-paper shadow-quiet transition hover:translate-y-[-1px] hover:bg-clayDeep"
        >
          <MessageSquarePlus size={15} />
          新建对话
        </button>
      </div>

      <div className="soft-scrollbar flex-1 overflow-y-auto px-3 pb-4">
        {conversations.length === 0 ? (
          <p className="px-2 pt-6 text-center text-xs text-muted">
            还没有历史对话。开始聊天后会自动保存在本浏览器。
          </p>
        ) : (
          <ul className="space-y-1.5">
            {conversations.map((conv) => {
              const active = conv.id === activeId
              return (
                <li key={conv.id}>
                  <div
                    className={[
                      'group flex items-center gap-2 rounded-2xl px-3 py-2.5 text-left transition',
                      active
                        ? 'bg-clay/60 text-ink shadow-quiet'
                        : 'text-muted hover:bg-paper/80 hover:text-ink',
                    ].join(' ')}
                  >
                    <button
                      type="button"
                      onClick={() => onSelect(conv.id)}
                      className="min-w-0 flex-1 text-left"
                      title={conv.title}
                    >
                      <div className="truncate text-[13px] font-medium">{conv.title}</div>
                      <div className="mt-0.5 text-[11px] text-muted/80">
                        {relativeTime(conv.updatedAt)}
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(conv.id)}
                      className="grid h-7 w-7 shrink-0 place-items-center rounded-xl text-muted/60 opacity-0 transition hover:bg-paper hover:text-red-700 group-hover:opacity-100"
                      title="删除此对话"
                      aria-label="删除此对话"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </aside>
  )
}
