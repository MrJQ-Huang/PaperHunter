import { useState, useEffect, useCallback } from 'react'
import { usePaperStore, Paper, Task } from '../stores/paperStore'
import PaperCard from '../components/PaperCard'
import { BookOpen, RefreshCw, ChevronLeft, ChevronRight, Search, Trash2, X, Download, AlertCircle, Clock, ArrowDownWideNarrow, ArrowUpNarrowWide, Star, Filter } from 'lucide-react'

const SOURCE_OPTIONS = [
  { value: '', label: '全部来源' },
  { value: 'arxiv', label: 'arXiv' },
  { value: 'semantic_scholar', label: 'Semantic Scholar' },
  { value: 'openalex', label: 'OpenAlex' },
  { value: 'crossref', label: 'CrossRef' },
  { value: 'google_scholar', label: 'Google Scholar' },
]

const SORT_OPTIONS = [
  { value: 'relevance', label: '相关度', icon: Star },
  { value: 'citations', label: '引用↓', icon: ArrowDownWideNarrow },
  { value: 'citations_asc', label: '引用↑', icon: ArrowUpNarrowWide },
  { value: 'date', label: '时间↓', icon: Clock },
]

const DOWNLOAD_FILTERS = [
  { value: '', label: '全部', icon: null },
  { value: 'downloaded', label: '已下载', icon: Download },
  { value: 'pending', label: '待下载', icon: Clock },
  { value: 'failed', label: '失败', icon: AlertCircle },
]

