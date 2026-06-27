import { useState, useCallback, useEffect } from 'react'
import { usePaperStore, ChatMessage, Task } from '../stores/paperStore'

export function useChat(
  taskId: string | null,
  onTaskCreated?: (task: Task) => void,
  onTaskUpdated?: (task: Task) => void,
) {
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const addMessage = usePaperStore((s) => s.addMessage)
  const setMessages = usePaperStore((s) => s.setMessages)
  const messagesByTask = usePaperStore((s) => s.messagesByTask)
  const messages = taskId ? (messagesByTask[taskId] || []) : []

  // 从后端同步消息到本地（原子写入，避免竞态）
  const syncMessages = useCallback(async (tid: string) => {
    try {
      const resp = await fetch(`/api/messages/${tid}`)
      if (!resp.ok) return
      const msgs = await resp.json()
      const mapped: ChatMessage[] = msgs.map((m: any) => ({
        type: 'chat' as const,
        from: m.role === 'user' ? 'user' as const : 'agent' as const,
        content: m.content,
        timestamp: m.timestamp,
        suggestions: m.suggestions,
      }))
      // 保留本地用户消息（尚未持久化的）
      const existing = usePaperStore.getState().messagesByTask[tid] || []
      const localUserMsgs = existing.filter(
        (m) => m.from === 'user' && !mapped.some((n) => n.content === m.content)
      )
      usePaperStore.getState().setMessages(tid, [...mapped, ...localUserMsgs])
    } catch {}
  }, [])

  const refreshTask = useCallback(async (tid: string) => {
    try {
      const resp = await fetch(`/api/tasks/${tid}`)
      if (resp.ok) {
        const task: Task = await resp.json()
        onTaskUpdated?.(task)
      }
    } catch {}
  }, [onTaskUpdated])

  useEffect(() => {
    if (taskId) syncMessages(taskId)
  }, [taskId, syncMessages])

  // 核心发送逻辑
  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || !taskId) return

      // 先把用户消息加入 store（气泡立刻出现）
      addMessage(taskId, {
        type: 'chat',
        from: 'user',
        content: content.trim(),
        timestamp: new Date().toISOString(),
      })
      setIsLoading(true)

      try {
        await fetch(`/api/messages/${taskId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: content.trim() }),
        })

        const replyResp = await fetch(`/api/messages/${taskId}/reply`, { method: 'POST' })
        if (replyResp.ok) {
          const reply = await replyResp.json()
          addMessage(taskId, {
            type: 'chat',
            from: 'agent',
            content: reply.content,
            timestamp: reply.timestamp,
            suggestions: reply.suggestions,
          })
          await refreshTask(taskId)
        }
      } catch {} finally {
        setIsLoading(false)
      }
    },
    [taskId, addMessage, refreshTask]
  )

  // 无任务时创建任务并发送首条消息
  const createAndSend = useCallback(
    async (content: string) => {
      if (!content.trim()) return
      setIsLoading(true)
      try {
        const resp = await fetch('/api/tasks', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: content.trim() }),
        })
        if (resp.ok) {
          const task: Task = await resp.json()
          onTaskCreated?.(task)
          addMessage(task.id, {
            type: 'chat',
            from: 'user',
            content: content.trim(),
            timestamp: new Date().toISOString(),
          })
          await syncMessages(task.id)
        }
      } catch {} finally {
        setIsLoading(false)
      }
    },
    [addMessage, onTaskCreated, syncMessages]
  )

  const confirmSearch = useCallback(async () => {
    if (!taskId) return
    addMessage(taskId, {
      type: 'chat', from: 'user', content: '确认，开始搜索！', timestamp: new Date().toISOString(),
    })
    try {
      const resp = await fetch(`/api/tasks/${taskId}/confirm`, { method: 'POST' })
      if (resp.ok) await refreshTask(taskId)
    } catch {}
  }, [taskId, addMessage, refreshTask])

  const terminateTask = useCallback(async () => {
    if (!taskId) return
    addMessage(taskId, {
      type: 'chat', from: 'user', content: '终止当前任务', timestamp: new Date().toISOString(),
    })
    try {
      const resp = await fetch(`/api/tasks/${taskId}/terminate`, { method: 'POST' })
      if (resp.ok) { await refreshTask(taskId); await syncMessages(taskId) }
    } catch {}
  }, [taskId, addMessage, refreshTask, syncMessages])

  const resetTask = useCallback(async () => {
    if (!taskId) return
    addMessage(taskId, {
      type: 'chat', from: 'user', content: '重置任务', timestamp: new Date().toISOString(),
    })
    try {
      const resp = await fetch(`/api/tasks/${taskId}/reset`, { method: 'POST' })
      if (resp.ok) { await refreshTask(taskId); await syncMessages(taskId) }
    } catch {}
  }, [taskId, addMessage, refreshTask, syncMessages])

  const handleSuggestion = useCallback(
    (suggestion: string) => { sendMessage(suggestion) },
    [sendMessage]
  )

  const generatePlan = useCallback(async () => {
    if (!taskId) return
    setIsLoading(true)
    try {
      const resp = await fetch(`/api/tasks/${taskId}/generate-plan`, { method: 'POST' })
      if (resp.ok) {
        await refreshTask(taskId)
        await syncMessages(taskId)
      } else {
        const err = await resp.text()
        addMessage(taskId, {
          type: 'chat', from: 'agent',
          content: `生成方案失败：${err}`,
          timestamp: new Date().toISOString(),
        })
      }
    } catch (e) {
      addMessage(taskId, {
        type: 'chat', from: 'agent',
        content: `生成方案出错：${e instanceof Error ? e.message : '网络错误'}`,
        timestamp: new Date().toISOString(),
      })
    } finally {
      setIsLoading(false)
    }
  }, [taskId, refreshTask, syncMessages, addMessage])

  const resetPlan = useCallback(async () => {
    if (!taskId) return
    setIsLoading(true)
    try {
      const resp = await fetch(`/api/tasks/${taskId}/reset-plan`, { method: 'POST' })
      if (resp.ok) {
        await refreshTask(taskId)
        await syncMessages(taskId)
      }
    } catch {} finally {
      setIsLoading(false)
    }
  }, [taskId, refreshTask, syncMessages])

  return {
    messages, input, setInput, sendMessage, createAndSend, handleSuggestion,
    confirmSearch, terminateTask, resetTask, generatePlan, resetPlan,
    taskId, isLoading, addMessage,
  }
}
