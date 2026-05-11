import { FormEvent, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Check,
  KeyRound,
  Loader2,
  Plug,
  Save,
  Server,
  Shield,
  Trash2,
  Wifi,
  WifiOff,
  X,
  Plus,
  Globe,
  Search,
} from 'lucide-react'
import ShellNav from '../components/ShellNav'
import { createTool, deleteTool, getAdminConfig, getToolPresets, listTools, saveAdminConfig, testLLMConfig, updateTool } from '../api'
import type { AdminConfig, TestResult, ToolItem, ToolPreset } from '../types'

type Status = 'idle' | 'loading' | 'saving' | 'saved' | 'error'
type TestStatus = 'idle' | 'testing' | 'success' | 'error'

const emptyConfig: AdminConfig = {
  llm_config: {
    id: 0,
    provider: 'Mock',
    model_name: 'wanderbot-mock',
    api_key: '',
    base_url: '',
    is_active: true,
    created_at: '',
    updated_at: '',
  },
  system_prompt: {
    id: 0,
    name: 'WanderBot Default',
    content: '',
    is_active: true,
    created_at: '',
    updated_at: '',
  },
}

const TOOL_TYPE_ICONS: Record<string, typeof Globe> = {
  firecrawl_search: Search,
  firecrawl_scrape: Globe,
}