export default function PaperList() {
  const papers = usePaperStore((s) => s.papers)
  const total = usePaperStore((s) => s.total)
  const setPapers = usePaperStore((s) => s.setPapers)
  const removePaper = usePaperStore((s) => s.removePaper)
  const updatePaper = usePaperStore((s) => s.updatePaper)
  const tasks = usePaperStore((s) => s.tasks)
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState('relevance')
  const [selectedTaskId, setSelectedTaskId] = useState('')
  const [downloadStatus, setDownloadStatus] = useState('')
  const [source, setSource] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [editingPaper, setEditingPaper] = useState<Paper | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)
  const perPage = 20

  const fetchPapers = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        page: String(page),
        per_page: String(perPage),
        sort,
      })
      if (selectedTaskId) params.set('task_id', selectedTaskId)
      if (search) params.set('search', search)
      if (downloadStatus) params.set('download_status', downloadStatus)
      if (source) params.set('source', source)
      const resp = await fetch(`/api/papers?${params}`)
      if (resp.ok) {
        const data = await resp.json()
        setPapers(data.papers, data.total)
      }
    } catch {} finally {
      setLoading(false)
    }
  }, [page, sort, selectedTaskId, search, downloadStatus, source, setPapers])

  useEffect(() => {
    fetchPapers()
  }, [fetchPapers])

  useEffect(() => {
    if (tasks.length === 0) {
      fetch('/api/tasks').then(r => r.json()).then(data => {
        usePaperStore.getState().setTasks(data)
      }).catch(() => {})
    }
  }, [tasks.length])

  const handleDownload = async (paperId: string) => {
    try {
      await fetch(`/api/papers/${paperId}/download`, { method: 'POST' })
    } catch {}
  }

  const handleDelete = async (paperId: string) => {
    try {
      const resp = await fetch(`/api/papers/${paperId}`, { method: 'DELETE' })
      if (resp.ok) {
        removePaper(paperId)
      }
    } catch {}
  }

  const handleClearAll = async () => {
    if (!confirmClear) {
      setConfirmClear(true)
      setTimeout(() => setConfirmClear(false), 5000)
      return
    }
    try {
      const taskParam = selectedTaskId ? `?task_id=${selectedTaskId}` : ''
      const resp = await fetch(`/api/papers${taskParam}`, { method: 'DELETE' })
      if (resp.ok) {
        setPapers([], 0)
        setConfirmClear(false)
      }
    } catch {}
  }

  const handleSaveEdit = async () => {
    if (!editingPaper) return
    try {
      const resp = await fetch(`/api/papers/${editingPaper.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: editingPaper.title,
          authors: editingPaper.authors,
          abstract: editingPaper.abstract,
          doi: editingPaper.doi,
          url: editingPaper.url,
          venue: editingPaper.venue,
          citation_count: editingPaper.citation_count,
          is_open_access: editingPaper.is_open_access,
        }),
      })
      if (resp.ok) {
        const updated = await resp.json()
        updatePaper(updated)
        setEditingPaper(null)
      }
    } catch {}
  }

  const totalPages = Math.ceil(total / perPage)

  return (
    <div className="grid grid-cols-12 gap-6">
      {/* 左侧筛选 */}
      <div className="col-span-3 space-y-4">
        {/* 下载状态 */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <span className="font-medium text-sm text-gray-800 block mb-2">下载状态</span>
          <div className="flex flex-wrap gap-1.5">
            {DOWNLOAD_FILTERS.map((opt) => {
              const Icon = opt.icon
              return (
                <button
                  key={opt.value}
                  onClick={() => { setDownloadStatus(opt.value); setPage(1) }}
                  className={`flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg transition-colors ${
                    downloadStatus === opt.value
                      ? 'bg-violet-50 text-violet-600 font-medium'
                      : 'text-gray-500 hover:bg-gray-50'
                  }`}
                >
                  {Icon && <Icon size={12} />}
                  {opt.label}
                </button>
              )
            })}
          </div>
        </div>

        {/* 任务筛选 */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <span className="font-medium text-sm text-gray-800 block mb-2">按任务筛选</span>
          <select
            value={selectedTaskId}
            onChange={(e) => { setSelectedTaskId(e.target.value); setPage(1) }}
            className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-200"
          >
            <option value="">全部任务</option>
            {tasks.map((task) => (
              <option key={task.id} value={task.id}>{task.query}</option>
            ))}
          </select>
        </div>

        {/* 来源筛选 */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <span className="font-medium text-sm text-gray-800 block mb-2">数据来源</span>
          <div className="flex flex-wrap gap-1.5">
            {SOURCE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => { setSource(opt.value); setPage(1) }}
                className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
                  source === opt.value
                    ? 'bg-violet-50 text-violet-600 font-medium'
                    : 'text-gray-500 hover:bg-gray-50'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* 排序 */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <span className="font-medium text-sm text-gray-800 block mb-2">排序方式</span>
          <div className="space-y-1">
            {SORT_OPTIONS.map((opt) => {
              const Icon = opt.icon
              return (
                <button
                  key={opt.value}
                  onClick={() => { setSort(opt.value); setPage(1) }}
                  className={`flex items-center gap-2 w-full text-left px-3 py-1.5 text-sm rounded-lg transition-colors ${
                    sort === opt.value
                      ? 'bg-violet-50 text-violet-600'
                      : 'text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  <Icon size={13} />
                  {opt.label}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* 右侧论文列表 */}
      <div className="col-span-9">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <BookOpen size={20} className="text-primary-500" />
            <h2 className="font-semibold text-gray-800">论文库</h2>
            <span className="text-sm text-gray-400">共 {total} 篇</span>
          </div>
          <div className="flex items-center gap-2">
            {/* 搜索框 */}
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1) }}
                placeholder="搜索标题/作者/摘要..."
                className="pl-8 pr-8 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 w-52"
              />
              {search && (
                <button
                  onClick={() => setSearch('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  <X size={14} />
                </button>
              )}
            </div>
            {/* 清空按钮 */}
            <button
              onClick={handleClearAll}
              className={`flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg transition-colors ${
                confirmClear
                  ? 'bg-red-500 text-white'
                  : 'text-red-500 hover:bg-red-50'
              }`}
            >
              <Trash2 size={14} />
              {confirmClear ? '确认清空' : '清空'}
            </button>
            {/* 刷新按钮 */}
            <button
              onClick={fetchPapers}
              className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800"
            >
              <RefreshCw size={14} />
              刷新
            </button>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-12 text-gray-400">
            <RefreshCw size={24} className="mx-auto mb-2 animate-spin" />
            加载中...
          </div>
        ) : papers.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <BookOpen size={48} className="mx-auto mb-4 text-gray-300" />
            <p>{search ? '未找到匹配的论文' : '暂无论文'}</p>
            <p className="text-sm mt-1">{search ? '请尝试其他关键词' : '请先在任务监控页面搜索论文'}</p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {papers.map((paper) => (
                <PaperCard
                  key={paper.id}
                  paper={paper}
                  onDownload={handleDownload}
                  onEdit={setEditingPaper}
                  onDelete={handleDelete}
                />
              ))}
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-2 mt-6">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-50"
                >
                  <ChevronLeft size={16} />
                </button>
                <span className="text-sm text-gray-600">
                  第 {page} / {totalPages} 页
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-50"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* 编辑弹窗 */}
      {editingPaper && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={() => setEditingPaper(null)}>
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6 max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-gray-800">编辑论文信息</h3>
              <button onClick={() => setEditingPaper(null)} className="text-gray-400 hover:text-gray-600">
                <X size={18} />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs text-gray-500 mb-1">标题</label>
                <input
                  type="text"
                  value={editingPaper.title}
                  onChange={(e) => setEditingPaper({ ...editingPaper, title: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">作者（逗号分隔）</label>
                <input
                  type="text"
                  value={editingPaper.authors.join(', ')}
                  onChange={(e) => setEditingPaper({ ...editingPaper, authors: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">摘要</label>
                <textarea
                  value={editingPaper.abstract}
                  onChange={(e) => setEditingPaper({ ...editingPaper, abstract: e.target.value })}
                  rows={4}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">DOI</label>
                  <input
                    type="text"
                    value={editingPaper.doi || ''}
                    onChange={(e) => setEditingPaper({ ...editingPaper, doi: e.target.value || null })}
                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">期刊/会议</label>
                  <input
                    type="text"
                    value={editingPaper.venue || ''}
                    onChange={(e) => setEditingPaper({ ...editingPaper, venue: e.target.value || null })}
                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">链接</label>
                  <input
                    type="text"
                    value={editingPaper.url}
                    onChange={(e) => setEditingPaper({ ...editingPaper, url: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">引用数</label>
                  <input
                    type="number"
                    value={editingPaper.citation_count ?? ''}
                    onChange={(e) => setEditingPaper({ ...editingPaper, citation_count: e.target.value ? parseInt(e.target.value) : null })}
                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              </div>

              <label className="flex items-center gap-2 text-sm text-gray-600">
                <input
                  type="checkbox"
                  checked={editingPaper.is_open_access}
                  onChange={(e) => setEditingPaper({ ...editingPaper, is_open_access: e.target.checked })}
                  className="rounded border-gray-300"
                />
                开放获取 (Open Access)
              </label>
            </div>

            <div className="flex justify-end gap-2 mt-5">
              <button
                onClick={() => setEditingPaper(null)}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
              >
                取消
              </button>
              <button
                onClick={handleSaveEdit}
                className="px-4 py-2 text-sm bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
