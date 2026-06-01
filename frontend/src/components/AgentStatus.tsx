import { AgentStatus as AgentStatusType } from '../stores/agentStore'
import { Search, Filter, Download, MessageCircle, Loader2, CheckCircle2, AlertCircle, Clock } from 'lucide-react'

const agentConfig: Record<string, { label: string; icon: typeof Search; color: string }> = {
  search: { label: 'Search Agent', icon: Search, color: 'text-blue-500' },
  filter: { label: 'Filter Agent', icon: Filter, color: 'text-purple-500' },
  download: { label: 'Download Agent', icon: Download, color: 'text-green-500' },
  chat: { label: 'Chat Agent', icon: MessageCircle, color: 'text-orange-500' },
}

const statusConfig: Record<string, { icon: typeof Clock; color: string; bg: string }> = {
  idle: { icon: Clock, color: 'text-gray-400', bg: 'bg-gray-50' },
  working: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-50' },
  done: { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-50' },
  error: { icon: AlertCircle, color: 'text-red-500', bg: 'bg-red-50' },
}

interface Props {
  agent: AgentStatusType
}

export default function AgentStatusCard({ agent }: Props) {
  const config = agentConfig[agent.agent] || agentConfig.chat
  const status = statusConfig[agent.status] || statusConfig.idle
  const Icon = config.icon
  const StatusIcon = status.icon

  return (
    <div className={`rounded-xl border border-gray-200 p-4 ${status.bg} transition-all`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Icon size={18} className={config.color} />
          <span className="font-medium text-sm text-gray-800">{config.label}</span>
        </div>
        <StatusIcon
          size={16}
          className={`${status.color} ${agent.status === 'working' ? 'animate-spin' : ''}`}
        />
      </div>

      <p className="text-xs text-gray-600 mb-2 line-clamp-2">{agent.message}</p>

      {agent.progress !== undefined && (
        <div className="w-full bg-gray-200 rounded-full h-1.5">
          <div
            className="bg-primary-500 h-1.5 rounded-full transition-all duration-500"
            style={{ width: `${agent.progress}%` }}
          />
        </div>
      )}
    </div>
  )
}
