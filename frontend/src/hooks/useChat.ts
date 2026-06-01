import { useState, useCallback, useEffect } from 'react'
import { usePaperStore, ChatMessage, Task } from '../stores/paperStore'
import { useWebSocket } from './useWebSocket'

export function useChat(
  taskId: string | null,
  onTaskCreated?: (task: Task) => void,
  onTaskUpdated?: (task: Task) => void,
) {
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(taskId)
  const addMessage = usePaperStore((s) => s.addMessage)
  const messagesByTask = usePaperStore((s) => s.messagesByTask)
  const activeTaskId = currentTaskId || taskId
  const messages = activeTaskId ? (messagesByTask[activeTaskId] || []) : []
  const { sendMessage: wsSend } = useWebSocket(activeTaskId)

  // 刷新后端消息到本地
  const syncMessages = useCallback(async (tid: string) => {
    try {
      const resp = await fetch(`/api/messages/${tid}`)
      if (resp.ok) {
        const msgs = await resp.json()
        usePaperStore.getState().clearMessages(tid)
        for (const m of msgs) {
          addMessage(tid, {
            type: 'chat',
            from: m.role === 'user' ? 'user' : 'agent',
            content: m.content,
            timestamp: m.timestamp,
            suggestions: m.suggestions,
          })
        }
      }
    } catch {}
  }, [addMessage])

  // 刷新任务状态
  const refreshTask = useCallback(async (tid: string) => {
    try {
      const resp = await fetch(`/api/tasks/${tid}`)
      if (resp.ok) {
        const task: Task = await resp.json()
        onTaskUpdated?.(task)
      }
    } catch {}
  }, [onTaskUpdated])

  // 当 taskId 变化时同步消息
  useEffect(() => {
    if (taskId && taskId !== currentTaskId) {
      setCurrentTaskId(taskId)
      syncMessages(taskId)
    }
  }, [taskId, currentTaskId, syncMessages])

  // 发送消息
  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim()) return

      let tid = currentTaskId || taskId

      // 没有任务时，先创建任务（不自动执行）
      if (!tid) {
        setIsLoading(true)
        try {
          const resp = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: content.trim() }),
          })
          if (resp.ok) {
            const task: Task = await resp.json()
            tid = task.id
            setCurrentTaskId(task.id)
            onTaskCreated?.(task)
            await syncMessages(task.id)
          }
        } catch {} finally {
          setIsLoading(false)
        }
        setInput('')
        return
      }

      // 有任务时正常发送
      addMessage(tid, {
        type: 'chat',
        from: 'user',
        content: content.trim(),
        timestamp: new Date().toISOString(),
      })
      setInput('')
      setIsLoading(true)

      try {
        await fetch(`/api/messages/${tid}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: content.trim() }),
        })

        const replyResp = await fetch(`/api/messages/${tid}/reply`, { method: 'POST' })
        if (replyResp.ok) {
          const reply = await replyResp.json()
          addMessage(tid, {
            type: 'chat',
            from: 'agent',
            content: reply.content,
            timestamp: reply.timestamp,
            suggestions: reply.suggestions,
          })
        }
      } catch {} finally {
        setIsLoading(false)
      }
    },
    [currentTaskId, taskId, addMessage, wsSend, onTaskCreated, syncMessages]
  )

  // 确认开始搜索
  const confirmSearch = useCallback(async () => {
    const tid = currentTaskId || taskId
    if (!tid) return

    addMessage(tid, {
      type: 'chat',
      from: 'user',
      content: '确认，开始搜索！',
      timestamp: new Date().toISOString(),
    })

    try {
      const resp = await fetch(`/api/tasks/${tid}/confirm`, { method: 'POST' })
      if (resp.ok) {
        await refreshTask(tid)
      }
    } catch {}
  }, [currentTaskId, taskId, addMessage, refreshTask])

  // 终止任务
  const terminateTask = useCallback(async () => {
    const tid = currentTaskId || taskId
    if (!tid) return

    addMessage(tid, {
      type: 'chat',
      from: 'user',
      content: '终止当前任务',
      timestamp: new Date().toISOString(),
    })

    try {
      const resp = await fetch(`/api/tasks/${tid}/terminate`, { method: 'POST' })
      if (resp.ok) {
        await refreshTask(tid)
        await syncMessages(tid)
      }
    } catch {}
  }, [currentTaskId, taskId, addMessage, refreshTask, syncMessages])

  // 重置任务
  const resetTask = useCallback(async () => {
    const tid = currentTaskId || taskId
    if (!tid) return

    addMessage(tid, {
      type: 'chat',
      from: 'user',
      content: '重置任务',
      timestamp: new Date().toISOString(),
    })

    try {
      const resp = await fetch(`/api/tasks/${tid}/reset`, { method: 'POST' })
      if (resp.ok) {
        await refreshTask(tid)
        await syncMessages(tid)
      }
    } catch {}
  }, [currentTaskId, taskId, addMessage, refreshTask, syncMessages])

  const handleSuggestion = useCallback(
    (suggestion: string) => {
      sendMessage(suggestion)
    },
    [sendMessage]
  )

  return {
    messages,
    input,
    setInput,
    sendMessage,
    handleSuggestion,
    confirmSearch,
    terminateTask,
    resetTask,
    taskId: activeTaskId,
    isLoading,
  }
}
