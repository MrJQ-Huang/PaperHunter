import { useState, useEffect, useCallback, useRef } from 'react'
import { useAgentStore } from '../stores/agentStore'
import { usePaperStore, Task } from '../stores/paperStore'
import AgentStatusCard from '../components/AgentStatus'
import TaskProgress from '../components/TaskProgress'
import ChatWindow from '../components/ChatWindow'
import PaperCard from '../components/PaperCard'
import { Search, Plus, RefreshCw, Trash2, ChevronDown, ChevronRight, Clock, CheckCircle2 } from 'lucide-react'

export default function Dashboard() {
  const [query, setQuery] = useState('')
  const [sources, setSources] = useState(['arxiv', 'semantic_scholar', 'openalex', 'crossref'])
  const [isCreating, setIsCreating] = useState(false)
  const [showCompleted, setShowCompleted] = useState(false)
  const pollingTasks = useRef(new Set<string>())
  const agents = useAgentStore((s) => s.agents)
  const updateAgent = useAgentStore((s) => s.updateAgent)
  const currentTask = usePaperStore((s) => s.currentTask)
  const setCurrentTask = usePaperStore((s) => s.setCurrentTask)
  const papers = usePaperStore((s) => s.papers)
  const setPapers = usePaperStore((s) => s.setPapers)
  const tasks = usePaperStore((s) => s.tasks)
  const setTasks = usePaperStore((s) => s.setTasks)

  const fetchTasks = useCallback(async () => {
    try {
      const resp = await fetch('/api/tasks')
      if (resp.ok) {
        const data = await resp.json()
        setTasks(data)
        if (data.length > 0 && !currentTask) {
          selectTask(data[0])
        }
      }
    } catch {}
  }, [setTasks, currentTask])

  const fetchPapers = useCallback(async (tid?: string) => {
    try {
      const taskParam = tid ? `&task_id=${tid}` : ''
      const resp = await fetch(`/api/papers?per_page=20&sort=relevance${taskParam}`)
      if (resp.ok) {
        const data = await resp.json()
        setPapers(data.papers, data.total)
      }
    } catch {}
  }, [setPapers])

  useEffect(() => {
    fetchTasks()
    fetchPapers(currentTask?.id)
  }, [fetchTasks, fetchPapers, currentTask?.id])

  const createTask = async () => {
    if (!query.trim()) return
    setIsCreating(true)
    try {
      const resp = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim(), sources }),
      })
      if (resp.ok) {
        const task = await resp.json()
        setCurrentTask(task)
        setQuery('')
        startPolling(task.id)
      }
    } catch {} finally {
      setIsCreating(false)
    }
  }

  // 从任务响应中恢复 Agent 状态
  const applyAgentStatuses = (data: any) => {
    if (data.agent_statuses) {
      for (const [agent, info] of Object.entries(data.agent_statuses) as [string, any][]) {
        updateAgent({
          agent,
          status: info.status,
          message: info.message,
          progress: info.progress,
        })
      }
    }
  }

  const startPolling = (taskId: string) => {
    if (pollingTasks.current.has(taskId)) return
    pollingTasks.current.add(taskId)

    const interval = setInterval(async () => {
      try {
        const resp = await fetch(`/api/tasks/${taskId}`)
        if (resp.ok) {
          const data = await resp.json()
          setCurrentTask(data)
          applyAgentStatuses(data)
          fetchPapers(taskId)
          if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
            clearInterval(interval)
            pollingTasks.current.delete(taskId)
          }
        }
      } catch {
        clearInterval(interval)
        pollingTasks.current.delete(taskId)
      }
    }, 3000)
  }

  // 选择任务时获取完整详情（含 Agent 状态）
  const selectTask = async (task: Task) => {
    setCurrentTask(task)
    fetchPapers(task.id)
    try {
      const resp = await fetch(`/api/tasks/${task.id}`)
      if (resp.ok) {
        const data = await resp.json()
        setCurrentTask(data)
        applyAgentStatuses(data)
      }
    } catch {}
  }

  const deleteTask = async (taskId: string) => {
    try {
      const resp = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' })
      if (resp.ok) {
        const remaining = tasks.filter((t) => t.id !== taskId)
        setTasks(remaining)
        if (currentTask?.id === taskId) {
          setCurrentTask(remaining[0] || null)
        }
      }
    } catch {}
  }

  const agentList = Object.values(agents)
  const hasActiveTask = currentTask && ['running', 'pending'].includes(currentTask.status)

  // 分组：活跃任务 vs 已完成任务
  const activeTasks = tasks.filter((t) => ['running', 'pending', 'paused'].includes(t.status))
  const completedTasks = tasks.filter((t) => ['completed', 'failed', 'cancelled'].includes(t.status))

  const statusIcon = (status: string) => {
    switch (status) {
      case 'running': return <Clock size={12} className="text-blue-500 animate-pulse" />
      case 'completed': return <CheckCircle2 size={12} className="text-green-500" />
      case 'failed': return <Clock size={12} className="text-red-500" />
      default: return <Clock size={12} className="text-gray-400" />
    }
  }

  return (
    <div className="grid grid-cols-12 gap-6 h-[calc(100vh-8rem)]">
      {/* 左侧面板 */}
      <div className="col-span-5 flex flex-col gap-4 overflow-hidden">
        {/* 搜索栏 */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-3">
            <Search size={18} className="text-primary-500" />
            <span className="font-semibold text-gray-800">论文搜索</span>
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && createTask()}
              placeholder="输入搜索主题..."
              className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            <button
              onClick={createTask}
              disabled={isCreating || !query.trim()}
              className="px-4 py-2 bg-primary-500 text-white text-sm rounded-lg hover:bg-primary-600 disabled:opacity-50 transition-colors flex items-center gap-1"
            >
              <Plus size={14} />
              搜索
            </button>
          </div>
          <div className="mt-2 flex flex-wrap gap-1">
            {['arxiv', 'semantic_scholar', 'openalex', 'crossref', 'google_scholar'].map((src) => (
              <button
                key={src}
                onClick={() =>
                  setSources((prev) =>
                    prev.includes(src) ? prev.filter((s) => s !== src) : [...prev, src]
                  )
                }
                className={`px-2 py-0.5 text-xs rounded-full transition-colors ${
                  sources.includes(src)
                    ? 'bg-primary-100 text-primary-700'
                    : 'bg-gray-100 text-gray-400'
                }`}
              >
                {src}
              </button>
            ))}
          </div>
        </div>

        {/* Agent 状态卡片 — 始终显示 */}
        <div className="grid grid-cols-2 gap-3">
          {agentList.map((agent) => (
            <AgentStatusCard key={agent.agent} agent={agent} />
          ))}
        </div>

        {/* 任务进度 — 仅在任务进行中显示，完成后隐藏 */}
        {currentTask && hasActiveTask && <TaskProgress task={currentTask} />}

        {/* 任务列表 */}
        {tasks.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-4 overflow-y-auto flex-1 min-h-0">
            <div className="flex items-center justify-between mb-3">
              <span className="font-medium text-sm text-gray-800">任务列表</span>
              <button onClick={fetchTasks} className="text-gray-400 hover:text-gray-600">
                <RefreshCw size={14} />
              </button>
            </div>

            {/* 活跃任务 */}
            {activeTasks.length > 0 && (
              <div className="space-y-2 mb-3">
                {activeTasks.map((task) => (
                  <div
                    key={task.id}
                    className={`flex items-center justify-between p-2.5 rounded-lg text-xs transition-colors ${
                      currentTask?.id === task.id
                        ? 'bg-primary-50 text-primary-700 border border-primary-200'
                        : 'hover:bg-gray-50 text-gray-600 border border-transparent'
                    }`}
                  >
                    <button
                      onClick={() => selectTask(task)}
                      className="flex-1 text-left truncate flex items-center gap-2"
                    >
                      {statusIcon(task.status)}
                      <span className="font-medium">{task.query}</span>
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteTask(task.id) }}
                      className="ml-2 p-1 text-gray-300 hover:text-red-500 transition-colors"
                      title="删除任务"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* 已完成任务 — 折叠 */}
            {completedTasks.length > 0 && (
              <div>
                <button
                  onClick={() => setShowCompleted(!showCompleted)}
                  className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 w-full py-1.5 transition-colors"
                >
                  {showCompleted ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <span>已完成 ({completedTasks.length})</span>
                </button>

                {showCompleted && (
                  <div className="space-y-1.5 mt-1">
                    {completedTasks.map((task) => (
                      <div
                        key={task.id}
                        className="flex items-center justify-between p-2 rounded-lg text-xs opacity-50 hover:opacity-80 transition-opacity"
                      >
                        <button
                          onClick={() => selectTask(task)}
                          className="flex-1 text-left truncate flex items-center gap-2"
                        >
                          {statusIcon(task.status)}
                          <span className="text-gray-500 line-clamp-1">{task.query}</span>
                          <span className="ml-auto text-gray-300 shrink-0">
                            {task.total_papers_found}篇
                          </span>
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); deleteTask(task.id) }}
                          className="ml-2 p-1 text-gray-200 hover:text-red-500 transition-colors"
                          title="删除任务"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 右侧：聊天 + 搜索结果 */}
      <div className="col-span-7 flex flex-col gap-4 overflow-hidden">
        <div className="flex-1 min-h-0">
          <ChatWindow
            taskId={currentTask?.id || null}
            taskStatus={currentTask?.status}
            onTaskCreated={(task) => {
              setCurrentTask(task)
              startPolling(task.id)
            }}
            onTaskUpdated={(task) => {
              setCurrentTask(task)
              fetchPapers(task.id)
              if (task.status === 'running') {
                startPolling(task.id)
              }
            }}
          />
        </div>

        {papers.length > 0 && (
          <div className="h-64 overflow-y-auto space-y-2">
            <h3 className="font-medium text-sm text-gray-800 sticky top-0 bg-gray-50 py-1">
              搜索结果 ({papers.length} 篇)
            </h3>
            {papers.slice(0, 5).map((paper) => (
              <PaperCard key={paper.id} paper={paper} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
