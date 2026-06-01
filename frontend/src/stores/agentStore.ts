import { create } from 'zustand'

export interface AgentStatus {
  agent: string
  status: 'idle' | 'working' | 'done' | 'error'
  message: string
  progress?: number
}

interface AgentState {
  agents: Record<string, AgentStatus>
  agentLogs: Record<string, string[]>
  agentCollapsed: Record<string, boolean>
  updateAgent: (update: AgentStatus) => void
  appendAgentLog: (agent: string, logLine: string) => void
  toggleAgentCollapse: (agent: string) => void
  setAgentCollapsed: (agent: string, collapsed: boolean) => void
  clearAgentLogs: () => void
  resetAgents: () => void
}

const defaultAgents: Record<string, AgentStatus> = {
  search: { agent: 'search', status: 'idle', message: '等待中...' },
  filter: { agent: 'filter', status: 'idle', message: '等待中...' },
  download: { agent: 'download', status: 'idle', message: '等待中...' },
  chat: { agent: 'chat', status: 'idle', message: '等待中...' },
}

export const useAgentStore = create<AgentState>((set) => ({
  agents: { ...defaultAgents },
  agentLogs: {},
  agentCollapsed: {},
  updateAgent: (update) =>
    set((state) => ({
      agents: {
        ...state.agents,
        [update.agent]: update,
      },
    })),
  appendAgentLog: (agent, logLine) =>
    set((state) => ({
      agentLogs: {
        ...state.agentLogs,
        [agent]: [...(state.agentLogs[agent] || []), logLine],
      },
    })),
  toggleAgentCollapse: (agent) =>
    set((state) => ({
      agentCollapsed: {
        ...state.agentCollapsed,
        [agent]: !state.agentCollapsed[agent],
      },
    })),
  setAgentCollapsed: (agent, collapsed) =>
    set((state) => ({
      agentCollapsed: {
        ...state.agentCollapsed,
        [agent]: collapsed,
      },
    })),
  clearAgentLogs: () => set({ agentLogs: {}, agentCollapsed: {} }),
  resetAgents: () => set({ agents: { ...defaultAgents }, agentLogs: {}, agentCollapsed: {} }),
}))
