import { useEffect, useRef } from 'react'
import { useChat } from '../hooks/useChat'
import { usePaperStore, Task } from '../stores/paperStore'
import { useAgentStore } from '../stores/agentStore'
import AgentBubble from './AgentBubble'
import { Send, Play, StopCircle, RotateCcw, Loader2, Sparkles, FileText, Wand2 } from 'lucide-react'

interface Props {
  taskId: string | null
  onTaskCreated?: (task: Task) => void
  onTaskUpdated?: (task: Task) => void
  taskStatus?: string
  searchPlan?: Task['search_plan']
  inputRef?: React.RefObject<HTMLInputElement | null> | React.MutableRefObject<HTMLInputElement | null>
}

export default function ChatWindow({ taskId, onTaskCreated, onTaskUpdated, taskStatus, searchPlan, inputRef: extRef }: Props) {
  const {
    messages, input, setInput, sendMessage, createAndSend, handleSuggestion,
    confirmSearch, terminateTask, resetTask, generatePlan, resetPlan, isLoading,
  } = useChat(taskId, onTaskCreated, onTaskUpdated)
  const bottomRef = useRef<HTMLDivElement>(null)
  const localRef = useRef<HTMLInputElement>(null)
  const ref = extRef || localRef
  const agents = useAgentStore((s) => s.agents)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading, agents])

  // EmptyState 主题选择事件
  useEffect(() => {
    const handler = (e: Event) => {
      const topic = (e as CustomEvent).detail
      if (topic) { setInput(topic); setTimeout(() => doSend(topic), 50) }
    }
    window.addEventListener('chat-send', handler)
    return () => window.removeEventListener('chat-send', handler)
  }, [sendMessage, createAndSend, setInput])

  // 发送消息：sendMessage 内部负责 addMessage（同步执行，气泡立刻出现）
  const doSend = (text: string) => {
    if (!text.trim() || isLoading) return
    setInput('')
    if (taskId) {
      sendMessage(text)
    } else {
      createAndSend(text)
    }
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !isLoading) {
      e.preventDefault()
      doSend(input)
    }
  }

  const hasPlan = searchPlan != null
  const showGeneratePlan = taskId && taskStatus === 'pending' && !hasPlan
  const showConfirm = taskId && taskStatus === 'pending' && hasPlan
  const showTerminate = taskId && taskStatus === 'running'
  const showReset = taskId && taskStatus && ['completed', 'failed', 'cancelled'].includes(taskStatus)
  const showPaperChat = taskId && taskStatus === 'completed'
  const showAgents = taskId && taskStatus && ['running', 'completed', 'failed', 'cancelled'].includes(taskStatus)
  const hasAgents = showAgents && ['search', 'filter', 'download', 'chat'].some((k) => {
    const a = agents[k]
    return a && (a.status !== 'idle' || (useAgentStore.getState().agentLogs[k]?.length ?? 0) > 0)
  })

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* 消息区域 */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3 min-h-0">
        {messages.length === 0 && !isLoading && !taskId && (
          <div className="text-center text-gray-300 text-xs mt-4">在下方输入研究主题开始~</div>
        )}

        {messages.map((msg, i) => (
          <div key={msg.id || `local-${i}`} className={`flex ${msg.from === 'user' ? 'justify-end' : 'justify-start'} msg-enter`}>
            {msg.from === 'user' ? (
              <div className="max-w-[75%] bg-gradient-to-r from-violet-500 to-purple-500 text-white rounded-2xl rounded-br-md px-4 py-2.5 text-sm shadow-sm shadow-violet-200/40">
                <p className="whitespace-pre-wrap">{msg.content}</p>
              </div>
            ) : (
              <div className="max-w-[80%] bg-white text-gray-700 rounded-2xl rounded-bl-md px-4 py-2.5 text-sm border border-gray-100 shadow-sm">
                <div className="flex items-center gap-1.5 mb-1">
                  <Sparkles size={12} className="text-violet-400" />
                  <span className="text-[10px] font-semibold text-violet-400">PaperHunter</span>
                </div>
                <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                {msg.suggestions && msg.suggestions.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {msg.suggestions.map((s, j) => (
                      <button key={j} onClick={() => handleSuggestion(s)} disabled={isLoading}
                        className="px-3 py-1.5 text-[11px] bg-violet-50 hover:bg-violet-100 text-violet-600 rounded-full transition-all active:scale-95 disabled:opacity-40">
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {/* Agent 气泡 */}
        {hasAgents && (
          <div className="space-y-2 py-1">
            {['search', 'filter', 'download', 'chat'].map((k) => {
              const a = agents[k]
              if (a && (a.status !== 'idle' || (useAgentStore.getState().agentLogs[k]?.length ?? 0) > 0)) {
                return <AgentBubble key={k} agentKey={k} />
              }
              return null
            })}
          </div>
        )}

        {/* 加载动画 */}
        {isLoading && (
          <div className="flex justify-start msg-enter">
            <div className="bg-white rounded-2xl rounded-bl-md px-4 py-3 border border-gray-100 shadow-sm">
              <div className="flex items-center gap-2">
                <div className="flex gap-1">
                  {[0, 150, 300].map((d) => (
                    <span key={d} className="w-1.5 h-1.5 bg-violet-300 rounded-full" style={{ animation: `dot-bounce 1s ${d}ms ease-in-out infinite` }} />
                  ))}
                </div>
                <span className="text-[11px] text-gray-400 ml-1">思考中...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* 搜索方案卡片 */}
      {hasPlan && taskStatus === 'pending' && !isLoading && searchPlan && (
        <div className="px-5 py-2">
          <div className="bg-gradient-to-br from-violet-50 to-purple-50 rounded-2xl border border-violet-100 p-4 space-y-2.5">
            <div className="flex items-center gap-2">
              <FileText size={14} className="text-violet-500" />
              <span className="text-xs font-semibold text-violet-600">搜索方案</span>
            </div>
            <div className="space-y-1.5 text-xs text-gray-600">
              <div><span className="text-gray-400">搜索词：</span><span className="font-medium text-gray-800">{searchPlan.query}</span></div>
              <div><span className="text-gray-400">数据源：</span>{searchPlan.sources?.join(', ')}</div>
              {searchPlan.summary && <div><span className="text-gray-400">策略：</span>{searchPlan.summary}</div>}
            </div>
          </div>
        </div>
      )}

      {/* 操作按钮 */}
      {(showGeneratePlan || showConfirm || showTerminate || showReset || showPaperChat) && !isLoading && (
        <div className="px-5 py-2.5 border-t border-gray-100 bg-white/80 backdrop-blur flex gap-2 flex-wrap">
          {showGeneratePlan && (
            <button onClick={generatePlan} className="flex items-center gap-1.5 px-5 py-2.5 bg-gradient-to-r from-violet-500 to-purple-500 text-white text-xs font-medium rounded-xl hover:from-violet-600 hover:to-purple-600 transition-all shadow-sm shadow-violet-200/40 active:scale-[0.98]">
              <Wand2 size={13} /> 生成搜索方案
            </button>
          )}
          {showConfirm && (
            <>
              <button onClick={confirmSearch} className="flex items-center gap-1.5 px-5 py-2.5 bg-gradient-to-r from-emerald-500 to-teal-500 text-white text-xs font-medium rounded-xl hover:from-emerald-600 hover:to-teal-600 transition-all shadow-sm shadow-emerald-200/40 active:scale-[0.98]">
                <Play size={13} /> 确认搜索
              </button>
              <button onClick={resetPlan} className="flex items-center gap-1.5 px-4 py-2.5 bg-gray-50 text-gray-500 text-xs font-medium rounded-xl hover:bg-gray-100 transition-all active:scale-[0.98]">
                <RotateCcw size={13} /> 调整方案
              </button>
            </>
          )}
          {showTerminate && (
            <button onClick={terminateTask} className="flex items-center gap-1.5 px-4 py-2.5 bg-red-50 text-red-500 text-xs font-medium rounded-xl hover:bg-red-100 transition-all active:scale-[0.98]">
              <StopCircle size={13} /> 终止
            </button>
          )}
          {showPaperChat && (
            <>
              <button onClick={() => sendMessage("帮我总结这些论文的主要研究方向和发现")} className="flex items-center gap-1.5 px-4 py-2.5 bg-blue-50 text-blue-500 text-xs font-medium rounded-xl hover:bg-blue-100 transition-all active:scale-[0.98]">
                <FileText size={13} /> 论文总结
              </button>
              <button onClick={() => sendMessage("推荐最相关的5篇论文并说明理由")} className="flex items-center gap-1.5 px-4 py-2.5 bg-blue-50 text-blue-500 text-xs font-medium rounded-xl hover:bg-blue-100 transition-all active:scale-[0.98]">
                <Sparkles size={13} /> 推荐论文
              </button>
            </>
          )}
          {showReset && (
            <button onClick={resetTask} className="flex items-center gap-1.5 px-4 py-2.5 bg-gray-50 text-gray-500 text-xs font-medium rounded-xl hover:bg-gray-100 transition-all active:scale-[0.98]">
              <RotateCcw size={13} /> 重置
            </button>
          )}
        </div>
      )}

      {/* 输入框 */}
      <div className="px-5 py-3 bg-white/80 backdrop-blur border-t border-gray-100 shrink-0">
        <div className="flex items-center gap-2.5 bg-gray-50 rounded-2xl border border-gray-100 focus-within:ring-2 focus-within:ring-violet-200 focus-within:border-violet-200 transition-all px-4 py-1">
          <input
            ref={ref as React.Ref<HTMLInputElement>}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={isLoading}
            placeholder={isLoading ? "等待回复..." : taskId ? "继续聊聊~" : "输入研究主题..."}
            className="flex-1 bg-transparent py-2 text-sm text-gray-700 focus:outline-none placeholder-gray-300 disabled:text-gray-300"
          />
          <button
            onClick={() => doSend(input)}
            disabled={!input.trim() || isLoading}
            className="p-2 bg-gradient-to-r from-violet-500 to-purple-500 text-white rounded-xl hover:from-violet-600 hover:to-purple-600 disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-sm shadow-violet-200/40 active:scale-90 shrink-0"
          >
            {isLoading ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
          </button>
        </div>
      </div>
    </div>
  )
}
