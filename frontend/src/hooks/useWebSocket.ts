import { useEffect, useRef, useCallback } from 'react'
import { useAgentStore } from '../stores/agentStore'
import { usePaperStore, ChatMessage } from '../stores/paperStore'

export function useWebSocket(taskId: string | null) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<number | null>(null)
  const reconnectAttempts = useRef(0)
  const maxReconnectAttempts = 10
  const updateAgent = useAgentStore((s) => s.updateAgent)
  const addMessage = usePaperStore((s) => s.addMessage)

  const connect = useCallback(() => {
    if (!taskId) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/chat/${taskId}`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      reconnectAttempts.current = 0
      // 启动心跳
      startHeartbeat(ws)
    }

    ws.onmessage = (event) => {
      try {
        const data: ChatMessage = JSON.parse(event.data)

        if (data.type === 'pong') return

        if (data.type === 'agent_status' && data.agent) {
          updateAgent({
            agent: data.agent,
            status: (data.status as any) || 'idle',
            message: data.message || '',
            progress: data.progress,
          })
        }

        if (data.type === 'chat' && taskId && data.from !== 'user') {
          addMessage(taskId, data)
        }
      } catch {
        // 忽略解析错误
      }
    }

    ws.onclose = () => {
      // 自动重连（指数退避）
      if (reconnectAttempts.current < maxReconnectAttempts) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000)
        reconnectTimer.current = window.setTimeout(() => {
          reconnectAttempts.current++
          connect()
        }, delay)
      }
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [taskId, updateAgent, addMessage])

  const startHeartbeat = (ws: WebSocket) => {
    const interval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      } else {
        clearInterval(interval)
      }
    }, 30000)
  }

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  const sendMessage = useCallback((command: string, params?: Record<string, any>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: 'user_command',
          command,
          params,
          timestamp: new Date().toISOString(),
        })
      )
    }
  }, [])

  return { sendMessage }
}
