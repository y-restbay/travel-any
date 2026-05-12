import { useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { Activity, Binary, Brain, Database, FileText, Plug, SearchCheck, Server, Shield } from 'lucide-react'
import ShellNav from '../components/ShellNav'
import EmbeddingConfigModule from './admin/EmbeddingConfigModule'
import KnowledgeBaseModule from './admin/KnowledgeBaseModule'
import LLMConfigModule from './admin/LLMConfigModule'
import RAGVerificationModule from './admin/RAGVerificationModule'
import SystemPromptModule from './admin/SystemPromptModule'
import ToolsModule from './admin/ToolsModule'
import MonitorModule from './admin/MonitorModule'

type AdminModule = 'llm' | 'embedding' | 'prompt' | 'knowledge' | 'rag' | 'tools' | 'monitor'

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
  { key: 'monitor', label: '监控大盘', desc: 'Prometheus / Grafana', icon: Activity },
]

export default function Admin() {
  const [activeModule, setActiveModule] = useState<AdminModule>('llm')
  const current = useMemo(() => modules.find((item) => item.key === activeModule) ?? modules[0], [activeModule])

  return (
    <main className="min-h-screen px-4 pb-20 pt-28 text-ink">
      <ShellNav />
      <section className="mx-auto grid w-full max-w-6xl gap-6 lg:grid-cols-[280px_1fr]">
        <aside className="lg:sticky lg:top-28 lg:self-start">
          <motion.div
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            className="rounded-4xl bg-paper/90 p-4 shadow-soft backdrop-blur"
          >
            <div className="mb-5 rounded-4xl bg-[#F8F6F1] p-4">
              <div className="flex items-center gap-3">
                <span className="grid h-11 w-11 place-items-center rounded-3xl bg-clay text-ink">
                  <Shield size={19} />
                </span>
                <div>
                  <p className="font-display text-xl">Admin</p>
                  <p className="text-xs text-muted">模块化控制台</p>
                </div>
              </div>
              <p className="mt-4 text-sm leading-6 text-muted">
                每个模块只负责一件事，方便后续继续接入登录、文件库、评测和更多工具。
              </p>
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
                    className={`flex w-full items-center gap-3 rounded-3xl px-4 py-3 text-left transition ${
                      active ? 'bg-ink text-paper shadow-quiet' : 'text-muted hover:bg-clay/30 hover:text-ink'
                    }`}
                  >
                    <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-2xl ${active ? 'bg-paper/15' : 'bg-[#F8F6F1]'}`}>
                      <Icon size={17} />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-medium">{item.label}</span>
                      <span className={`block truncate text-xs ${active ? 'text-paper/65' : 'text-muted/80'}`}>{item.desc}</span>
                    </span>
                  </button>
                )
              })}
            </nav>
          </motion.div>
        </aside>

        <section className="min-w-0">
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
            <div className="mb-3 flex w-fit items-center gap-2 rounded-3xl bg-sage px-4 py-2 text-sm text-moss">
              <Brain size={16} />
              WanderBot Control Plane
            </div>
            <h1 className="font-display text-4xl leading-tight md:text-5xl">{current.label}</h1>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-muted">
              {current.desc}
            </p>
          </motion.div>

          {activeModule === 'llm' && <LLMConfigModule />}
          {activeModule === 'embedding' && <EmbeddingConfigModule />}
          {activeModule === 'prompt' && <SystemPromptModule />}
          {activeModule === 'knowledge' && <KnowledgeBaseModule />}
          {activeModule === 'rag' && <RAGVerificationModule />}
          {activeModule === 'tools' && <ToolsModule />}
          {activeModule === 'monitor' && <MonitorModule />}
        </section>
      </section>
    </main>
  )
}
