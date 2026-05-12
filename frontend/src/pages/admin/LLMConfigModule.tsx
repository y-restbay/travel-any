import { FormEvent, useEffect, useState } from 'react'
import { Check, CheckCircle, KeyRound, Loader2, Pencil, Plus, Save, Server, ToggleRight, Trash2, Wifi, X } from 'lucide-react'
import {
  createLLMConfig,
  deleteLLMConfig,
  listLLMConfigs,
  testLLMConfig,
  updateLLMConfig,
} from '../../api'
import type { LLMConfig, TestResult } from '../../types'
import { EmptyState, Field, IconButton, InlineNotice, LoadingState, Modal, ModuleCard, SoftButton } from './shared'

type TestStatus = 'idle' | 'testing' | 'success' | 'error'
type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

const blankForm = {
  provider: 'OpenAI',
  model_name: 'gpt-4.1-mini',
  api_key: '',
  base_url: '',
}

export default function LLMConfigModule() {
  const [configs, setConfigs] = useState<LLMConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState(blankForm)
  const [activateAfterSave, setActivateAfterSave] = useState(false)
  const [testStatus, setTestStatus] = useState<TestStatus>('idle')
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [error, setError] = useState('')

  useEffect(() => {
    loadConfigs()
  }, [])

  async function loadConfigs() {
    setLoading(true)
    try {
      setConfigs(await listLLMConfigs())
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '模型配置加载失败')
    } finally {
      setLoading(false)
    }
  }

  function openCreate() {
    setForm(blankForm)
    setEditingId(null)
    setActivateAfterSave(true)
    setShowNew(true)
    setTestResult(null)
    setTestStatus('idle')
  }

  function openEdit(config: LLMConfig) {
    setForm({
      provider: config.provider,
      model_name: config.model_name,
      api_key: config.api_key,
      base_url: config.base_url,
    })
    setEditingId(config.id)
    setActivateAfterSave(false)
    setShowNew(true)
    setTestResult(null)
    setTestStatus('idle')
  }

  function closeForm() {
    setShowNew(false)
    setEditingId(null)
    setForm(blankForm)
    setActivateAfterSave(false)
  }

  async function handleSave(event: FormEvent) {
    event.preventDefault()
    if (!form.provider.trim() || !form.model_name.trim()) return
    setSaveStatus('saving')
    try {
      const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null
      const shouldActivate = submitter?.dataset.intent === 'save-active' || activateAfterSave
      if (editingId === null) {
        await createLLMConfig({ ...form, is_active: shouldActivate || configs.length === 0 })
      } else {
        const updates: Partial<typeof form> & { is_active?: boolean } = { ...form }
        if (shouldActivate) updates.is_active = true
        await updateLLMConfig(editingId, updates)
      }
      setSaveStatus('saved')
      closeForm()
      await loadConfigs()
      window.setTimeout(() => setSaveStatus('idle'), 1200)
    } catch (err) {
      setError(err instanceof Error ? err.message : '模型配置保存失败')
      setSaveStatus('error')
    }
  }

  async function handleActivate(id: number) {
    await updateLLMConfig(id, { is_active: true })
    await loadConfigs()
  }

  async function handleDelete(id: number) {
    await deleteLLMConfig(id)
    await loadConfigs()
  }

  async function handleTestConnection() {
    setTestStatus('testing')
    setTestResult(null)
    try {
      const result = await testLLMConfig(form)
      setTestResult(result)
      setTestStatus(result.success ? 'success' : 'error')
    } catch (err) {
      setTestResult({
        success: false,
        latency_ms: 0,
        message: err instanceof Error ? err.message : '请求失败',
      })
      setTestStatus('error')
    }
  }

  const active = configs.find((item) => item.is_active)

  return (
    <div className="space-y-6">
      <ModuleCard
        icon={<Server size={20} />}
        title="大模型配置"
        desc="只管理模型供应商、模型名称、API Key 和 Base URL。聊天接口始终读取当前激活的这一条配置。"
        actions={
          <SoftButton onClick={openCreate} tone="primary">
            <Plus size={16} />
            新建模型
          </SoftButton>
        }
      >
        <div className="mb-5 grid gap-3 sm:grid-cols-3">
          <Metric label="当前模型" value={active ? `${active.provider} / ${active.model_name}` : '未配置'} />
          <Metric label="配置数量" value={`${configs.length}`} />
          <Metric label="连接状态" value={active?.base_url ? '自定义端点' : '默认端点'} />
        </div>

        {error && <InlineNotice tone="error">{error}</InlineNotice>}

        {/* ---- Modal ---- */}
        <Modal
          open={showNew}
          onClose={closeForm}
          title={editingId === null ? '新建模型配置' : '编辑模型配置'}
          subtitle={editingId === null ? '添加一个新的 LLM 供应商配置。保存后即可在聊天中使用。' : '修改已保存的模型参数。'}
        >
          <form onSubmit={handleSave}>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Provider">
                <input
                  value={form.provider}
                  onChange={(event) => setForm((current) => ({ ...current, provider: event.target.value }))}
                  className="input"
                  placeholder="OpenAI / Gemini / Mock"
                />
              </Field>
              <Field label="Model name">
                <input
                  value={form.model_name}
                  onChange={(event) => setForm((current) => ({ ...current, model_name: event.target.value }))}
                  className="input"
                  placeholder="gpt-4.1-mini"
                />
              </Field>
              <Field label="Base URL">
                <input
                  value={form.base_url}
                  onChange={(event) => setForm((current) => ({ ...current, base_url: event.target.value }))}
                  className="input"
                  placeholder="https://api.openai.com/v1"
                />
              </Field>
              <Field label="API Key">
                <div className="relative">
                  <KeyRound className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" size={17} />
                  <input
                    type="password"
                    value={form.api_key}
                    onChange={(event) => setForm((current) => ({ ...current, api_key: event.target.value }))}
                    className="input pl-11"
                    placeholder="sk-..."
                  />
                </div>
              </Field>
            </div>

            <label className="mt-4 flex cursor-pointer items-center gap-3 rounded-3xl bg-[#F8F6F1] px-4 py-3 transition hover:bg-clay/20">
              <input
                type="checkbox"
                checked={activateAfterSave}
                onChange={(e) => setActivateAfterSave(e.target.checked)}
                className="h-4 w-4 rounded accent-ink"
              />
              <span className="text-sm text-ink">保存后立即启用此模型</span>
              {active && editingId !== active.id && activateAfterSave && (
                <span className="rounded-full bg-sage px-2 py-0.5 text-[11px] text-moss">
                  将替代 {active.provider}/{active.model_name}
                </span>
              )}
            </label>

            {testResult && (
              <div className="mt-4">
                <InlineNotice tone={testResult.success ? 'success' : 'error'}>
                  <span className="flex items-start gap-2">
                    {testResult.success ? <Check className="mt-0.5 shrink-0" size={16} /> : <X className="mt-0.5 shrink-0" size={16} />}
                    <span>{testResult.message}</span>
                  </span>
                </InlineNotice>
              </div>
            )}

            <div className="mt-6 flex flex-col gap-3 border-t border-line/50 pt-5 sm:flex-row sm:justify-end">
              <SoftButton onClick={handleTestConnection} disabled={testStatus === 'testing'}>
                {testStatus === 'testing' ? <Loader2 className="animate-spin" size={16} /> : <Wifi size={16} />}
                测试连接
              </SoftButton>
              <SoftButton onClick={closeForm} type="button">取消</SoftButton>
              <SoftButton type="submit" tone="primary" disabled={saveStatus === 'saving'}>
                {saveStatus === 'saving' ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
                {editingId === null ? '保存模型' : '保存修改'}
              </SoftButton>
              <SoftButton type="submit" tone="success" disabled={saveStatus === 'saving'} intent="save-active">
                {saveStatus === 'saving' ? <Loader2 className="animate-spin" size={16} /> : <CheckCircle size={16} />}
                保存并启用
              </SoftButton>
            </div>
          </form>
        </Modal>

        {loading ? (
          <LoadingState />
        ) : configs.length === 0 ? (
          <EmptyState>还没有模型配置。创建一条 Mock 或真实供应商配置后，聊天接口就能读取它。</EmptyState>
        ) : (
          <div className="space-y-3">
            {configs.map((config) => (
              <div key={config.id} className="flex flex-col gap-4 rounded-4xl bg-[#F8F6F1] px-5 py-4 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${config.is_active ? 'bg-green-500' : 'bg-line'}`} />
                    <span className="font-medium">{config.provider} / {config.model_name}</span>
                    {config.is_active && <span className="rounded-full bg-sage px-2 py-0.5 text-[11px] font-medium text-moss">当前使用</span>}
                  </div>
                  <p className="mt-1 truncate text-sm text-muted">{config.base_url || '使用供应商默认 Base URL'}</p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {!config.is_active ? (
                    <SoftButton tone="primary" onClick={() => handleActivate(config.id)} className="!px-3 !py-2">
                      <ToggleRight size={15} />
                      启用
                    </SoftButton>
                  ) : (
                    <span className="mr-1 rounded-full border border-sage px-3 py-1.5 text-[11px] text-moss">
                      运行中
                    </span>
                  )}
                  <IconButton title="编辑" onClick={() => openEdit(config)}>
                    <Pencil size={15} />
                  </IconButton>
                  {!config.is_active && (
                    <IconButton title="删除" danger onClick={() => handleDelete(config.id)}>
                      <Trash2 size={15} />
                    </IconButton>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </ModuleCard>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-3xl bg-[#F8F6F1] px-4 py-3">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 truncate text-sm font-semibold text-ink">{value}</p>
    </div>
  )
}