export default function Admin() {
  const [config, setConfig] = useState<AdminConfig>(emptyConfig)
  const [status, setStatus] = useState<Status>('loading')
  const [error, setError] = useState('')

  // Test connection state
  const [testStatus, setTestStatus] = useState<TestStatus>('idle')
  const [testResult, setTestResult] = useState<TestResult | null>(null)

  // Tool management state
  const [tools, setTools] = useState<ToolItem[]>([])
  const [toolsLoading, setToolsLoading] = useState(true)
  const [showAddTool, setShowAddTool] = useState(false)
  const [presets, setPresets] = useState<ToolPreset[]>([])
  const [editToolId, setEditToolId] = useState<number | null>(null)

  // Tool form state
  const [toolForm, setToolForm] = useState({
    name: '',
    label: '',
    description: '',
    tool_type: 'firecrawl_search',
    api_key: '',
  })

  useEffect(() => {
    Promise.all([
      getAdminConfig(),
      listTools(),
      getToolPresets(),
    ])
      .then(([configData, toolsData, presetsData]) => {
        setConfig(configData)
        setTools(toolsData)
        setPresets(presetsData)
        setStatus('idle')
        setToolsLoading(false)
      })
      .catch((err: Error) => {
        setError(err.message)
        setStatus('error')
        setToolsLoading(false)
      })
  }, [])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setStatus('saving')
    setError('')
    try {
      const updated = await saveAdminConfig({
        llm_config: {
          provider: config.llm_config.provider,
          model_name: config.llm_config.model_name,
          api_key: config.llm_config.api_key,
          base_url: config.llm_config.base_url,
          is_active: true,
        },
        system_prompt: {
          name: config.system_prompt.name,
          content: config.system_prompt.content,
          is_active: true,
        },
      })
      setConfig(updated)
      setStatus('saved')
      window.setTimeout(() => setStatus('idle'), 1600)
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
      setStatus('error')
    }
  }

  async function handleTestConnection() {
    setTestStatus('testing')
    setTestResult(null)
    try {
      const result = await testLLMConfig({
        provider: config.llm_config.provider,
        model_name: config.llm_config.model_name,
        api_key: config.llm_config.api_key,
        base_url: config.llm_config.base_url,
      })
      setTestResult(result)
      setTestStatus(result.success ? 'success' : 'error')
    } catch (err) {
      setTestResult({ success: false, latency_ms: 0, message: err instanceof Error ? err.message : '请求失败' })
      setTestStatus('error')
    }
  }

  function handlePresetSelect(preset: ToolPreset) {
    setToolForm({
      name: preset.name,
      label: preset.label,
      description: preset.description,
      tool_type: preset.tool_type,
      api_key: '',
    })
  }

  function resetToolForm() {
    setToolForm({ name: '', label: '', description: '', tool_type: 'firecrawl_search', api_key: '' })
    setEditToolId(null)
  }

  async function handleSaveTool() {
    if (!toolForm.name.trim()) return
    try {
      if (editToolId !== null) {
        const updated = await updateTool(editToolId, {
          name: toolForm.name,
          label: toolForm.label || toolForm.name,
          description: toolForm.description,
          tool_type: toolForm.tool_type,
          config: { api_key: toolForm.api_key },
        })
        setTools((prev) => prev.map((t) => (t.id === editToolId ? updated : t)))
      } else {
        const created = await createTool({
          name: toolForm.name,
          label: toolForm.label || toolForm.name,
          description: toolForm.description,
          tool_type: toolForm.tool_type,
          config: { api_key: toolForm.api_key },
        })
        setTools((prev) => [...prev, created])
      }
      resetToolForm()
      setShowAddTool(false)
    } catch (err) {
      console.error('Save tool failed', err)
    }
  }

  async function handleToggleTool(tool: ToolItem) {
    try {
      const updated = await updateTool(tool.id, { is_active: !tool.is_active })
      setTools((prev) => prev.map((t) => (t.id === tool.id ? updated : t)))
    } catch (err) {
      console.error('Toggle tool failed', err)
    }
  }

  async function handleDeleteTool(id: number) {
    try {
      await deleteTool(id)
      setTools((prev) => prev.filter((t) => t.id !== id))
    } catch (err) {
      console.error('Delete tool failed', err)
    }
  }

  function startEdit(tool: ToolItem) {
    setToolForm({
      name: tool.name,
      label: tool.label,
      description: tool.description,
      tool_type: tool.tool_type,
      api_key: (tool.config as Record<string, string>)?.api_key || '',
    })
    setEditToolId(tool.id)
    setShowAddTool(true)
  }

  const setLLM = (key: keyof AdminConfig['llm_config'], value: string) => {
    setConfig((current) => ({
      ...current,
      llm_config: { ...current.llm_config, [key]: value },
    }))
  }

  const setPrompt = (key: keyof AdminConfig['system_prompt'], value: string) => {
    setConfig((current) => ({
      ...current,
      system_prompt: { ...current.system_prompt, [key]: value },
    }))
  }

  return (
    <main className="min-h-screen px-4 pb-20 pt-28 text-ink">
      <ShellNav />
      <section className="mx-auto flex w-full max-w-5xl flex-col gap-8">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col gap-3"
        >
          <div className="flex w-fit items-center gap-2 rounded-3xl bg-sage px-4 py-2 text-sm text-moss">
            <Shield size={16} />
            Admin workspace
          </div>
          <h1 className="font-display text-4xl leading-tight md:text-5xl">配置漫游指南的大脑与语气</h1>
          <p className="max-w-2xl text-base leading-8 text-muted">
            V1 暂不启用登录校验。这里保存的配置会被聊天流式接口读取。
          </p>
        </motion.div>

        {/* LLM Config + System Prompt */}
        <form onSubmit={handleSubmit} className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
          <motion.section
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="rounded-4xl bg-paper/88 p-6 shadow-soft backdrop-blur"
          >
            <div className="mb-6 flex items-center gap-3">
              <span className="grid h-11 w-11 place-items-center rounded-3xl bg-clay">
                <Server size={20} />
              </span>
              <div>
                <h2 className="text-lg font-semibold">LLM Config</h2>
                <p className="text-sm text-muted">供应商、模型与 API 入口</p>
              </div>
            </div>

            <div className="space-y-5">
              <Field label="Provider">
                <input
                  value={config.llm_config.provider}
                  onChange={(event) => setLLM('provider', event.target.value)}
                  className="input"
                  placeholder="OpenAI / Gemini / Mock"
                />
              </Field>
              <Field label="Model name">
                <input
                  value={config.llm_config.model_name}
                  onChange={(event) => setLLM('model_name', event.target.value)}
                  className="input"
                  placeholder="gpt-4.1-mini"
                />
              </Field>
              <Field label="Base URL">
                <input
                  value={config.llm_config.base_url}
                  onChange={(event) => setLLM('base_url', event.target.value)}
                  className="input"
                  placeholder="https://api.openai.com/v1"
                />
              </Field>
              <Field label="API Key">
                <div className="relative">
                  <KeyRound className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" size={17} />
                  <input
                    type="password"
                    value={config.llm_config.api_key}
                    onChange={(event) => setLLM('api_key', event.target.value)}
                    className="input pl-11"
                    placeholder="sk-..."
                  />
                </div>
              </Field>

              {/* Test Connection */}
              <div className="pt-2">
                <button
                  type="button"
                  onClick={handleTestConnection}
                  disabled={testStatus === 'testing'}
                  className="inline-flex items-center gap-2 rounded-3xl border border-line bg-paper px-4 py-2.5 text-sm text-ink transition hover:bg-clay/40 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {testStatus === 'testing' ? (
                    <Loader2 className="animate-spin" size={16} />
                  ) : (
                    <Wifi size={16} />
                  )}
                  {testStatus === 'testing' ? '测试中...' : '测试连接'}
                </button>

                {testResult && (
                  <div
                    className={`mt-3 rounded-2xl px-4 py-2.5 text-sm leading-6 ${
                      testResult.success
                        ? 'bg-green-50 text-green-800'
                        : 'bg-red-50 text-red-800'
                    }`}
                  >
                    <span className="flex items-start gap-2">
                      {testResult.success ? (
                        <Check size={16} className="mt-0.5 shrink-0" />
                      ) : (
                        <X size={16} className="mt-0.5 shrink-0" />
                      )}
                      <span>{testResult.message}</span>
                    </span>
                  </div>
                )}
              </div>
            </div>
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="rounded-4xl bg-paper/88 p-6 shadow-soft backdrop-blur"
          >
            <div className="mb-6">
              <h2 className="text-lg font-semibold">System Prompt</h2>
              <p className="text-sm leading-6 text-muted">定义 WanderBot 的旅行规划风格、边界和默认推理方向。</p>
            </div>
            <div className="space-y-5">
              <Field label="Prompt name">
                <input
                  value={config.system_prompt.name}
                  onChange={(event) => setPrompt('name', event.target.value)}
                  className="input"
                />
              </Field>
              <Field label="Prompt content">
                <textarea
                  value={config.system_prompt.content}
                  onChange={(event) => setPrompt('content', event.target.value)}
                  className="input min-h-[280px] resize-none leading-7"
                />
              </Field>
            </div>
          </motion.section>

          <div className="lg:col-span-2">
            <div className="flex flex-col items-start justify-between gap-4 rounded-4xl bg-[#EEE8DF]/80 p-4 shadow-quiet backdrop-blur sm:flex-row sm:items-center">
              <p className="px-2 text-sm text-muted">
                {status === 'error' ? error : '保存后，聊天接口会读取当前激活的模型配置与系统提示词。'}
              </p>
              <button
                type="submit"
                disabled={status === 'saving' || status === 'loading'}
                className="inline-flex items-center gap-2 rounded-3xl bg-ink px-5 py-3 text-sm font-medium text-paper shadow-quiet transition hover:translate-y-[-1px] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {status === 'saving' || status === 'loading' ? (
                  <Loader2 className="animate-spin" size={17} />
                ) : status === 'saved' ? (
                  <Check size={17} />
                ) : (
                  <Save size={17} />
                )}
                {status === 'saved' ? '已保存' : '保存配置'}
              </button>
            </div>
          </div>
        </form>

        {/* Tools Section */}
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="rounded-4xl bg-paper/88 p-6 shadow-soft backdrop-blur"
        >
          <div className="mb-6 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="grid h-11 w-11 place-items-center rounded-3xl bg-sage">
                <Plug size={20} className="text-moss" />
              </span>
              <div>
                <h2 className="text-lg font-semibold">工具集成</h2>
                <p className="text-sm text-muted">为 WanderBot 配置可调用的第三方工具（联网搜索等）</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => {
                resetToolForm()
                setShowAddTool(!showAddTool)
              }}
              className="inline-flex items-center gap-2 rounded-3xl bg-ink px-4 py-2.5 text-sm font-medium text-paper transition hover:translate-y-[-1px]"
            >
              <Plus size={16} />
              {showAddTool ? '取消' : '添加工具'}
            </button>
          </div>

          {/* Add/Edit Tool Form */}
          {showAddTool && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              className="mb-6 rounded-3xl bg-[#F8F6F1] p-5"
            >
              <h3 className="mb-4 text-sm font-medium text-muted">
                {editToolId !== null ? '编辑工具' : '选择模板填加'}
              </h3>

              {/* Presets (only when adding) */}
              {editToolId === null && (
                <div className="mb-4 flex flex-wrap gap-2">
                  {presets.map((preset) => (
                    <button
                      key={preset.name}
                      type="button"
                      onClick={() => handlePresetSelect(preset)}
                      className={`rounded-2xl px-3 py-1.5 text-xs transition ${
                        toolForm.name === preset.name
                          ? 'bg-ink text-paper'
                          : 'bg-paper text-muted hover:bg-clay/40'
                      }`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="工具名称">
                  <input
                    value={toolForm.name}
                    onChange={(e) => setToolForm((f) => ({ ...f, name: e.target.value }))}
                    className="input"
                    placeholder="web_search"
                  />
                </Field>
                <Field label="显示名称">
                  <input
                    value={toolForm.label}
                    onChange={(e) => setToolForm((f) => ({ ...f, label: e.target.value }))}
                    className="input"
                    placeholder="Web Search"
                  />
                </Field>
                <Field label="类型">
                  <select
                    value={toolForm.tool_type}
                    onChange={(e) => setToolForm((f) => ({ ...f, tool_type: e.target.value }))}
                    className="input appearance-none"
                  >
                    <option value="firecrawl_search">Firecrawl Search</option>
                    <option value="firecrawl_scrape">Firecrawl Scrape</option>
                  </select>
                </Field>
                <Field label="API Key">
                  <input
                    type="password"
                    value={toolForm.api_key}
                    onChange={(e) => setToolForm((f) => ({ ...f, api_key: e.target.value }))}
                    className="input"
                    placeholder="fc-..."
                  />
                </Field>
                <Field label="描述" className="sm:col-span-2">
                  <textarea
                    value={toolForm.description}
                    onChange={(e) => setToolForm((f) => ({ ...f, description: e.target.value }))}
                    className="input min-h-[60px] resize-none leading-6"
                    placeholder="描述这个工具的用途..."
                  />
                </Field>
              </div>

              <div className="mt-4 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => {
                    resetToolForm()
                    setShowAddTool(false)
                  }}
                  className="rounded-3xl px-4 py-2 text-sm text-muted transition hover:bg-clay/40"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={handleSaveTool}
                  disabled={!toolForm.name.trim()}
                  className="inline-flex items-center gap-2 rounded-3xl bg-ink px-5 py-2 text-sm font-medium text-paper transition hover:translate-y-[-1px] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Save size={15} />
                  {editToolId !== null ? '保存修改' : '添加'}
                </button>
              </div>
            </motion.div>
          )}

          {/* Tools List */}
          {toolsLoading ? (
            <div className="flex items-center justify-center py-10 text-muted">
              <Loader2 className="mr-2 animate-spin" size={18} />
              加载中...
            </div>
          ) : tools.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-line px-6 py-10 text-center text-sm text-muted">
              暂无配置的工具。点击"添加工具"来为 WanderBot 增加联网能力。
            </div>
          ) : (
            <div className="space-y-3">
              {tools.map((tool) => {
                const Icon = TOOL_TYPE_ICONS[tool.tool_type] || Plug
                return (
                  <div
                    key={tool.id}
                    className="flex items-center justify-between rounded-3xl bg-[#F8F6F1] px-5 py-3.5 transition"
                  >
                    <div className="flex items-center gap-4">
                      <span
                        className={`grid h-10 w-10 place-items-center rounded-2xl ${
                          tool.is_active ? 'bg-sage text-moss' : 'bg-line/50 text-muted/50'
                        }`}
                      >
                        <Icon size={18} />
                      </span>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className={`text-sm font-medium ${tool.is_active ? 'text-ink' : 'text-muted/60'}`}>
                            {tool.label || tool.name}
                          </span>
                          <span className="rounded-full bg-line px-2 py-0.5 text-[11px] text-muted">
                            {tool.tool_type}
                          </span>
                        </div>
                        {tool.description && (
                          <p className="mt-0.5 text-xs leading-5 text-muted">{tool.description}</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => startEdit(tool)}
                        className="grid h-8 w-8 place-items-center rounded-xl text-muted transition hover:bg-clay/40"
                        title="编辑"
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleToggleTool(tool)}
                        className={`grid h-8 w-8 place-items-center rounded-xl transition ${
                          tool.is_active
                            ? 'text-green-700 hover:bg-green-100'
                            : 'text-muted hover:bg-clay/40'
                        }`}
                        title={tool.is_active ? '禁用' : '启用'}
                      >
                        {tool.is_active ? <Wifi size={15} /> : <WifiOff size={15} />}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteTool(tool.id)}
                        className="grid h-8 w-8 place-items-center rounded-xl text-muted transition hover:bg-red-100 hover:text-red-600"
                        title="删除"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </motion.section>
      </section>
    </main>
  )
}

function Field({ label, children, className = '' }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-2 block px-1 text-sm font-medium text-muted">{label}</span>
      {children}
    </label>
  )
}
