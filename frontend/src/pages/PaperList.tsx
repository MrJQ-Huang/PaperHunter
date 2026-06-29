import { useState, useEffect, useCallback, useMemo } from 'react'
import { usePaperStore, Paper, Task } from '../stores/paperStore'
import PaperCard from '../components/PaperCard'
import { BookOpen, RefreshCw, ChevronDown, ChevronLeft, ChevronRight, Search, Trash2, X, Download, AlertCircle, Clock, ArrowDownWideNarrow, ArrowUpNarrowWide, Star, GitBranch, Network, CalendarDays, Layers3, Sparkles, SlidersHorizontal, Eye, Loader2 } from 'lucide-react'

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

const PAPER_TYPE_FILTERS = [
  { value: '', label: '全部类型' },
  { value: 'survey', label: '综述' },
  { value: 'benchmark', label: 'Benchmark' },
  { value: 'dataset', label: '数据集' },
  { value: 'method', label: '方法' },
  { value: 'system', label: '系统' },
]

const LEARNING_ROLE_FILTERS = [
  { value: '', label: '全部角色' },
  { value: 'field_overview', label: '入门综述' },
  { value: 'foundation', label: '基础必读' },
  { value: 'representative_method', label: '代表方法' },
  { value: 'recent_frontier', label: '前沿' },
  { value: 'benchmark_or_dataset', label: 'Benchmark' },
  { value: 'implementation_reference', label: '实现参考' },
]

const typeLabels: Record<string, string> = {
  survey: '综述',
  benchmark: 'Benchmark',
  dataset: '数据集',
  method: '方法',
  system: '系统',
  application: '应用',
  theory: '理论',
  unknown: '未分类',
}

const roleLabels: Record<string, string> = {
  field_overview: '入门综述',
  foundation: '基础必读',
  representative_method: '代表方法',
  recent_frontier: '前沿',
  benchmark_or_dataset: 'Benchmark',
  implementation_reference: '实现参考',
  niche_detail: '细分参考',
}

type GraphBranch = {
  name: string
  intent?: string
  papers: Paper[]
  count: number
  years: number[]
}

const getPaperYear = (paper: Paper) => {
  if (!paper.published_date) return null
  const year = new Date(paper.published_date).getFullYear()
  return Number.isFinite(year) ? year : null
}

const pickCorePapers = (papers: Paper[]) => {
  const ranked = [...papers].sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0))
  const strong = ranked.filter((p) => (p.relevance_score || 0) >= 6.5)
  return (strong.length > 0 ? strong : ranked.slice(0, 3)).slice(0, 6)
}

const scoreOf = (paper: Paper) => paper.relevance_score ?? 0

const normalizeTopic = (value: string) => value.trim().toLowerCase()

