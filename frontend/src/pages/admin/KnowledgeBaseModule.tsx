import { FormEvent, useEffect, useRef, useState } from 'react'
import { Database, FileUp, Loader2, RefreshCw, RotateCcw, Save } from 'lucide-react'
import { getRagStats, ingestText, rebuildRagVectorIndex, uploadRagFile } from '../../api'
import type { IngestResult, RAGStats } from '../../types'
import { EmptyState, Field, InlineNotice, LoadingState, ModuleCard, SoftButton } from './shared'

const docTypes = [
  { value: 'guide', label: '专业指南 / 长文' },
  { value: 'review', label: '短评 / 社交帖子' },
  { value: 'report', label: '报告 / 手册' },
  { value: 'ugc', label: 'UGC / 评论' },
]

export default function KnowledgeBaseModule() {
  const [stats, setStats] = useState<RAGStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [file, setFile] = useState<File | null>(null)
  const [docType, setDocType] = useState('guide')
  const [source, setSource] = useState('admin-upload')
  const [manualText, setManualText] = useState('')
  const [manualFilename, setManualFilename] = useState('manual-note.txt')
  const [uploading, setUploading] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [result, setResult] = useState<IngestResult | null>(null)
  const [error, setError] = useState('')
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    refreshStats()
  }, [])

  async function refreshStats() {
    setLoading(true)
    try {
      setStats(await getRagStats())
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '知识库统计加载失败')
    } finally {
      setLoading(false)
    }
  }

  async function handleUpload(event: FormEvent) {
    event.preventDefault()
    if (!file) return
    setUploading(true)
    setResult(null)
    try {
      const ingestResult = await uploadRagFile(file, { doc_type: docType, source })
      setResult(ingestResult)
      setFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      await refreshStats()
    } catch (err) {
      setError(err instanceof Error ? err.message : '文件上传失败')
    } finally {
      setUploading(false)
    }
  }

  async function handleManualIngest() {
    if (!manualText.trim()) return
    setUploading(true)
    setResult(null)
    try {
      const ingestResult = await ingestText({
        text: manualText,
        filename: manualFilename || 'manual-note.txt',
        doc_type: docType,
        source: source || 'admin-manual',
      })
      setResult(ingestResult)
      setManualText('')
      await refreshStats()
    } catch (err) {
      setError(err instanceof Error ? err.message : '文本入库失败')
    } finally {
      setUploading(false)
    }
  }

  async function handleRebuildVectors() {
    setRebuilding(true)
    setResult(null)
    try {
      setStats(await rebuildRagVectorIndex())
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '向量索引重建失败')
    } finally {
      setRebuilding(false)
    }
  }

  return (
    <div className="space-y-6">
      <ModuleCard
        icon={<Database size={20} />}
        title="知识库文件"
        desc="只负责把自定义旅游资料上传、切分、写入 ChromaDB、BM25 和实体索引。Prompt 和模型配置不在这里编辑。"
        actions={
          <div className="flex flex-wrap gap-2">
            <SoftButton onClick={handleRebuildVectors} disabled={rebuilding}>
              {rebuilding ? <Loader2 className="animate-spin" size={16} /> : <RotateCcw size={16} />}
              重建向量
            </SoftButton>
            <SoftButton onClick={refreshStats}>
              <RefreshCw size={16} />
              刷新统计
            </SoftButton>
          </div>
        }
      >
        {loading ? (
          <LoadingState label="读取知识库状态..." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            <Metric label="切片总数" value={`${stats?.chunk_count ?? 0}`} />
            <Metric label="向量库条目" value={`${stats?.vector_count ?? 0}`} />
            <Metric label="实体索引" value={`${stats?.entity_count ?? 0}`} />
          </div>
        )}

        {stats && (
          <div className="mt-4 grid gap-3 text-xs leading-5 text-muted md:grid-cols-2">
            <div className="rounded-3xl bg-[#F8F6F1] px-4 py-3">
              <span className="block font-medium text-ink">ChromaDB</span>
              <span className="break-all">{stats.chroma_path}</span>
            </div>
            <div className="rounded-3xl bg-[#F8F6F1] px-4 py-3">
              <span className="block font-medium text-ink">Collection</span>
              <span className="break-all">{stats.collection_name ?? 'wanderbot_knowledge'}</span>
            </div>
            <div className="rounded-3xl bg-[#F8F6F1] px-4 py-3">
              <span className="block font-medium text-ink">Embedding</span>
              <span className="break-all">
                {stats.embedding_provider ?? 'hash'} / {stats.embedding_model ?? 'hash-384'}
                {stats.is_real_embedding ? ' · real' : ' · fallback'}
              </span>
            </div>
            <div className="rounded-3xl bg-[#F8F6F1] px-4 py-3">
              <span className="block font-medium text-ink">BM25</span>
              <span className="break-all">{stats.bm25_path}</span>
            </div>
            {typeof stats.reindexed_chunks === 'number' && (
              <div className="rounded-3xl bg-[#F8F6F1] px-4 py-3">
                <span className="block font-medium text-ink">Reindexed</span>
                <span>{stats.reindexed_chunks} chunks</span>
              </div>
            )}
          </div>
        )}

        {error && <div className="mt-4"><InlineNotice tone="error">{error}</InlineNotice></div>}
        {result && (
          <div className="mt-4">
            <InlineNotice tone="success">
              已入库：{result.filename}，采用 {result.strategy === 'long_form' ? '长文切片' : '短文切片'}，生成 {result.chunk_count} 个 chunk，抽取 {result.entity_count} 个实体。
            </InlineNotice>
          </div>
        )}
      </ModuleCard>

      <ModuleCard icon={<FileUp size={20} />} title="上传文件" desc="V1 支持 UTF-8 文本文件。上传后会立即执行自适应切片并写入混合索引。">
        <form onSubmit={handleUpload} className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="文档类型" hint="决定切片策略：指南/报告倾向 1000/200；短评/UGC 倾向 300/50。">
              <select value={docType} onChange={(event) => setDocType(event.target.value)} className="input appearance-none">
                {docTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </Field>
            <Field label="来源标记">
              <input value={source} onChange={(event) => setSource(event.target.value)} className="input" placeholder="iceland-guide" />
            </Field>
          </div>
          <Field label="选择文件">
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.md,.csv,.json"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="block w-full cursor-pointer rounded-3xl bg-[#F8F6F1] px-4 py-3 text-sm text-muted shadow-quiet file:mr-4 file:rounded-2xl file:border-0 file:bg-paper file:px-4 file:py-2 file:text-sm file:font-medium file:text-ink hover:file:bg-clay/30"
            />
          </Field>
          <div className="flex justify-end">
            <SoftButton type="submit" tone="primary" disabled={!file || uploading}>
              {uploading ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
              上传并入库
            </SoftButton>
          </div>
        </form>
      </ModuleCard>

      <ModuleCard icon={<FileUp size={20} />} title="手动文本入库" desc="用于快速粘贴测试资料，验证切片、向量写入、BM25 写入和检索链路。">
        <div className="grid gap-4">
          <Field label="文件名">
            <input value={manualFilename} onChange={(event) => setManualFilename(event.target.value)} className="input" placeholder="iceland-nature-note.txt" />
          </Field>
          <Field label="文本内容">
            <textarea
              value={manualText}
              onChange={(event) => setManualText(event.target.value)}
              className="input min-h-[150px] resize-none leading-7"
              placeholder="粘贴一段旅行资料，例如冰岛南岸景点、预算、住宿或交通建议..."
            />
          </Field>
          <div className="flex justify-end">
            <SoftButton onClick={handleManualIngest} tone="primary" disabled={!manualText.trim() || uploading}>
              {uploading ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
              写入知识库
            </SoftButton>
          </div>
        </div>
      </ModuleCard>

      <ModuleCard icon={<Database size={20} />} title="已入库文件" desc="这里用于核对上传后的文件级结果：切片数量、策略、来源和文档 ID。">
        {!stats || (stats.documents?.length ?? 0) === 0 ? (
          <EmptyState>暂无入库文件。上传或粘贴一段资料后，这里会显示文件级切片结果。</EmptyState>
        ) : (
          <div className="space-y-3">
            {stats.documents?.map((document) => (
              <div key={document.document_id} className="rounded-4xl bg-[#F8F6F1] px-5 py-4">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{document.filename}</p>
                    <p className="mt-1 text-xs text-muted">{document.document_id}</p>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs text-muted">
                    <span className="rounded-full bg-paper px-2.5 py-1">{document.chunk_count} chunks</span>
                    <span className="rounded-full bg-paper px-2.5 py-1">{document.strategy ?? 'unknown'}</span>
                    {document.doc_type && <span className="rounded-full bg-paper px-2.5 py-1">{document.doc_type}</span>}
                    {document.source && <span className="rounded-full bg-paper px-2.5 py-1">{document.source}</span>}
                  </div>
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
    <div className="rounded-3xl bg-[#F8F6F1] px-4 py-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold text-ink">{value}</p>
    </div>
  )
}
