import { FormEvent, useEffect, useMemo, useState } from 'react'
import { BookOpenCheck, Check, Copy, FileText, Loader2, Pencil, Plus, Save, Trash2 } from 'lucide-react'
import {
  createSystemPrompt,
  deleteSystemPrompt,
  getRagStats,
  listSystemPrompts,
  updateSystemPrompt,
} from '../../api'
import type { RAGDocumentSummary, SystemPrompt } from '../../types'
import { EmptyState, Field, IconButton, InlineNotice, LoadingState, ModuleCard, SoftButton } from './shared'

const blankPrompt = {
  name: '',
  content: '',
  knowledge_scope: [] as string[],
}

export default function SystemPromptModule() {
  const [prompts, setPrompts] = useState<SystemPrompt[]>([])
  const [documents, setDocuments] = useState<RAGDocumentSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [showEditor, setShowEditor] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState(blankPrompt)
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [error, setError] = useState('')

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    setLoading(true)
    try {
      const [promptData, stats] = await Promise.all([listSystemPrompts(), getRagStats()])
      setPrompts(promptData)
      setDocuments(stats.documents ?? [])
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '系统提示词加载失败')
    } finally {
      setLoading(false)
    }
  }

  function openCreate() {
    setForm(blankPrompt)
    setEditingId(null)
    setShowEditor(true)
  }

  function openEdit(prompt: SystemPrompt) {
    setForm({
      name: prompt.name,
      content: prompt.content,
      knowledge_scope: prompt.knowledge_scope ?? [],
    })
    setEditingId(prompt.id)
    setShowEditor(true)
  }

  function closeEditor() {
    setShowEditor(false)
    setEditingId(null)
    setForm(blankPrompt)
  }

  async function handleSave(event: FormEvent) {
    event.preventDefault()
    if (!form.name.trim() || !form.content.trim()) return
    setStatus('saving')
    try {
      if (editingId === null) {
        await createSystemPrompt({ ...form, is_active: prompts.length === 0 })
      } else {
        await updateSystemPrompt(editingId, form)
      }
      setStatus('saved')
      closeEditor()
      await loadData()
      window.setTimeout(() => setStatus('idle'), 1200)
    } catch (err) {
      setStatus('error')
      setError(err instanceof Error ? err.message : '系统提示词保存失败')
    }
  }

  async function handleActivate(id: number) {
    await updateSystemPrompt(id, { is_active: true })
    await loadData()
  }

  async function handleDelete(id: number) {
    await deleteSystemPrompt(id)
    await loadData()
  }

  function toggleDocument(documentId: string) {
    setForm((current) => {
      const selected = current.knowledge_scope.includes(documentId)
      return {
        ...current,
        knowledge_scope: selected
          ? current.knowledge_scope.filter((item) => item !== documentId)
          : [...current.knowledge_scope, documentId],
      }
    })
  }

  const activePrompt = useMemo(() => prompts.find((prompt) => prompt.is_active), [prompts])

  return (
    <ModuleCard
      icon={<FileText size={20} />}
      title="System Prompt"
      desc="只管理助手的角色、回答边界和可关联的知识库文件。模型参数不在这里出现，保持提示词模块单一职责。"
      actions={
        <SoftButton onClick={openCreate} tone="primary">
          <Plus size={16} />
          新建 Prompt
        </SoftButton>
      }
    >
      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <Metric label="当前 Prompt" value={activePrompt?.name ?? '未配置'} />
        <Metric label="Prompt 数量" value={`${prompts.length}`} />
        <Metric label="可选知识文件" value={`${documents.length}`} />
      </div>

      <InlineNotice>
        文件选择会保存为 Prompt 的知识库范围。当前聊天接口仍使用全局 RAG 检索，后续可以基于这个字段进一步限定检索文档。
      </InlineNotice>

      {error && <div className="mt-4"><InlineNotice tone="error">{error}</InlineNotice></div>}

      {showEditor && (
        <form onSubmit={handleSave} className="mt-5 rounded-4xl bg-[#F8F6F1] p-5">
          <div className="grid gap-4">
            <Field label="Prompt name">
              <input
                value={form.name}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                className="input"
                placeholder="Iceland nature planner"
              />
            </Field>
            <Field label="Prompt content">
              <textarea
                value={form.content}
                onChange={(event) => setForm((current) => ({ ...current, content: event.target.value }))}
                className="input min-h-[220px] resize-none leading-7"
                placeholder="输入系统提示词内容..."
              />
            </Field>
            <Field label="关联知识库文件" hint="不选择时表示不限定文件范围；选择后会保存到 Prompt 配置中。">
              {documents.length === 0 ? (
                <div className="rounded-3xl border border-dashed border-line px-4 py-6 text-center text-sm text-muted">
                  知识库还没有上传文件。先去“知识库文件”模块上传文本文件。
                </div>
              ) : (
                <div className="grid gap-2 md:grid-cols-2">
                  {documents.map((document) => {
                    const checked = form.knowledge_scope.includes(document.document_id)
                    return (
                      <button
                        type="button"
                        key={document.document_id}
                        onClick={() => toggleDocument(document.document_id)}
                        className={`flex items-center gap-3 rounded-3xl px-4 py-3 text-left transition ${
                          checked ? 'bg-sage text-moss shadow-quiet' : 'bg-paper text-ink hover:bg-clay/30'
                        }`}
                      >
                        <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-2xl ${checked ? 'bg-paper/80' : 'bg-[#F8F6F1]'}`}>
                          {checked ? <Check size={15} /> : <BookOpenCheck size={15} />}
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium">{document.filename}</span>
                          <span className="block text-xs opacity-75">{document.chunk_count} chunks · {document.strategy ?? 'unknown'}</span>
                        </span>
                      </button>
                    )
                  })}
                </div>
              )}
            </Field>
          </div>

          <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:justify-end">
            <SoftButton onClick={closeEditor}>取消</SoftButton>
            <SoftButton type="submit" tone="primary" disabled={status === 'saving'}>
              {status === 'saving' ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
              {editingId === null ? '保存 Prompt' : '保存修改'}
            </SoftButton>
          </div>
        </form>
      )}

      <div className="mt-5">
        {loading ? (
          <LoadingState />
        ) : prompts.length === 0 ? (
          <EmptyState>还没有系统提示词。创建一条后，聊天接口会读取当前激活的 Prompt。</EmptyState>
        ) : (
          <div className="space-y-3">
            {prompts.map((prompt) => (
              <div key={prompt.id} className="flex flex-col gap-4 rounded-4xl bg-[#F8F6F1] px-5 py-4 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${prompt.is_active ? 'bg-green-500' : 'bg-line'}`} />
                    <span className="font-medium">{prompt.name}</span>
                    {prompt.is_active && <span className="rounded-full bg-sage px-2 py-0.5 text-[11px] text-moss">当前激活</span>}
                    {(prompt.knowledge_scope?.length ?? 0) > 0 && (
                      <span className="rounded-full bg-paper px-2 py-0.5 text-[11px] text-muted">
                        {prompt.knowledge_scope.length} 个文件
                      </span>
                    )}
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm leading-6 text-muted">{prompt.content}</p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {!prompt.is_active && (
                    <IconButton title="激活" onClick={() => handleActivate(prompt.id)}>
                      <Copy size={15} />
                    </IconButton>
                  )}
                  <IconButton title="编辑" onClick={() => openEdit(prompt)}>
                    <Pencil size={15} />
                  </IconButton>
                  {!prompt.is_active && (
                    <IconButton title="删除" danger onClick={() => handleDelete(prompt.id)}>
                      <Trash2 size={15} />
                    </IconButton>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </ModuleCard>
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