const asStringList = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.map(String).filter(Boolean)
  if (typeof value === 'string' && value.trim()) return [value.trim()]
  return []
}

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
  const [paperType, setPaperType] = useState('')
  const [learningRole, setLearningRole] = useState('')
  const [subtopic, setSubtopic] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [editingPaper, setEditingPaper] = useState<Paper | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)
  const [selectedPapers, setSelectedPapers] = useState<Set<string>>(new Set())
  const [downloading, setDownloading] = useState(false)
  const [downloadingPaperIds, setDownloadingPaperIds] = useState<Set<string>>(new Set())
  const [graphPapers, setGraphPapers] = useState<Paper[]>([])
  const [graphLoading, setGraphLoading] = useState(false)
  const [coreCollapsed, setCoreCollapsed] = useState(false)
  const [lowRelevanceCollapsed, setLowRelevanceCollapsed] = useState(true)
  const [scoreThreshold, setScoreThreshold] = useState(5)
  const perPage = 20
  const activeTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) || tasks[0] || null,
    [tasks, selectedTaskId]
  )
  const activeTaskId = selectedTaskId || activeTask?.id || ''
  const relevantGraphPapers = useMemo(
    () => graphPapers.filter((paper) => scoreOf(paper) >= scoreThreshold),
    [graphPapers, scoreThreshold]
  )
  const lowRelevancePapers = useMemo(
    () => graphPapers.filter((paper) => scoreOf(paper) < scoreThreshold),
    [graphPapers, scoreThreshold]
  )
  const visiblePapers = useMemo(
    () => papers.filter((paper) => scoreOf(paper) >= scoreThreshold),
    [papers, scoreThreshold]
  )
  const hiddenPageCount = papers.length - visiblePapers.length
  const corePapers = useMemo(() => pickCorePapers(relevantGraphPapers), [relevantGraphPapers])

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
      if (paperType) params.set('paper_type', paperType)
      if (learningRole) params.set('learning_role', learningRole)
      if (subtopic) params.set('subtopic', subtopic)
      const resp = await fetch(`/api/papers?${params}`)
      if (resp.ok) {
        const data = await resp.json()
        setPapers(data.papers, data.total)
      }
    } catch {} finally {
      setLoading(false)
    }
  }, [page, sort, selectedTaskId, search, downloadStatus, source, paperType, learningRole, subtopic, setPapers])

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

  useEffect(() => {
    if (!activeTaskId) {
      setGraphPapers([])
      return
    }
    setGraphLoading(true)
    const params = new URLSearchParams({
      task_id: activeTaskId,
      page: '1',
      per_page: '10000',
      sort: 'date',
    })
    fetch(`/api/papers?${params}`)
      .then((resp) => resp.ok ? resp.json() : null)
      .then((data) => setGraphPapers(data?.papers || []))
      .catch(() => setGraphPapers([]))
      .finally(() => setGraphLoading(false))
  }, [activeTaskId])

  const markDownloading = (ids: string[], active: boolean) => {
    setDownloadingPaperIds((prev) => {
      const next = new Set(prev)
      ids.forEach((id) => {
        if (active) next.add(id)
        else next.delete(id)
      })
      return next
    })
  }

  const refreshPaper = async (paperId: string) => {
    const resp = await fetch(`/api/papers/${paperId}`)
    if (!resp.ok) return null
    const paper = await resp.json() as Paper
    updatePaper(paper)
    setGraphPapers((prev) => prev.map((p) => (p.id === paper.id ? paper : p)))
    return paper
  }

  const pollDownloadProgress = async (taskId: string, paperIds: string[]) => {
    let remaining = new Set(paperIds)
    for (let i = 0; i < 80 && remaining.size > 0; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1500))
      const params = new URLSearchParams({
        task_id: taskId,
        page: '1',
        per_page: '10000',
        sort: 'date',
      })
      const resp = await fetch(`/api/papers?${params}`)
      if (!resp.ok) continue
      const data = await resp.json()
      const latest = (data?.papers || []) as Paper[]
      const byId = new Map(latest.map((paper) => [paper.id, paper]))
      setGraphPapers(latest)
      setDownloadingPaperIds((prev) => {
        const next = new Set(prev)
        paperIds.forEach((id) => {
          const paper = byId.get(id)
          if (paper && paper.download_status !== 'pending') next.delete(id)
        })
        return next
      })
      remaining = new Set(paperIds.filter((id) => {
        const paper = byId.get(id)
        return !paper || paper.download_status === 'pending'
      }))
      await fetchPapers()
    }
    markDownloading(Array.from(remaining), false)
  }

  const handleDownload = async (paperId: string) => {
    markDownloading([paperId], true)
    try {
      const resp = await fetch(`/api/papers/${paperId}/download`, { method: 'POST' })
      if (resp.ok) {
        await refreshPaper(paperId)
        await fetchPapers()
      }
    } catch {
    } finally {
      markDownloading([paperId], false)
    }
  }

  const handleDeletePdf = async (paperId: string) => {
    try {
      const resp = await fetch(`/api/papers/${paperId}/pdf`, { method: 'DELETE' })
      if (resp.ok) {
        const data = await resp.json()
        if (data?.paper) {
          updatePaper(data.paper)
          setGraphPapers((prev) => prev.map((p) => (p.id === paperId ? data.paper : p)))
        }
        await fetchPapers()
      }
    } catch {}
  }

  const handleDownloadAll = async () => {
    setDownloading(true)
    const downloadPool = graphPapers.length > 0 ? graphPapers : visiblePapers
    const ids = downloadPool
      .filter((paper) => paper.download_status === 'pending' || paper.download_status === 'failed')
      .map((paper) => paper.id)
    markDownloading(ids, true)
    try {
      // 找到当前任务的 task_id
      const taskId = selectedTaskId || (tasks.length > 0 ? tasks[0].id : '')
      if (!taskId) {
        markDownloading(ids, false)
        return
      }
      const resp = await fetch(`/api/tasks/${taskId}/download`, { method: 'POST' })
      if (resp.ok) {
        await pollDownloadProgress(taskId, ids)
      } else {
        markDownloading(ids, false)
      }
    } catch {
      markDownloading(ids, false)
    } finally {
      setDownloading(false)
    }
  }

  const handleDownloadSelected = async () => {
    if (selectedPapers.size === 0) return
    setDownloading(true)
    const ids = Array.from(selectedPapers)
    markDownloading(ids, true)
    try {
      const taskId = selectedTaskId || (tasks.length > 0 ? tasks[0].id : '')
      if (!taskId) {
        markDownloading(ids, false)
        return
      }
      const resp = await fetch(`/api/tasks/${taskId}/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paper_ids: ids }),
      })
      if (resp.ok) {
        setSelectedPapers(new Set())
        await pollDownloadProgress(taskId, ids)
      } else {
        markDownloading(ids, false)
      }
    } catch {
      markDownloading(ids, false)
    } finally {
      setDownloading(false)
    }
  }

  const toggleSelect = (paperId: string) => {
    setSelectedPapers(prev => {
      const next = new Set(prev)
      if (next.has(paperId)) next.delete(paperId)
      else next.add(paperId)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (visiblePapers.length === 0) return
    const visibleIds = visiblePapers.map(p => p.id)
    const allVisibleSelected = visibleIds.every((id) => selectedPapers.has(id))
    if (allVisibleSelected) {
      setSelectedPapers(new Set())
    } else {
      setSelectedPapers(new Set(visibleIds))
    }
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

  const graphData = useMemo(() => {
    const planSubtopics = activeTask?.search_plan?.subtopics || []
    const branchMap = new Map<string, GraphBranch>()

    planSubtopics.forEach((item) => {
      const name = item.name?.trim()
      if (!name) return
      branchMap.set(normalizeTopic(name), {
        name,
        intent: item.intent,
        papers: [],
        count: 0,
        years: [],
      })
    })

    relevantGraphPapers.forEach((paper) => {
      const names = [
        ...asStringList(paper.subtopics),
        paper.search_subtopic || '',
      ].filter(Boolean)
      const branchNames = names.length > 0 ? names : ['未归类']

      branchNames.forEach((name) => {
        const key = normalizeTopic(name)
        const branch = branchMap.get(key) || {
          name,
          papers: [],
          count: 0,
          years: [],
        }
        if (!branch.papers.some((p) => p.id === paper.id)) {
          branch.papers.push(paper)
        }
        branchMap.set(key, branch)
      })
    })

    const branches = Array.from(branchMap.values()).map((branch) => {
      const papersByDate = [...branch.papers].sort((a, b) => {
        const ay = getPaperYear(a) || 9999
        const by = getPaperYear(b) || 9999
        return ay - by || (b.relevance_score || 0) - (a.relevance_score || 0)
      })
      const years = Array.from(new Set(papersByDate.map(getPaperYear).filter((y): y is number => y !== null))).sort((a, b) => a - b)
      return {
        ...branch,
        papers: papersByDate,
        count: papersByDate.length,
        years,
      }
    }).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))

    const typeCounts = relevantGraphPapers.reduce<Record<string, number>>((acc, paper) => {
      const type = paper.paper_type || 'unknown'
      acc[type] = (acc[type] || 0) + 1
      return acc
    }, {})

    return {
      domain: activeTask?.search_plan?.domain || activeTask?.query || '当前任务',
      goal: activeTask?.search_plan?.goal || activeTask?.query || '',
      branches,
      typeCounts,
      yearRange: relevantGraphPapers
        .map(getPaperYear)
        .filter((year): year is number => year !== null)
        .sort((a, b) => a - b),
    }
  }, [activeTask, relevantGraphPapers])

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

        {/* 标签筛选 */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <span className="font-medium text-sm text-gray-800 block mb-2">文献类型</span>
          <div className="flex flex-wrap gap-1.5">
            {PAPER_TYPE_FILTERS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => { setPaperType(opt.value); setPage(1) }}
                className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
                  paperType === opt.value ? 'bg-violet-50 text-violet-600 font-medium' : 'text-gray-500 hover:bg-gray-50'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <span className="font-medium text-sm text-gray-800 block mb-2">学习角色</span>
          <div className="flex flex-wrap gap-1.5">
            {LEARNING_ROLE_FILTERS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => { setLearningRole(opt.value); setPage(1) }}
                className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
                  learningRole === opt.value ? 'bg-amber-50 text-amber-700 font-medium' : 'text-gray-500 hover:bg-gray-50'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <input
            type="text"
            value={subtopic}
            onChange={(e) => { setSubtopic(e.target.value); setPage(1) }}
            placeholder="子方向关键词..."
            className="mt-3 w-full px-2 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-200"
          />
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center justify-between gap-2 mb-2">
            <span className="font-medium text-sm text-gray-800 flex items-center gap-1.5">
              <SlidersHorizontal size={14} className="text-violet-500" />
              相关性阈值
            </span>
            <span className="text-xs font-semibold text-violet-600">{scoreThreshold.toFixed(1)}+</span>
          </div>
          <input
            type="range"
            min="0"
            max="8"
            step="0.5"
            value={scoreThreshold}
            onChange={(e) => setScoreThreshold(Number(e.target.value))}
            className="w-full accent-violet-500"
          />
          <div className="mt-2 grid grid-cols-4 gap-1">
            {[
              { value: 0, label: '全部' },
              { value: 3, label: '宽松' },
              { value: 5, label: '推荐' },
              { value: 6.5, label: '严格' },
            ].map((item) => (
              <button
                key={item.value}
                onClick={() => setScoreThreshold(item.value)}
                className={`px-2 py-1 text-[11px] rounded-lg transition-colors ${
                  scoreThreshold === item.value ? 'bg-violet-50 text-violet-600 font-medium' : 'text-gray-500 hover:bg-gray-50'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg bg-emerald-50 px-2 py-1.5">
              <span className="block text-emerald-500">保留</span>
              <span className="font-semibold text-emerald-700">{relevantGraphPapers.length}</span>
            </div>
            <button
              onClick={() => setLowRelevanceCollapsed((value) => !value)}
              className="rounded-lg bg-gray-50 px-2 py-1.5 text-left hover:bg-gray-100"
            >
              <span className="block text-gray-400">隔离</span>
              <span className="font-semibold text-gray-700">{lowRelevancePapers.length}</span>
            </button>
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
            {scoreThreshold > 0 && (
              <span className="text-xs text-violet-500 bg-violet-50 rounded-full px-2 py-0.5">
                当前页显示 {visiblePapers.length} 篇，隐藏 {hiddenPageCount} 篇
              </span>
            )}
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
            {/* 全选/下载按钮 */}
            {visiblePapers.length > 0 && (
              <>
                <button
                  onClick={toggleSelectAll}
                  className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800 border border-gray-200 rounded-lg"
                >
                  {visiblePapers.every((paper) => selectedPapers.has(paper.id)) ? '取消全选' : '全选'}
                </button>
                {selectedPapers.size > 0 && (
                  <button
                    onClick={handleDownloadSelected}
                    disabled={downloading}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm bg-emerald-50 text-emerald-600 rounded-lg hover:bg-emerald-100 disabled:opacity-50"
                  >
                    {downloading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                    下载选中 ({selectedPapers.size})
                  </button>
                )}
              </>
            )}
            {/* 下载全部 */}
            <button
              onClick={handleDownloadAll}
              disabled={downloading}
              className="flex items-center gap-1 px-3 py-1.5 text-sm text-emerald-600 hover:text-emerald-700 border border-emerald-200 rounded-lg hover:bg-emerald-50 disabled:opacity-50"
            >
              {downloading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
              {downloading ? '下载中...' : '下载全部'}
            </button>
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

        <div className="bg-white border border-gray-200 rounded-xl p-4 mb-4">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <Network size={16} className="text-violet-500" />
                <h3 className="font-semibold text-gray-800 text-sm">任务知识图谱</h3>
                {graphLoading && <RefreshCw size={12} className="text-gray-300 animate-spin" />}
              </div>
              <p className="text-xs text-gray-500 line-clamp-1">{graphData.goal || graphData.domain}</p>
            </div>
            <button
              onClick={() => { setSelectedTaskId(activeTaskId); setSubtopic(''); setSearch(''); setPage(1) }}
              disabled={!activeTaskId}
              className="shrink-0 px-3 py-1.5 text-xs border border-gray-200 rounded-lg text-gray-500 hover:bg-gray-50 disabled:opacity-40"
            >
              查看全部分支
            </button>
          </div>

          <div className="grid grid-cols-12 gap-4">
            <div className="col-span-12 xl:col-span-3">
              <button
                onClick={() => { setSelectedTaskId(activeTaskId); setSubtopic(''); setPage(1) }}
                className="w-full text-left rounded-xl border border-violet-100 bg-violet-50/70 p-4 hover:bg-violet-50 transition-colors"
              >
                <div className="flex items-center gap-2 mb-2">
                  <Layers3 size={16} className="text-violet-500" />
                  <span className="text-xs font-semibold text-violet-600">大领域</span>
                </div>
                <div className="font-semibold text-gray-900 text-sm line-clamp-2">{graphData.domain}</div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-500">
                  <div>
                    <span className="block text-gray-400">保留论文</span>
                    <span className="font-semibold text-gray-700">{relevantGraphPapers.length}</span>
                  </div>
                  <div>
                    <span className="block text-gray-400">分支</span>
                    <span className="font-semibold text-gray-700">{graphData.branches.length}</span>
                  </div>
                  <div className="col-span-2">
                    <span className="block text-gray-400">隔离</span>
                    <span className="font-semibold text-gray-700">{lowRelevancePapers.length} 篇低相关</span>
                  </div>
                  <div className="col-span-2">
                    <span className="block text-gray-400">时间</span>
                    <span className="font-semibold text-gray-700">
                      {graphData.yearRange.length > 0
                        ? `${graphData.yearRange[0]}-${graphData.yearRange[graphData.yearRange.length - 1]}`
                        : '暂无'}
                    </span>
                  </div>
                </div>
              </button>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {Object.entries(graphData.typeCounts).slice(0, 6).map(([type, count]) => (
                  <button
                    key={type}
                    onClick={() => { setPaperType(type === 'unknown' ? '' : type); setPage(1) }}
                    className="px-2 py-1 text-[11px] rounded bg-gray-50 text-gray-500 hover:bg-gray-100"
                  >
                    {typeLabels[type] || type} {count}
                  </button>
                ))}
              </div>
            </div>

            <div className="col-span-12 xl:col-span-9 overflow-x-auto">
              {graphData.branches.length === 0 ? (
                <div className="h-full min-h-[180px] flex items-center justify-center text-sm text-gray-300 border border-dashed border-gray-200 rounded-xl">
                  当前任务还没有可绘制的子方向标签
                </div>
              ) : (
                <div className="flex gap-3 min-w-max pb-1">
                  {graphData.branches.slice(0, 10).map((branch) => {
                    const selected = normalizeTopic(subtopic) === normalizeTopic(branch.name)
                    const milestonePapers = branch.papers.slice(0, 6)
                    return (
                      <div
                        key={branch.name}
                        className={`w-72 rounded-xl border p-3 transition-colors ${
                          selected ? 'border-violet-300 bg-violet-50/60' : 'border-gray-200 bg-white'
                        }`}
                      >
                        <button
                          onClick={() => {
                            setSelectedTaskId(activeTaskId)
                            setSubtopic(branch.name)
                            setSearch('')
                            setPage(1)
                          }}
                          className="w-full text-left"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <GitBranch size={14} className={selected ? 'text-violet-500 shrink-0' : 'text-gray-400 shrink-0'} />
                              <span className="text-sm font-semibold text-gray-800 line-clamp-1">{branch.name}</span>
                            </div>
                            <span className="text-xs text-gray-400 shrink-0">{branch.count} 篇</span>
                          </div>
                          {branch.intent && <p className="mt-1 text-[11px] text-gray-400 line-clamp-2">{branch.intent}</p>}
                        </button>

                        <div className="mt-3 border-l border-gray-200 pl-3 space-y-2">
                          {milestonePapers.length === 0 ? (
                            <div className="text-xs text-gray-300 py-8">等待该分支补充论文</div>
                          ) : milestonePapers.map((paper) => {
                            const year = getPaperYear(paper)
                            return (
                              <button
                                key={paper.id}
                                onClick={() => {
                                  setSelectedTaskId(activeTaskId)
                                  setSubtopic(branch.name)
                                  setSearch(paper.title)
                                  setPage(1)
                                }}
                                className="relative block w-full text-left rounded-lg px-2 py-1.5 hover:bg-gray-50"
                              >
                                <span className="absolute -left-[17px] top-3 w-2 h-2 rounded-full bg-violet-300 border border-white" />
                                <div className="flex items-center gap-2 mb-0.5">
                                  <CalendarDays size={11} className="text-gray-300" />
                                  <span className="text-[11px] font-medium text-gray-500">{year || '未知年份'}</span>
                                  {paper.paper_type && (
                                    <span className="text-[10px] text-gray-400 bg-gray-50 rounded px-1">
                                      {typeLabels[paper.paper_type] || paper.paper_type}
                                    </span>
                                  )}
                                </div>
                                <div className="text-xs text-gray-700 line-clamp-2">{paper.title}</div>
                                {paper.learning_role && (
                                  <div className="mt-0.5 text-[10px] text-amber-600">
                                    {roleLabels[paper.learning_role] || paper.learning_role}
                                  </div>
                                )}
                              </button>
                            )
                          })}
                        </div>

                        {branch.years.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-1">
                            {branch.years.slice(0, 8).map((year) => (
                              <span key={year} className="text-[10px] text-gray-400 bg-gray-50 px-1.5 py-0.5 rounded">
                                {year}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>

        {corePapers.length > 0 && (
          <div className="bg-amber-50/70 border border-amber-100 rounded-xl p-4 mb-4">
            <div className={`flex items-start justify-between gap-3 ${coreCollapsed ? '' : 'mb-3'}`}>
              <div>
                <div className="flex items-center gap-2">
                  <Sparkles size={16} className="text-amber-500" />
                  <h3 className="font-semibold text-gray-900 text-sm">核心论文池</h3>
                  <span className="text-[11px] text-amber-700 bg-amber-100 rounded-full px-2 py-0.5">
                    {corePapers.length} 篇优先阅读
                  </span>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  根据当前任务的语义评分自动提取，优先展示最可能支撑领域脉络的关键论文。
                </p>
              </div>
              <div className="shrink-0 flex items-center gap-2">
                <button
                  onClick={() => { setSort('relevance'); setSearch(''); setSubtopic(''); setPage(1) }}
                  className="px-3 py-1.5 text-xs rounded-lg bg-white/80 text-amber-700 border border-amber-100 hover:bg-white"
                >
                  按评分查看全部
                </button>
                <button
                  onClick={() => setCoreCollapsed((value) => !value)}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-white/80 text-amber-700 border border-amber-100 hover:bg-white"
                >
                  {coreCollapsed ? '展开' : '收起'}
                  <ChevronDown size={13} className={`transition-transform ${coreCollapsed ? '-rotate-90' : ''}`} />
                </button>
              </div>
            </div>
            {!coreCollapsed && (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                {corePapers.map((paper) => (
                  <PaperCard
                    key={paper.id}
                    paper={paper}
                    featured
                    compact
                    onDownload={handleDownload}
                    onDeletePdf={handleDeletePdf}
                    onEdit={setEditingPaper}
                    onDelete={handleDelete}
                    selected={selectedPapers.has(paper.id)}
                    onToggleSelect={toggleSelect}
                    downloading={downloadingPaperIds.has(paper.id)}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {lowRelevancePapers.length > 0 && (
          <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 mb-4">
            <div className={`flex items-start justify-between gap-3 ${lowRelevanceCollapsed ? '' : 'mb-3'}`}>
              <div>
                <div className="flex items-center gap-2">
                  <Eye size={16} className="text-gray-400" />
                  <h3 className="font-semibold text-gray-800 text-sm">低相关隔离区</h3>
                  <span className="text-[11px] text-gray-500 bg-white rounded-full px-2 py-0.5">
                    {lowRelevancePapers.length} 篇已从图谱和主列表隐藏
                  </span>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  这些论文评分低于当前阈值，暂不参与分支主视图；展开后仍可人工复核。
                </p>
              </div>
              <div className="shrink-0 flex items-center gap-2">
                <button
                  onClick={() => setScoreThreshold(0)}
                  className="px-3 py-1.5 text-xs rounded-lg bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
                >
                  显示全部
                </button>
                <button
                  onClick={() => setLowRelevanceCollapsed((value) => !value)}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
                >
                  {lowRelevanceCollapsed ? '展开' : '收起'}
                  <ChevronDown size={13} className={`transition-transform ${lowRelevanceCollapsed ? '-rotate-90' : ''}`} />
                </button>
              </div>
            </div>
            {!lowRelevanceCollapsed && (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                {lowRelevancePapers
                  .slice()
                  .sort((a, b) => scoreOf(b) - scoreOf(a))
                  .slice(0, 20)
                  .map((paper) => (
                    <PaperCard
                      key={paper.id}
                      paper={paper}
                      compact
                      onDownload={handleDownload}
                      onDeletePdf={handleDeletePdf}
                      onEdit={setEditingPaper}
                      onDelete={handleDelete}
                      selected={selectedPapers.has(paper.id)}
                      onToggleSelect={toggleSelect}
                      downloading={downloadingPaperIds.has(paper.id)}
                    />
                  ))}
              </div>
            )}
          </div>
        )}

        {loading ? (
          <div className="text-center py-12 text-gray-400">
            <RefreshCw size={24} className="mx-auto mb-2 animate-spin" />
            加载中...
          </div>
        ) : visiblePapers.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <BookOpen size={48} className="mx-auto mb-4 text-gray-300" />
            <p>{papers.length > 0 ? '当前阈值下没有可显示论文' : search ? '未找到匹配的论文' : '暂无论文'}</p>
            <p className="text-sm mt-1">{papers.length > 0 ? '降低相关性阈值即可查看被隔离论文' : search ? '请尝试其他关键词' : '请先在任务监控页面搜索论文'}</p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {visiblePapers.map((paper) => (
                <PaperCard
                  key={paper.id}
                  paper={paper}
                  onDownload={handleDownload}
                  onDeletePdf={handleDeletePdf}
                  onEdit={setEditingPaper}
                  onDelete={handleDelete}
                  selected={selectedPapers.has(paper.id)}
                  onToggleSelect={toggleSelect}
                  downloading={downloadingPaperIds.has(paper.id)}
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
