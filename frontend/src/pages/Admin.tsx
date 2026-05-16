import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { Activity, Binary, ChevronLeft, ChevronRight, Database, FileText, LockKeyhole, LogOut, PanelLeftClose, PanelLeftOpen, Plug, ScrollText, SearchCheck, Server, ShieldCheck } from 'lucide-react'
import EmbeddingConfigModule from './admin/EmbeddingConfigModule'
import KnowledgeBaseModule from './admin/KnowledgeBaseModule'
import LLMConfigModule from './admin/LLMConfigModule'
import RAGVerificationModule from './admin/RAGVerificationModule'
import SystemPromptModule from './admin/SystemPromptModule'
import ToolsModule from './admin/ToolsModule'
import MonitorModule from './admin/MonitorModule'
import LogsModule from './admin/LogsModule'
import { clearAdminToken, getAdminToken, loginAdmin } from '../api'

type AdminModule = 'llm' | 'embedding' | 'prompt' | 'knowledge' | 'rag' | 'tools' | 'logs' | 'monitor'
const ADMIN_SIDEBAR_STORAGE_KEY = 'wanderbot:admin-sidebar-collapsed'
const ADMIN_AUTH_STORAGE_KEY = 'wanderbot:admin-authenticated'

const modules: Array<{
  key: AdminModule
  label: string
  desc: string
  icon: typeof Server
}> = [
  { key: 'llm', label: '大模型配置', desc: 'Provider, key, base URL', icon: Server },
  { key: 'embedding', label: '向量模型配置', desc: 'Embedding provider 和 key', icon: Binary },
  { key: 'prompt', label: 'System Prompt', desc: '角色、边界、文件范围', icon: FileText },
  { key: 'knowledge', label: '知识库文件', desc: '上传、切片、入库', icon: Database },
  { key: 'rag', label: 'RAG 验证', desc: '四步链路可观测', icon: SearchCheck },
  { key: 'tools', label: '工具集成', desc: '外部工具和凭证', icon: Plug },
  { key: 'logs', label: '日志管理', desc: '提问 / 回答 / 工具报错', icon: ScrollText },
  { key: 'monitor', label: '监控大盘', desc: 'Prometheus / Grafana', icon: Activity },
]

