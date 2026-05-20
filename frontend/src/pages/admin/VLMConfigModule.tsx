import { FormEvent, useEffect, useState } from 'react'
import { Camera, Check, CheckCircle, KeyRound, Loader2, Pencil, Plus, Save, ToggleRight, Trash2, Wifi, X } from 'lucide-react'
import {
  createVLMConfig,
  deleteVLMConfig,
  listVLMConfigs,
  testVLMConfig,
  updateVLMConfig,
} from '../../api'
import type { TestResult, VLMConfig } from '../../types'
import { EmptyState, Field, IconButton, InlineNotice, LoadingState, Modal, ModuleCard, SoftButton } from './shared'

type TestStatus = 'idle' | 'testing' | 'success' | 'error'
type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

const blankForm = {
  provider: 'dashscope',
  model_name: 'qwen-vl-max',
  api_key: '',
  base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
}

export default function VLMConfigModule() {
  const [configs, setConfigs] = useState<VLMConfig[]>([])
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
      setConfigs(await listVLMConfigs())
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '图片识别模型配置加载失败')
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

  function openEdit(config: VLMConfig) {
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
    if (!form.model_name.trim()) return
    setSaveStatus('saving')
    try {
      const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null
      const shouldActivate = submitter?.dataset.intent === 'save-active' || activateAfterSave
      if (editingId === null) {
        await createVLMConfig({ ...form, is_active: shouldActivate || configs.length === 0 })
      } else {
        const updates: Partial<typeof form> & { is_active?: boolean } = { ...form }
        if (shouldActivate) updates.is_active = true
        await updateVLMConfig(editingId, updates)
      }
      setSaveStatus('saved')
      closeForm()
      await loadConfigs()
      window.setTimeout(() => setSaveStatus('idle'), 1200)
    } catch (err) {
      setError(err instanceof Error ? err.message : '图片识别模型配置保存失败')
      setSaveStatus('error')
    }
  }

  async function handleActivate(id: number) {
    await updateVLMConfig(id, { is_active: true })
    await loadConfigs()
  }

  async function handleDelete(id: number) {
    await deleteVLMConfig(id)
    await loadConfigs()
  }

  async function handleTestConnection() {
    setTestStatus('testing')
    setTestResult(null)
    try {
      const result = await testVLMConfig(form)
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
        icon={<Camera size={20} />}
        title="图片识别模型 (VLM)"
        desc="为 identify_landmark 工具配置多模态大模型。默认使用阿里百炼的 qwen-vl-max，OpenAI 兼容模式接入。API Key 留空时回退到环境变量 DASHSCOPE_API_KEY。"
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
          <Metric label="端点" value={active?.base_url ? active.base_url : '使用默认端点'} />
        </div>

        {error && <InlineNotice tone="error">{error}</InlineNotice>}

        <Modal
          open={showNew}
          onClose={closeForm}
          title={editingId === null ? '新建图片识别模型' : '编辑图片识别模型'}
          subtitle={
            editingId === null
              ? '建议沿用默认值:百炼 OpenAI 兼容模式 + qwen-vl-max。'
              : '修改 VLM 调用参数。API Key 留空保留原值。'
          }
        >
          <form onSubmit={handleSave}>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Provider" hint="供识别使用，例如 dashscope / openai">
                <input
                  value={form.provider}
                  onChange={(event) => setForm((current) => ({ ...current, provider: event.target.value }))}
                  className="input"
                  placeholder="dashscope"
                />
              </Field>
              <Field label="Model name" hint="qwen-vl-max / qwen-vl-plus / glm-4v-flash 等">
                <input
                  value={form.model_name}
                  onChange={(event) => setForm((current) => ({ ...current, model_name: event.target.value }))}
                  className="input"
                  placeholder="qwen-vl-max"
                />
              </Field>
              <Field label="Base URL" hint="百炼 OpenAI 兼容模式: https://dashscope.aliyuncs.com/compatible-mode/v1">
                <input
                  value={form.base_url}
                  onChange={(event) => setForm((current) => ({ ...current, base_url: event.target.value }))}
                  className="input"
                  placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
                />
              </Field>
              <Field label="API Key" hint="留空则使用环境变量 DASHSCOPE_API_KEY">
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
              <span className="text-sm text-ink">保存后立即启用此 VLM 配置</span>
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

            <div className="sticky bottom-0 -mx-6 mt-6 flex flex-col gap-3 border-t border-line/50 bg-paper/95 px-6 pt-5 pb-1 backdrop-blur md:-mx-7 md:px-7 sm:flex-row sm:justify-end">
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
          <EmptyState>还没有图片识别模型配置。新增一条后,看图识景点功能即可可用。</EmptyState>
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
                  <p className="mt-1 truncate text-sm text-muted">{config.base_url || '默认端点'}</p>
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
