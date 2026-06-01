import { create } from 'zustand'

export interface AgentStatus {
  agent: string
  status: 'idle' | 'working' | 'done' | 'error'
  message: string
  progress?: number
}

interface AgentState {
  agents: Record<string, AgentStatus>
  updateAgent: (update: AgentStatus) => void
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
  updateAgent: (update) =>
    set((state) => ({
      agents: {
        ...state.agents,
        [update.agent]: update,
      },
    })),
  resetAgents: () => set({ agents: { ...defaultAgents } }),
}))
