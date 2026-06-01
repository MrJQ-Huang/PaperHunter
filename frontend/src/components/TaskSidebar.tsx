import { useState, useRef, useEffect, useMemo } from 'react'
import { Task } from '../stores/paperStore'
import { Search, Plus, ChevronDown, ChevronRight, Clock, CheckCircle2, AlertCircle, Pause, Pencil, Copy, Trash2, Loader2 } from 'lucide-react'

interface Props {
  tasks: Task[]
  currentTaskId: string | null
  onSelectTask: (task: Task) => void
  onNewTask: () => void
  onDeleteTask: (taskId: string) => void
}

function timeAgo(dateStr: string): string {
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  return `${Math.floor(diff / 86400)}天前`
}

const statusInfo: Record<string, { icon: typeof Clock; color: string; label: string }> = {
  running: { icon: Loader2, color: 'text-blue-500', label: '运行中' },
  pending: { icon: Clock, color: 'text-amber-500', label: '待确认' },
  paused: { icon: Pause, color: 'text-gray-400', label: '暂停' },
  completed: { icon: CheckCircle2, color: 'text-emerald-500', label: '完成' },
  failed: { icon: AlertCircle, color: 'text-red-400', label: '失败' },
  cancelled: { icon: AlertCircle, color: 'text-gray-400', label: '取消' },
}

export default function TaskSidebar({ tasks, currentTaskId, onSelectTask, onNewTask, onDeleteTask }: Props) {
  const [search, setSearch] = useState('')
  const [showCompleted, setShowCompleted] = useState(false)
  const [ctx, setCtx] = useState<{ id: string; x: number; y: number } | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setCtx(null)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const filtered = useMemo(() => {
    if (!search.trim()) return tasks
    const q = search.toLowerCase()
    return tasks.filter((t) => t.query.toLowerCase().includes(q))
  }, [tasks, search])

  const active = filtered.filter((t) => ['running', 'pending', 'paused'].includes(t.status))
  const done = filtered.filter((t) => ['completed', 'failed', 'cancelled'].includes(t.status))

  return (
    <div className="w-64 bg-white border-r border-gray-100 flex flex-col shrink-0">
      {/* 标题 */}
      <div className="px-4 pt-4 pb-2">
        <h2 className="text-xs font-bold text-gray-400 tracking-wider uppercase">任务列表</h2>
      </div>

      {/* 搜索 */}
      <div className="px-3 mb-2">
        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-300" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索..."
            className="w-full pl-8 pr-3 py-2 text-xs bg-gray-50 text-gray-700 rounded-xl border-0 focus:outline-none focus:ring-2 focus:ring-violet-200 placeholder-gray-300"
          />
        </div>
      </div>

      {/* 新任务按钮 */}
      <div className="px-3 mb-2">
        <button
          onClick={onNewTask}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-2.5 bg-gradient-to-r from-violet-500 to-purple-500 text-white text-xs font-medium rounded-xl hover:from-violet-600 hover:to-purple-600 transition-all shadow-sm shadow-violet-200 active:scale-[0.98]"
        >
          <Plus size={14} />
          新任务
        </button>
      </div>

      {/* 任务列表 */}
      <div className="flex-1 overflow-y-auto px-2 space-y-0.5">
        {active.length > 0 && active.map((task) => (
          <TaskItem
            key={task.id}
            task={task}
            isActive={currentTaskId === task.id}
            onSelect={onSelectTask}
            onContextMenu={(e, id) => { e.preventDefault(); setCtx({ id, x: e.clientX, y: e.clientY }) }}
          />
        ))}

        {done.length > 0 && (
          <div className="mt-2">
            <button
              onClick={() => setShowCompleted(!showCompleted)}
              className="flex items-center gap-1 px-2 py-1.5 text-[11px] text-gray-400 hover:text-gray-500 w-full transition-colors"
            >
              {showCompleted ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              已完成 ({done.length})
            </button>
            {showCompleted && done.map((task) => (
              <TaskItem
                key={task.id}
                task={task}
                isActive={currentTaskId === task.id}
                onSelect={onSelectTask}
                onContextMenu={(e, id) => { e.preventDefault(); setCtx({ id, x: e.clientX, y: e.clientY }) }}
                dimmed
              />
            ))}
          </div>
        )}

        {filtered.length === 0 && (
          <div className="text-center text-gray-300 text-xs py-10">
            {search ? '没有找到~' : '还没有任务哦'}
          </div>
        )}
      </div>

      {/* 右键菜单 */}
      {ctx && (
        <div ref={menuRef} className="ctx-menu fixed bg-white rounded-xl shadow-lg shadow-gray-200/50 border border-gray-100 py-1.5 z-50 min-w-[130px]" style={{ left: ctx.x, top: ctx.y }}>
          <button onClick={() => { navigator.clipboard.writeText(tasks.find(t => t.id === ctx.id)?.query || ''); setCtx(null) }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition-colors">
            <Copy size={12} /> 复制主题
          </button>
          <div className="border-t border-gray-100 my-1" />
          <button onClick={() => { onDeleteTask(ctx.id); setCtx(null) }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-red-400 hover:bg-red-50 transition-colors">
            <Trash2 size={12} /> 删除
          </button>
        </div>
      )}
    </div>
  )
}

function TaskItem({ task, isActive, onSelect, onContextMenu, dimmed }: {
  task: Task; isActive: boolean; onSelect: (t: Task) => void
  onContextMenu: (e: React.MouseEvent, id: string) => void; dimmed?: boolean
}) {
  const info = statusInfo[task.status] || statusInfo.pending
  const Icon = info.icon
  const isRunning = task.status === 'running'

  return (
    <div
      className={`group rounded-xl px-3 py-2.5 cursor-pointer transition-all duration-150 ${
        isActive
          ? 'bg-violet-50 border border-violet-200/60 shadow-sm shadow-violet-100/50'
          : 'hover:bg-gray-50 border border-transparent'
      } ${dimmed ? 'opacity-50 hover:opacity-80' : ''}`}
      onClick={() => onSelect(task)}
      onContextMenu={(e) => onContextMenu(e, task.id)}
    >
      <div className="text-xs font-medium text-gray-700 truncate leading-tight mb-1">
        {task.query}
      </div>
      <div className="flex items-center gap-1.5">
        <Icon size={10} className={`${info.color} ${isRunning ? 'animate-spin' : ''}`} />
        <span className={`text-[10px] ${info.color}`}>{info.label}</span>
        {task.total_papers_found > 0 && (
          <span className="text-[10px] text-gray-300">·{task.total_papers_found}篇</span>
        )}
        <span className="text-[10px] text-gray-300 ml-auto">{timeAgo(task.updated_at)}</span>
      </div>
    </div>
  )
}
