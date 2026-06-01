import { useState, useRef, useCallback, useEffect } from 'react'
import { Paper } from '../stores/paperStore'
import PaperCard from './PaperCard'
import { ChevronUp, ChevronDown, Search, Download, AlertCircle, FileText } from 'lucide-react'

interface Props {
  papers: Paper[]
  total: number
  downloaded: number
  failed: number
}

export default function PaperDrawer({ papers, total, downloaded, failed }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [height, setHeight] = useState(300)
  const [isDragging, setIsDragging] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const startY = useRef(0)
  const startH = useRef(0)

  const filtered = searchQuery.trim()
    ? papers.filter((p) => p.title.toLowerCase().includes(searchQuery.toLowerCase()) || p.authors.some((a) => a.toLowerCase().includes(searchQuery.toLowerCase())))
    : papers

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsDragging(true)
    startY.current = e.clientY
    startH.current = height
  }, [height])

  useEffect(() => {
    if (!isDragging) return
    const move = (e: MouseEvent) => setHeight(Math.max(150, Math.min(window.innerHeight * 0.7, startH.current + (startY.current - e.clientY))))
    const up = () => setIsDragging(false)
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', up)
    return () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up) }
  }, [isDragging])

  return (
    <div className="bg-white border-t border-gray-100 shrink-0 rounded-t-2xl">
      {/* 统计栏 */}
      <button onClick={() => setExpanded(!expanded)} className="w-full flex items-center justify-between px-5 py-3 hover:bg-gray-50/80 transition-colors rounded-t-2xl">
        <div className="flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1.5 text-gray-600 font-semibold">
            <FileText size={14} className="text-violet-400" />
            {total} 篇论文
          </span>
          {downloaded > 0 && <span className="flex items-center gap-1 text-emerald-500 font-medium"><Download size={12} />{downloaded}</span>}
          {failed > 0 && <span className="flex items-center gap-1 text-red-400 font-medium"><AlertCircle size={12} />{failed}</span>}
        </div>
        {expanded ? <ChevronDown size={14} className="text-gray-300" /> : <ChevronUp size={14} className="text-gray-300" />}
      </button>

      {/* 展开区域 */}
      {expanded && (
        <div style={{ height: `${height}px` }} className="flex flex-col overflow-hidden">
          <div className="drawer-handle flex justify-center py-1.5" onMouseDown={onMouseDown}>
            <div className="w-10 h-1 bg-gray-200 rounded-full" />
          </div>
          <div className="px-5 pb-2">
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
          <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
            {filtered.length > 0 ? filtered.map((p) => <PaperCard key={p.id} paper={p} />) : (
              <div className="text-center text-gray-300 text-xs py-10">{searchQuery ? '没有找到~' : '暂无论文'}</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
