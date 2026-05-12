import { useEffect, useState } from 'react'
import { Globe, Loader2, Pencil, Plug, Plus, Save, Search, Trash2, Wifi, WifiOff } from 'lucide-react'
import { createTool, deleteTool, getToolPresets, listTools, updateTool } from '../../api'
import type { ToolItem, ToolPreset } from '../../types'
import { EmptyState, Field, IconButton, LoadingState, ModuleCard, SoftButton } from './shared'

const toolIcons: Record<string, typeof Globe> = {
  firecrawl_search: Search,
  firecrawl_scrape: Globe,
}

const blankTool = {
  name: '',
  label: '',
  description: '',
  tool_type: 'firecrawl_search',
  api_key: '',
}

export default function ToolsModule() {
  const [tools, setTools] = useState<ToolItem[]>([])
  const [presets, setPresets] = useState<ToolPreset[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState(blankTool)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    Promise.all([listTools(), getToolPresets()])
      .then(([toolData, presetData]) => {
        setTools(toolData)
        setPresets(presetData)
      })
      .finally(() => setLoading(false))
  }, [])

  function openCreate() {
    setForm(blankTool)
    setEditingId(null)
    setShowForm(true)
  }

  function openEdit(tool: ToolItem) {
    setForm({
      name: tool.name,
      label: tool.label,
      description: tool.description,
      tool_type: tool.tool_type,
      api_key: String(tool.config?.api_key ?? ''),
    })
    setEditingId(tool.id)
    setShowForm(true)
  }

  function closeForm() {
    setForm(blankTool)
    setEditingId(null)
    setShowForm(false)
  }

  function applyPreset(preset: ToolPreset) {
    setForm({
      name: preset.name,
      label: preset.label,
      description: preset.description,
      tool_type: preset.tool_type,
      api_key: '',
    })
  }

  async function saveTool() {
    if (!form.name.trim()) return
    setSaving(true)
    try {
      if (editingId === null) {
        const created = await createTool({
          name: form.name,
          label: form.label || form.name,
          description: form.description,
          tool_type: form.tool_type,
          config: { api_key: form.api_key },
        })
        setTools((current) => [...current, created])
      } else {
        const updated = await updateTool(editingId, {
          name: form.name,
          label: form.label || form.name,
          description: form.description,
          tool_type: form.tool_type,
          config: { api_key: form.api_key },
        })
        setTools((current) => current.map((tool) => (tool.id === editingId ? updated : tool)))
      }
      closeForm()
    } finally {
      setSaving(false)
    }
  }

  async function toggleTool(tool: ToolItem) {
    const updated = await updateTool(tool.id, { is_active: !tool.is_active })
    setTools((current) => current.map((item) => (item.id === tool.id ? updated : item)))
  }

  async function removeTool(id: number) {
    await deleteTool(id)
    setTools((current) => current.filter((item) => item.id !== id))
  }

  return (
    <ModuleCard
      icon={<Plug size={20} />}
      title="工具集成"
      desc="只管理第三方工具的开关和凭证，例如 Firecrawl Search / Scrape。RAG 文件与模型配置在各自模块中处理。"
      actions={
        <SoftButton onClick={openCreate} tone="primary">
          <Plus size={16} />
          添加工具
        </SoftButton>
      }
    >
      {showForm && (
        <div className="mb-6 rounded-4xl bg-[#F8F6F1] p-5">
          {editingId === null && presets.length > 0 && (
            <div className="mb-4 flex flex-wrap gap-2">
              {presets.map((preset) => (
                <button
                  key={preset.name}
                  type="button"
                  onClick={() => applyPreset(preset)}
                  className={`rounded-2xl px-3 py-1.5 text-xs transition ${
                    form.name === preset.name ? 'bg-ink text-paper' : 'bg-paper text-muted hover:bg-clay/40'
                  }`}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="工具名称">
              <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} className="input" placeholder="web_search" />
            </Field>
            <Field label="显示名称">
              <input value={form.label} onChange={(event) => setForm((current) => ({ ...current, label: event.target.value }))} className="input" placeholder="Web Search" />
            </Field>
            <Field label="类型">
              <select value={form.tool_type} onChange={(event) => setForm((current) => ({ ...current, tool_type: event.target.value }))} className="input appearance-none">
                <option value="firecrawl_search">Firecrawl Search</option>
                <option value="firecrawl_scrape">Firecrawl Scrape</option>
              </select>
            </Field>
            <Field label="API Key">
              <input type="password" value={form.api_key} onChange={(event) => setForm((current) => ({ ...current, api_key: event.target.value }))} className="input" placeholder="fc-..." />
            </Field>
            <Field label="描述" className="sm:col-span-2">
              <textarea value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} className="input min-h-[80px] resize-none leading-6" />
            </Field>
          </div>

          <div className="mt-5 flex justify-end gap-3">
            <SoftButton onClick={closeForm}>取消</SoftButton>
            <SoftButton onClick={saveTool} tone="primary" disabled={!form.name.trim() || saving}>
              {saving ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
              保存工具
            </SoftButton>
          </div>
        </div>
      )}

      {loading ? (
        <LoadingState />
      ) : tools.length === 0 ? (
        <EmptyState>暂无配置的工具。添加工具后，真实模型可在回答前调用外部能力。</EmptyState>
      ) : (
        <div className="space-y-3">
          {tools.map((tool) => {
            const Icon = toolIcons[tool.tool_type] || Plug
            return (
              <div key={tool.id} className="flex flex-col gap-4 rounded-4xl bg-[#F8F6F1] px-5 py-4 md:flex-row md:items-center md:justify-between">
                <div className="flex min-w-0 items-center gap-4">
                  <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-3xl ${tool.is_active ? 'bg-sage text-moss' : 'bg-line/50 text-muted/60'}`}>
                    <Icon size={18} />
                  </span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{tool.label || tool.name}</span>
                      <span className="rounded-full bg-paper px-2 py-0.5 text-[11px] text-muted">{tool.tool_type}</span>
                      {tool.is_active && <span className="rounded-full bg-sage px-2 py-0.5 text-[11px] text-moss">启用中</span>}
                    </div>
                    {tool.description && <p className="mt-1 line-clamp-2 text-sm leading-6 text-muted">{tool.description}</p>}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <IconButton title="编辑" onClick={() => openEdit(tool)}>
                    <Pencil size={15} />
                  </IconButton>
                  <IconButton title={tool.is_active ? '禁用' : '启用'} onClick={() => toggleTool(tool)}>
                    {tool.is_active ? <Wifi size={15} /> : <WifiOff size={15} />}
                  </IconButton>
                  <IconButton title="删除" danger onClick={() => removeTool(tool.id)}>
                    <Trash2 size={15} />
                  </IconButton>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </ModuleCard>
  )
}