export default function Admin() {
  const [authenticated, setAuthenticated] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.sessionStorage.getItem(ADMIN_AUTH_STORAGE_KEY) === '1' && Boolean(getAdminToken())
  })
  const [activeModule, setActiveModule] = useState<AdminModule>('llm')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const current = useMemo(() => modules.find((item) => item.key === activeModule) ?? modules[0], [activeModule])
  const monitorActive = activeModule === 'monitor'
  const effectiveSidebarCollapsed = sidebarCollapsed || monitorActive

  useEffect(() => {
    if (typeof window === 'undefined') return
    const raw = window.localStorage.getItem(ADMIN_SIDEBAR_STORAGE_KEY)
    setSidebarCollapsed(raw === '1')
  }, [])

  function toggleSidebar() {
    setSidebarCollapsed((current) => {
      const next = !current
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(ADMIN_SIDEBAR_STORAGE_KEY, next ? '1' : '0')
      }
      return next
    })
  }

  function handleLogin() {
    setAuthenticated(true)
    if (typeof window !== 'undefined') {
      window.sessionStorage.setItem(ADMIN_AUTH_STORAGE_KEY, '1')
    }
  }

  function handleLogout() {
    setAuthenticated(false)
    if (typeof window !== 'undefined') {
      window.sessionStorage.removeItem(ADMIN_AUTH_STORAGE_KEY)
      clearAdminToken()
    }
  }

  if (!authenticated) {
    return <AdminLogin onLogin={handleLogin} />
  }

  if (monitorActive) {
    return (
      <main className="min-h-screen px-2 pb-20 pt-4 text-ink xl:px-3">
        <section className="mx-auto w-full max-w-none">
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-3 flex items-end justify-between gap-4 px-1">
            <div>
              <h1 className="font-display text-2xl leading-tight md:text-3xl">{current.label}</h1>
              <p className="mt-2 text-sm text-muted">{current.desc}</p>
            </div>
            <div className="hidden shrink-0 items-center gap-2 md:flex">
              <button
                type="button"
                onClick={() => {
                  setActiveModule('llm')
                  setSidebarCollapsed(false)
                }}
                className="inline-flex items-center gap-2 rounded-3xl bg-paper/90 px-4 py-2.5 text-sm text-muted shadow-soft transition hover:text-ink"
              >
                <ChevronLeft size={16} />
                返回配置
              </button>
              <button
                type="button"
                onClick={handleLogout}
                className="inline-flex items-center gap-2 rounded-3xl bg-paper/90 px-4 py-2.5 text-sm text-muted shadow-soft transition hover:text-ink"
              >
                <LogOut size={16} />
                退出登录
              </button>
            </div>
          </motion.div>
          <MonitorModule />
        </section>
      </main>
    )
  }

  return (
    <main className="min-h-screen px-4 pb-20 pt-5 text-ink xl:px-6">
      <section
        className={`mx-auto grid w-full transition-[grid-template-columns] duration-300 ${
          `max-w-[1520px] gap-6 ${
            sidebarCollapsed ? 'lg:grid-cols-[92px_minmax(0,1fr)]' : 'lg:grid-cols-[248px_minmax(0,1fr)]'
          }`
        }`}
      >
        <aside className="lg:sticky lg:top-5 lg:self-start">
          <motion.div
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            className="rounded-4xl bg-paper/90 p-3 shadow-soft backdrop-blur"
          >
            <div className={`mb-3 flex ${effectiveSidebarCollapsed ? 'justify-center' : 'justify-end'} rounded-3xl bg-[#F8F6F1] p-2`}>
              <button
                type="button"
                onClick={toggleSidebar}
                title={effectiveSidebarCollapsed ? '展开侧边栏' : '隐藏侧边栏'}
                className="grid h-9 w-9 shrink-0 place-items-center rounded-2xl text-muted transition hover:bg-paper hover:text-ink"
              >
                {effectiveSidebarCollapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
              </button>
            </div>

            <nav className="space-y-2">
              {modules.map((item) => {
                const Icon = item.icon
                const active = item.key === activeModule
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => setActiveModule(item.key)}
                    className={`flex w-full items-center rounded-3xl py-3 text-left transition ${
                      effectiveSidebarCollapsed ? 'justify-center px-2' : 'gap-3 px-4'
                    } ${
                      active ? 'bg-ink text-paper shadow-quiet' : 'text-muted hover:bg-clay/30 hover:text-ink'
                    }`}
                    title={effectiveSidebarCollapsed ? item.label : undefined}
                  >
                    <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-2xl ${active ? 'bg-paper/15' : 'bg-[#F8F6F1]'}`}>
                      <Icon size={17} />
                    </span>
                    {!effectiveSidebarCollapsed && (
                      <span className="min-w-0">
                        <span className="block text-sm font-medium">{item.label}</span>
                        <span className={`block truncate text-xs ${active ? 'text-paper/65' : 'text-muted/80'}`}>{item.desc}</span>
                      </span>
                    )}
                  </button>
                )
              })}
            </nav>
          </motion.div>
        </aside>

        <section className="min-w-0">
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className={`flex items-end justify-between gap-4 ${monitorActive ? 'mb-3 px-1' : 'mb-4'}`}
          >
            <div>
              <h1 className={`font-display leading-tight ${monitorActive ? 'text-2xl md:text-3xl' : 'text-3xl md:text-4xl'}`}>
                {current.label}
              </h1>
              <p className="mt-2 text-sm text-muted">{current.desc}</p>
            </div>
            <div className="hidden shrink-0 items-center gap-2 lg:flex">
              <button
                type="button"
                onClick={toggleSidebar}
                className={`inline-flex items-center gap-2 rounded-3xl bg-paper/90 px-4 py-2.5 text-sm text-muted shadow-soft transition hover:text-ink ${
                  monitorActive ? 'invisible pointer-events-none' : ''
                }`}
              >
                {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
                {sidebarCollapsed ? '展开导航' : '收起导航'}
              </button>
              <button
                type="button"
                onClick={handleLogout}
                className="inline-flex items-center gap-2 rounded-3xl bg-paper/90 px-4 py-2.5 text-sm text-muted shadow-soft transition hover:text-ink"
              >
                <LogOut size={16} />
                退出登录
              </button>
            </div>
          </motion.div>

          {activeModule === 'llm' && <LLMConfigModule />}
          {activeModule === 'embedding' && <EmbeddingConfigModule />}
          {activeModule === 'prompt' && <SystemPromptModule />}
          {activeModule === 'knowledge' && <KnowledgeBaseModule />}
          {activeModule === 'rag' && <RAGVerificationModule />}
          {activeModule === 'tools' && <ToolsModule />}
          {activeModule === 'logs' && <LogsModule />}
        </section>
      </section>
    </main>
  )
}

function AdminLogin({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    try {
      await loginAdmin(username.trim(), password)
      setError('')
      onLogin()
    } catch {
      setError('账号或密码不正确')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="min-h-screen px-4 py-8 text-ink">
      <section className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-6xl items-center justify-center">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.26 }}
          className="grid w-full max-w-5xl overflow-hidden rounded-[2rem] bg-paper/90 shadow-soft backdrop-blur lg:grid-cols-[1fr_420px]"
        >
          <div className="flex min-h-[420px] flex-col justify-between bg-[#F8F6F1] p-8 md:p-10">
            <div>
              <span className="grid h-12 w-12 place-items-center rounded-3xl bg-sage text-moss">
                <ShieldCheck size={22} />
              </span>
              <h1 className="mt-6 font-display text-3xl leading-tight md:text-4xl">管理员入口</h1>
              <p className="mt-4 max-w-xl text-sm leading-7 text-muted">
                后台配置、工具凭证、知识库与监控面板已从用户聊天界面分离。登录后再进入管理工作台。
              </p>
            </div>
            <div className="mt-8 grid gap-3 text-xs leading-5 text-muted sm:grid-cols-3">
              <p className="rounded-3xl bg-paper/75 p-4">配置大模型、Embedding 与系统提示词。</p>
              <p className="rounded-3xl bg-paper/75 p-4">管理知识库文件、工具和 RAG 验证链路。</p>
              <p className="rounded-3xl bg-paper/75 p-4">查看 Prometheus / Grafana 运维大盘。</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col justify-center p-7 md:p-8">
            <div className="mb-6 flex items-center gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-2xl bg-clay/55 text-clayDeep">
                <LockKeyhole size={18} />
              </span>
              <div>
                <h2 className="text-lg font-semibold">登录管理后台</h2>
                <p className="mt-1 text-xs text-muted">账号密码由后端环境变量校验，管理接口会自动携带登录令牌。</p>
              </div>
            </div>

            <label className="block">
              <span className="mb-2 block px-1 text-sm font-medium text-muted">管理员账号</span>
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                className="w-full rounded-3xl border border-line bg-[#F8F6F1] px-4 py-3 text-sm outline-none transition focus:border-clayDeep/40 focus:bg-paper"
                placeholder="admin"
              />
            </label>

            <label className="mt-4 block">
              <span className="mb-2 block px-1 text-sm font-medium text-muted">密码</span>
              <input
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                autoComplete="current-password"
                className="w-full rounded-3xl border border-line bg-[#F8F6F1] px-4 py-3 text-sm outline-none transition focus:border-clayDeep/40 focus:bg-paper"
                placeholder="admin123"
              />
            </label>

            {error && <p className="mt-3 rounded-3xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

            <button
              type="submit"
              disabled={submitting}
              className="mt-6 inline-flex items-center justify-center gap-2 rounded-3xl bg-ink px-5 py-3 text-sm font-medium text-paper shadow-quiet transition hover:-translate-y-0.5"
            >
              <ShieldCheck size={16} />
              {submitting ? '正在登录...' : '进入管理后台'}
            </button>
          </form>
        </motion.div>
      </section>
    </main>
  )
}
