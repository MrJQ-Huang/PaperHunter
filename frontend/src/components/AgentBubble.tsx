import { useRef, useEffect } from 'react'
import { useAgentStore } from '../stores/agentStore'
import { Search, Filter, Download, MessageCircle, Loader2, CheckCircle2, AlertCircle, ChevronDown, ChevronRight, Copy } from 'lucide-react'

const agentMeta: Record<string, { label: string; icon: typeof Search; emoji: string; bg: string; accent: string }> = {
  search: { label: '搜索助手', icon: Search, emoji: '🔍', bg: 'bg-blue-50', accent: 'border-blue-200 text-blue-600' },
  filter: { label: '筛选助手', icon: Filter, emoji: '🎯', bg: 'bg-violet-50', accent: 'border-violet-200 text-violet-600' },
  download: { label: '下载助手', icon: Download, emoji: '📥', bg: 'bg-emerald-50', accent: 'border-emerald-200 text-emerald-600' },
  chat: { label: '聊天助手', icon: MessageCircle, emoji: '💬', bg: 'bg-amber-50', accent: 'border-amber-200 text-amber-600' },
}

interface Props {
  agentKey: string
}

export default function AgentBubble({ agentKey }: Props) {
  const agent = useAgentStore((s) => s.agents[agentKey])
  const logs = useAgentStore((s) => s.agentLogs[agentKey] || [])
  const collapsed = useAgentStore((s) => s.agentCollapsed[agentKey] ?? false)
  const toggleCollapse = useAgentStore((s) => s.toggleAgentCollapse)
  const logsEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!collapsed) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, collapsed])

  if (!agent) return null

  const meta = agentMeta[agentKey] || agentMeta.chat
  const isWorking = agent.status === 'working'
  const isDone = agent.status === 'done'
  const isError = agent.status === 'error'

  const statusText = () => {
    if (isWorking) return agent.message || '工作中...'
    if (isDone) return agent.message || '完成了!'
    if (isError) return '出了点问题'
    return '休息中'
  }

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(logs.join('\n'))
  }

  return (
    <div className={`rounded-2xl border overflow-hidden transition-all duration-300 msg-enter ${
      isWorking ? `${meta.bg} border-current/20` :
      isDone ? 'bg-emerald-50/50 border-emerald-200/50' :
      isError ? 'bg-red-50/50 border-red-200/50' :
      'bg-gray-50/80 border-gray-200/50'
    }`}>
      {/* 头部 */}
      <div
        className="flex items-center gap-2.5 px-4 py-2.5 cursor-pointer select-none hover:bg-black/[0.02] transition-colors"
        onClick={() => toggleCollapse(agentKey)}
      >
        <span className="text-base">{meta.emoji}</span>
        <span className="text-xs font-semibold text-gray-700">{meta.label}</span>

        <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${
          isWorking ? 'bg-blue-100 text-blue-600' :
          isDone ? 'bg-emerald-100 text-emerald-600' :
          isError ? 'bg-red-100 text-red-600' :
          'bg-gray-100 text-gray-500'
        }`}>
          {statusText()}
        </span>

        <div className="ml-auto flex items-center gap-1.5">
          {isWorking && <Loader2 size={12} className="animate-spin text-blue-400" />}
          {isDone && <CheckCircle2 size={12} className="text-emerald-400" />}
          {isError && <AlertCircle size={12} className="text-red-400" />}
          {(isDone || isError) && (
            <button onClick={handleCopy} className="p-0.5 text-gray-400 hover:text-gray-600 transition-colors" title="复制日志">
              <Copy size={11} />
            </button>
          )}
          {collapsed ? <ChevronRight size={13} className="text-gray-400" /> : <ChevronDown size={13} className="text-gray-400" />}
        </div>
      </div>

      {/* 进度条 */}
      {isWorking && agent.progress !== undefined && (
        <div className="px-4 pb-1">
          <div className="h-1 bg-gray-200/60 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${agent.progress}%`, background: 'linear-gradient(90deg, #818cf8, #a78bfa, #c084fc)' }}
            />
          </div>
        </div>
      )}

      {/* 日志 */}
      {!collapsed && logs.length > 0 && (
        <div className="px-4 pb-3 max-h-48 overflow-y-auto space-y-0.5">
          {logs.map((line, i) => (
            <div key={i} className="text-[11px] leading-relaxed text-gray-500 font-mono">
              {line.startsWith('✓') ? <span className="text-emerald-500">{line}</span> :
               line.startsWith('✗') ? <span className="text-red-400">{line}</span> :
               line.startsWith('[状态]') ? <span className="text-blue-400">{line}</span> :
               line}
            </div>
          ))}
          <div ref={logsEndRef} />
        </div>
      )}
    </div>
  )
}
