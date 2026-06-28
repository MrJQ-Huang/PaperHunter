import { useState, useRef, useCallback, useEffect } from 'react'
import { Paper } from '../stores/paperStore'
import PaperCard from './PaperCard'
import { ChevronLeft, ChevronRight, Search, Download, AlertCircle, FileText, ArrowDownWideNarrow, ArrowUpNarrowWide, Star, Sparkles } from 'lucide-react'

interface Props {
  papers: Paper[]
  total: number
  downloaded: number
  failed: number
}

type SortMode = 'relevance' | 'date_desc' | 'date_asc'

const sortConfig: Record<SortMode, { icon: typeof Star; label: string; next: SortMode }> = {
  relevance: { icon: Star, label: '相关度', next: 'date_desc' },
  date_desc: { icon: ArrowDownWideNarrow, label: '时间↓', next: 'date_asc' },
  date_asc: { icon: ArrowUpNarrowWide, label: '时间↑', next: 'relevance' },
}

const pickCorePapers = (papers: Paper[]) => {
  const ranked = [...papers].sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0))
  const strong = ranked.filter((p) => (p.relevance_score || 0) >= 6.5)
  return (strong.length > 0 ? strong : ranked.slice(0, 3)).slice(0, 6)
}

export default function PaperDrawer({ papers, total, downloaded, failed }: Props) {
  const [expanded, setExpanded] = useState(true)
  const [width, setWidth] = useState(380)
  const [isDragging, setIsDragging] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [sortMode, setSortMode] = useState<SortMode>('relevance')
  const startX = useRef(0)
  const startW = useRef(0)

  const filtered = searchQuery.trim()
    ? papers.filter((p) => p.title.toLowerCase().includes(searchQuery.toLowerCase()) || p.authors.some((a) => a.toLowerCase().includes(searchQuery.toLowerCase())))
    : papers

  const sorted = [...filtered].sort((a, b) => {
    if (sortMode === 'date_desc') return (b.published_date || '').localeCompare(a.published_date || '')
    if (sortMode === 'date_asc') return (a.published_date || '').localeCompare(b.published_date || '')
    return (b.relevance_score || 0) - (a.relevance_score || 0)
  })
  const corePapers = pickCorePapers(filtered)
  const coreIds = new Set(corePapers.map((p) => p.id))
  const regularPapers = sorted.filter((p) => !coreIds.has(p.id))

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsDragging(true)
    startX.current = e.clientX
    startW.current = width
  }, [width])

  useEffect(() => {
    if (!isDragging) return
    const move = (e: MouseEvent) => setWidth(Math.max(280, Math.min(600, startW.current - (e.clientX - startX.current))))
    const up = () => setIsDragging(false)
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', up)
    return () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up) }
  }, [isDragging])

  // 折叠状态：只显示一个窄条
  if (!expanded) {
    return (
      <div className="shrink-0 border-l border-gray-100 bg-white flex flex-col items-center py-4 w-12">
        <button onClick={() => setExpanded(true)} className="flex flex-col items-center gap-2 text-gray-400 hover:text-violet-500 transition-colors">
          <ChevronLeft size={14} />
          <FileText size={16} />
          <span className="text-[10px] font-semibold writing-mode-vertical" style={{ writingMode: 'vertical-rl' }}>{total}篇</span>
        </button>
        {downloaded > 0 && (
          <span className="mt-3 text-[10px] text-emerald-500 font-medium flex items-center gap-0.5" style={{ writingMode: 'vertical-rl' }}>
            <Download size={10} /> {downloaded}
          </span>
        )}
      </div>
    )
  }

  return (
    <div className="relative shrink-0 border-l border-gray-100 bg-white flex flex-col" style={{ width: `${width}px` }}>
      {/* 拖拽手柄 */}
      <div
        className="absolute top-0 bottom-0 -left-1 w-2 cursor-col-resize hover:bg-violet-200/50 transition-colors z-10"
        onMouseDown={onMouseDown}
      />

      {/* 标题栏 */}
      <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <FileText size={14} className="text-violet-400" />
          <span className="text-xs font-bold text-gray-700">论文列表</span>
          <span className="text-[10px] text-gray-400">{total}篇</span>
        </div>
        <div className="flex items-center gap-2">
          {downloaded > 0 && <span className="flex items-center gap-1 text-[10px] text-emerald-500 font-medium"><Download size={10} />{downloaded}</span>}
          {failed > 0 && <span className="flex items-center gap-1 text-[10px] text-red-400 font-medium"><AlertCircle size={10} />{failed}</span>}
          <button
            onClick={() => setSortMode(sortConfig[sortMode].next)}
            className="flex items-center gap-1 px-2 py-1 text-[10px] text-gray-400 hover:text-violet-500 hover:bg-violet-50 rounded-lg transition-colors"
            title={`当前: ${sortConfig[sortMode].label}`}
          >
            {(() => { const Icon = sortConfig[sortMode].icon; return <Icon size={12} />; })()}
            {sortConfig[sortMode].label}
          </button>
          <button onClick={() => setExpanded(false)} className="p-1 hover:bg-gray-100 rounded-lg transition-colors">
            <ChevronRight size={14} className="text-gray-300" />
          </button>
        </div>
      </div>

      {/* 搜索 */}
      <div className="px-3 py-2 border-b border-gray-50 shrink-0">
        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-300" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索论文..."
            className="w-full pl-8 pr-3 py-2 text-xs bg-gray-50 border-0 rounded-xl focus:outline-none focus:ring-2 focus:ring-violet-200 placeholder-gray-300"
          />
        </div>
      </div>

      {/* 论文列表 */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
        {corePapers.length > 0 && (
          <div className="rounded-2xl border border-amber-100 bg-amber-50/60 p-3">
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="flex items-center gap-1.5">
                <Sparkles size={13} className="text-amber-500" />
                <span className="text-xs font-bold text-amber-800">核心论文池</span>
              </div>
              <span className="text-[10px] text-amber-600">{corePapers.length} 篇优先看</span>
            </div>
            <div className="space-y-2">
              {corePapers.map((p) => <PaperCard key={p.id} paper={p} featured compact />)}
            </div>
          </div>
        )}
        {regularPapers.length > 0 ? regularPapers.map((p) => <PaperCard key={p.id} paper={p} />) : sorted.length === 0 ? (
          <div className="text-center text-gray-300 text-xs py-10">{searchQuery ? '没有找到~' : '暂无论文'}</div>
        ) : (
          <div className="text-center text-gray-300 text-xs py-6">其余论文暂无</div>
        )}
      </div>
    </div>
  )
}
