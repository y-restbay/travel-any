import { FormEvent, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowUp, Loader2, MapPinned, Sparkles } from 'lucide-react'
import ShellNav from '../components/ShellNav'
import { streamChat } from '../api'
import type { ChatMessage } from '../types'

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

  async function submit(value = input) {
    const content = value.trim()
    if (!content || isStreaming) return

    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: 'user', content }
    const assistantId = crypto.randomUUID()
    const assistantMessage: ChatMessage = { id: assistantId, role: 'assistant', content: '' }
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
    <main className="flex h-screen flex-col overflow-hidden text-ink">
      <ShellNav />
      <section ref={scrollRef} onScroll={handleScroll} className="soft-scrollbar flex-1 overflow-y-auto px-4 pb-44 pt-28">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-7">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="pb-3 pt-4">
            <div className="mb-5 flex w-fit items-center gap-2 rounded-3xl bg-paper/80 px-4 py-2 text-sm text-muted shadow-quiet">
              <MapPinned size={16} />
              Travel planning, softly
            </div>
            <h1 className="max-w-2xl font-display text-4xl leading-tight md:text-6xl">
              把旅行灵感整理成可以出发的路线。
            </h1>
          </motion.div>

          {messages.map((message, index) => (
            <MessageBubble key={message.id} message={message} index={index} />
          ))}

          {isStreaming && (
            <div className="flex items-center gap-2 pl-1 text-sm text-muted">
              <Loader2 className="animate-spin" size={16} />
              WanderBot 正在整理路线
            </div>
          )}
        </div>
      </section>

      <div className="fixed bottom-0 left-0 right-0 z-20 bg-gradient-to-t from-[#F4F1EC] via-[#F4F1EC]/92 to-transparent px-4 pb-5 pt-16">
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
    </main>
  )
}

function MessageBubble({ message, index }: { message: ChatMessage; index: number }) {
  const isUser = message.role === 'user'
  return (
    <motion.article
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, delay: Math.min(index * 0.02, 0.12) }}
      className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div
        className={[
          'max-w-[88%] text-[15px] md:max-w-[78%]',
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
        {isUser ? (
          <p className="whitespace-pre-wrap leading-7">{message.content}</p>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]} className="markdown-body">
            {message.content || ' '}
          </ReactMarkdown>
        )}
      </div>
    </motion.article>
  )
}
