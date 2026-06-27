import { useState, useEffect, useCallback, useRef } from 'react'
import { useAgentStore } from '../stores/agentStore'
import { usePaperStore, Task } from '../stores/paperStore'
import { useWebSocket } from '../hooks/useWebSocket'
import TaskSidebar from '../components/TaskSidebar'
import ChatWindow from '../components/ChatWindow'
import PaperDrawer from '../components/PaperDrawer'
import EmptyState from '../components/EmptyState'
import { Sparkles } from 'lucide-react'

export default function Dashboard() {
  const pollingTasks = useRef(new Set<string>())
  const currentTaskRef = useRef<Task | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const resetAgents = useAgentStore((s) => s.resetAgents)
  const currentTask = usePaperStore((s) => s.currentTask)

  // WebSocket 连接：实时接收 Agent 状态和日志
  useWebSocket(currentTask?.id || null)
  const setCurrentTask = usePaperStore((s) => s.setCurrentTask)
  const papers = usePaperStore((s) => s.papers)
  const setPapers = usePaperStore((s) => s.setPapers)
  const tasks = usePaperStore((s) => s.tasks)
  const setTasks = usePaperStore((s) => s.setTasks)

  useEffect(() => {
    currentTaskRef.current = currentTask
  }, [currentTask])

  const fetchTasks = useCallback(async () => {
    try {
      const resp = await fetch('/api/tasks')
      if (resp.ok) setTasks(await resp.json())
    } catch {}
  }, [setTasks])

  const fetchPapers = useCallback(async (tid?: string) => {
    try {
      const resp = await fetch(`/api/papers?per_page=50&sort=relevance${tid ? `&task_id=${tid}` : ''}`)
      if (resp.ok) { const d = await resp.json(); setPapers(d.papers, d.total) }
    } catch {}
  }, [setPapers])

  // 挂载时等待后端就绪，加载任务列表 + 自动选中最近任务
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      // 轮询等待后端就绪（最多等 30 秒）
      for (let i = 0; i < 60; i++) {
        if (cancelled) return
        try {
          const resp = await fetch('/api/health')
          if (resp.ok) break
        } catch {}
        await new Promise((r) => setTimeout(r, 500))
      }
      if (cancelled) return
      // 后端就绪，加载任务
      try {
        const resp = await fetch('/api/tasks')
        if (!resp.ok) return
        const list: Task[] = await resp.json()
        setTasks(list)
        if (list.length > 0) {
          const task = list[0]
          setCurrentTask(task)
          resetAgents()
          fetch(`/api/papers?per_page=50&sort=relevance&task_id=${task.id}`)
            .then((r) => r.ok ? r.json() : null)
            .then((d) => { if (d) setPapers(d.papers, d.total) })
            .catch(() => {})
          fetch(`/api/tasks/${task.id}`)
            .then((r) => r.ok ? r.json() : null)
            .then((d) => {
              if (d) {
                setCurrentTask(d)
                if (d.agent_statuses) {
                  for (const [k, v] of Object.entries(d.agent_statuses) as [string, any][]) {
                    useAgentStore.getState().updateAgent({ agent: k, status: v.status, message: v.message, progress: v.progress })
                  }
                }
              }
            })
            .catch(() => {})
        }
      } catch {}
    }
    load()
    return () => { cancelled = true }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { fetchPapers(currentTask?.id) }, [currentTask?.id, fetchPapers])

  const applyAgentStatuses = (data: any) => {
    if (!data.agent_statuses) return
    for (const [k, v] of Object.entries(data.agent_statuses) as [string, any][]) {
      useAgentStore.getState().updateAgent({ agent: k, status: v.status, message: v.message, progress: v.progress })
    }
  }

  const startPolling = (taskId: string) => {
    if (pollingTasks.current.has(taskId)) return
    pollingTasks.current.add(taskId)
    const iv = setInterval(async () => {
      try {
        const resp = await fetch(`/api/tasks/${taskId}`)
        if (resp.ok) {
          const d = await resp.json()
          usePaperStore.getState().updateTask(d)
          if (currentTaskRef.current?.id === taskId) {
            setCurrentTask(d)
            applyAgentStatuses(d)
            fetchPapers(taskId)
          }
          if (['completed', 'failed', 'cancelled'].includes(d.status)) { clearInterval(iv); pollingTasks.current.delete(taskId) }
        }
      } catch { clearInterval(iv); pollingTasks.current.delete(taskId) }
    }, 3000)
  }

  const selectTask = async (task: Task) => {
    setCurrentTask(task)
    resetAgents()
    fetchPapers(task.id)
    try {
      const resp = await fetch(`/api/tasks/${task.id}`)
      if (resp.ok) {
        const d = await resp.json()
        setCurrentTask(d)
        applyAgentStatuses(d)
        if (d.status === 'running') startPolling(task.id)
      }
    } catch {}
  }

  const deleteTask = async (taskId: string) => {
    try {
      const resp = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' })
      if (resp.ok) {
        const remaining = tasks.filter((t) => t.id !== taskId)
        setTasks(remaining)
        if (currentTask?.id === taskId) setCurrentTask(remaining[0] || null)
      }
    } catch {}
  }

  const renameTask = async (taskId: string, newQuery: string) => {
    try {
      const resp = await fetch(`/api/tasks/${taskId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: newQuery }),
      })
      if (resp.ok) {
        const updated: Task = await resp.json()
        setTasks(tasks.map((t) => t.id === taskId ? updated : t))
        if (currentTask?.id === taskId) setCurrentTask(updated)
      }
    } catch {}
  }

  const handleNewTask = () => {
    setCurrentTask(null)
    currentTaskRef.current = null
    resetAgents()
    setPapers([], 0)
    setTimeout(() => inputRef.current?.focus(), 100)
  }

  const handleTaskCreated = (task: Task) => {
    setCurrentTask(task)
    currentTaskRef.current = task
    const latestTasks = usePaperStore.getState().tasks
    setTasks([task, ...latestTasks.filter((t) => t.id !== task.id)])
    fetchTasks()
    startPolling(task.id)
  }

  const handleTaskUpdated = (task: Task) => {
    setCurrentTask(task)
    currentTaskRef.current = task
    const latestTasks = usePaperStore.getState().tasks
    const hasTask = latestTasks.some((t) => t.id === task.id)
    setTasks(hasTask ? latestTasks.map((t) => t.id === task.id ? task : t) : [task, ...latestTasks])
    fetchPapers(task.id)
    if (task.status === 'running') startPolling(task.id)
  }

  const handleSelectTopic = (topic: string) => {
    const ev = new CustomEvent('chat-send', { detail: topic })
    window.dispatchEvent(ev)
  }

  const downloaded = papers.filter((p) => p.download_status === 'done').length
  const failed = papers.filter((p) => p.download_status === 'failed').length

  // 快捷键
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 'n') { e.preventDefault(); handleNewTask() }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [tasks, currentTask])

  return (
    <div className="flex h-[calc(100vh-3.5rem)] -mx-4 -my-6 overflow-hidden bg-[#fafafa]">
      {/* 左侧任务栏 */}
      <TaskSidebar
        tasks={tasks}
        currentTaskId={currentTask?.id || null}
        onSelectTask={selectTask}
        onNewTask={handleNewTask}
        onDeleteTask={deleteTask}
        onRenameTask={renameTask}
      />

      {/* 右侧主区域 */}
      <div className="flex-1 flex min-w-0">
        {/* 聊天区域 */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* 顶部栏 */}
          <div className="h-14 px-5 flex items-center justify-between bg-white/80 backdrop-blur border-b border-gray-100 shrink-0">
            <div className="flex items-center gap-2.5 min-w-0">
              {currentTask ? (
                <>
                  <h1 className="text-sm font-bold text-gray-800 truncate">{currentTask.query}</h1>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                    currentTask.status === 'running' ? 'bg-blue-50 text-blue-500' :
                    currentTask.status === 'pending' ? 'bg-amber-50 text-amber-500' :
                    currentTask.status === 'reviewing' ? 'bg-violet-50 text-violet-500' :
                    currentTask.status === 'completed' ? 'bg-emerald-50 text-emerald-500' :
                    currentTask.status === 'failed' ? 'bg-red-50 text-red-400' :
                    'bg-gray-100 text-gray-400'
                  }`}>
                    {currentTask.status === 'pending' ? '待确认' : currentTask.status === 'running' ? '执行中' : currentTask.status === 'reviewing' ? '待筛选' : currentTask.status === 'completed' ? '已完成' : currentTask.status === 'failed' ? '失败' : currentTask.status}
                  </span>
                </>
              ) : (
                <div className="flex items-center gap-2">
                  <Sparkles size={16} className="text-violet-400" />
                  <span className="text-sm font-bold text-gray-700">PaperHunter</span>
                </div>
              )}
            </div>
            {currentTask && currentTask.total_papers_found > 0 && (
              <span className="text-xs text-gray-400">{currentTask.total_papers_found} 篇</span>
            )}
          </div>

          {/* 内容区 */}
          <div className="flex-1 flex flex-col min-h-0">
            {!currentTask ? (
              <>
                <EmptyState onSelectTopic={handleSelectTopic} />
                <ChatWindow taskId={null} taskStatus={undefined} onTaskCreated={handleTaskCreated} onTaskUpdated={handleTaskUpdated} inputRef={inputRef} />
              </>
            ) : (
              <ChatWindow
                taskId={currentTask.id}
                taskStatus={currentTask.status}
                searchPlan={currentTask.search_plan}
                onTaskCreated={handleTaskCreated}
                onTaskUpdated={handleTaskUpdated}
                inputRef={inputRef}
              />
            )}
          </div>
        </div>

        {/* 右侧论文面板 */}
        {currentTask && papers.length > 0 && (
          <PaperDrawer papers={papers} total={papers.length} downloaded={downloaded} failed={failed} />
        )}
      </div>
    </div>
  )
}
