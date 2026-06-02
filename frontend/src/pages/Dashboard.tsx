import { useState, useEffect, useCallback, useRef } from 'react'
import { useAgentStore } from '../stores/agentStore'
import { usePaperStore, Task } from '../stores/paperStore'
import TaskSidebar from '../components/TaskSidebar'
import ChatWindow from '../components/ChatWindow'
import PaperDrawer from '../components/PaperDrawer'
import EmptyState from '../components/EmptyState'
import { Sparkles } from 'lucide-react'

export default function Dashboard() {
  const pollingTasks = useRef(new Set<string>())
  const inputRef = useRef<HTMLInputElement>(null)

  const resetAgents = useAgentStore((s) => s.resetAgents)
  const currentTask = usePaperStore((s) => s.currentTask)
  const setCurrentTask = usePaperStore((s) => s.setCurrentTask)
  const papers = usePaperStore((s) => s.papers)
  const setPapers = usePaperStore((s) => s.setPapers)
  const tasks = usePaperStore((s) => s.tasks)
  const setTasks = usePaperStore((s) => s.setTasks)

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

  useEffect(() => { fetchTasks() }, [fetchTasks])
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
          setCurrentTask(d)
          applyAgentStatuses(d)
          fetchPapers(taskId)
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

  const handleNewTask = () => {
    setCurrentTask(null)
    resetAgents()
    setPapers([], 0)
    setTimeout(() => inputRef.current?.focus(), 100)
  }

  const handleTaskCreated = (task: Task) => {
    setCurrentTask(task)
    fetchTasks()
    startPolling(task.id)
  }

  const handleTaskUpdated = (task: Task) => {
    setCurrentTask(task)
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
      />

      {/* 右侧主区域 */}
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
                  currentTask.status === 'completed' ? 'bg-emerald-50 text-emerald-500' :
                  currentTask.status === 'failed' ? 'bg-red-50 text-red-400' :
                  'bg-gray-100 text-gray-400'
                }`}>
                  {currentTask.status === 'pending' ? '待确认' : currentTask.status === 'running' ? '执行中' : currentTask.status === 'completed' ? '已完成' : currentTask.status === 'failed' ? '失败' : currentTask.status}
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

        {/* 论文抽屉 */}
        {currentTask && papers.length > 0 && (
          <PaperDrawer papers={papers} total={papers.length} downloaded={downloaded} failed={failed} />
        )}
      </div>
    </div>
  )
}
