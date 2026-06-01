import { useEffect, useRef } from 'react'
import { useChat } from '../hooks/useChat'
import { usePaperStore, Task } from '../stores/paperStore'
import { Send, Sparkles, Play, StopCircle, RotateCcw, Loader2 } from 'lucide-react'

interface Props {
  taskId: string | null
  onTaskCreated?: (task: Task) => void
  onTaskUpdated?: (task: Task) => void
  taskStatus?: string
}

export default function ChatWindow({ taskId, onTaskCreated, onTaskUpdated, taskStatus }: Props) {
  const {
    messages, input, setInput, sendMessage, handleSuggestion,
    confirmSearch, terminateTask, resetTask, isLoading,
  } = useChat(taskId, onTaskCreated, onTaskUpdated)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !isLoading) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  const showConfirm = taskId && taskStatus === 'pending'
  const showTerminate = taskId && taskStatus === 'running'
  const showReset = taskId && (taskStatus === 'completed' || taskStatus === 'failed' || taskStatus === 'cancelled')

  return (
    <div className="flex flex-col h-full bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
        <Sparkles size={16} className="text-primary-500" />
        <span className="font-medium text-sm text-gray-800">PaperHunter 聊天</span>
        {isLoading && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-blue-500">
            <Loader2 size={12} className="animate-spin" />
            思考中...
          </span>
        )}
        {!isLoading && taskStatus && (
          <span className={`ml-auto text-xs px-2 py-0.5 rounded-full ${
            taskStatus === 'running' ? 'bg-blue-100 text-blue-600' :
            taskStatus === 'pending' ? 'bg-yellow-100 text-yellow-600' :
            taskStatus === 'completed' ? 'bg-green-100 text-green-600' :
            'bg-gray-100 text-gray-500'
          }`}>
            {taskStatus === 'pending' ? '待确认' :
             taskStatus === 'running' ? '执行中' :
             taskStatus === 'completed' ? '已完成' :
             taskStatus}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
        {messages.length === 0 && !isLoading && (
          <div className="text-center text-gray-400 text-sm mt-8">
            <Sparkles size={32} className="mx-auto mb-2 text-gray-300" />
            <p>输入搜索主题开始论文检索</p>
            <p className="text-xs mt-1">例如: "ROS2 navigation" 或 "transformer attention mechanism"</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={msg.id || i}
            className={`flex ${msg.from === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-xl px-4 py-2 text-sm ${
                msg.from === 'user'
                  ? 'bg-primary-500 text-white rounded-br-sm'
                  : 'bg-gray-100 text-gray-800 rounded-bl-sm'
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>

              {msg.suggestions && msg.suggestions.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {msg.suggestions.map((s, j) => (
                    <button
                      key={j}
                      onClick={() => handleSuggestion(s)}
                      disabled={isLoading}
                      className="px-2 py-1 text-xs bg-white/20 hover:bg-white/30 rounded-full transition-colors disabled:opacity-50"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {/* 加载动画 */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-xl rounded-bl-sm px-4 py-3 flex items-center gap-2">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-xs text-gray-400">正在思考...</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* 操作按钮区 */}
      {(showConfirm || showTerminate || showReset) && !isLoading && (
        <div className="px-4 py-2 border-t border-gray-100 flex gap-2">
          {showConfirm && (
            <button
              onClick={confirmSearch}
              className="flex items-center gap-1.5 px-4 py-2 bg-green-500 text-white text-sm rounded-lg hover:bg-green-600 transition-colors"
            >
              <Play size={14} />
              确认开始搜索
            </button>
          )}
          {showTerminate && (
            <button
              onClick={terminateTask}
              className="flex items-center gap-1.5 px-4 py-2 bg-red-500 text-white text-sm rounded-lg hover:bg-red-600 transition-colors"
            >
              <StopCircle size={14} />
              终止任务
            </button>
          )}
          {showReset && (
            <button
              onClick={resetTask}
              className="flex items-center gap-1.5 px-4 py-2 bg-gray-500 text-white text-sm rounded-lg hover:bg-gray-600 transition-colors"
            >
              <RotateCcw size={14} />
              重置任务
            </button>
          )}
        </div>
      )}

      <div className="border-t border-gray-100 p-3">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            placeholder={isLoading ? "等待回复中..." : taskId ? "继续沟通搜索方案..." : "输入搜索主题开始..."}
            className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:bg-gray-50"
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || isLoading}
            className="p-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
      </div>
    </div>
  )
}
