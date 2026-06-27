import { create } from 'zustand'

export interface AgentStatus {
  agent: string
  status: 'idle' | 'working' | 'done' | 'error'
  message: string
  progress?: number
}

export interface SearchGraphPaper {
  id: string
  title: string
  year?: number | null
  source?: string
  subtopic?: string | null
}

export interface SearchGraphBranch {
  name: string
  intent?: string
  status: 'pending' | 'searching' | 'found' | 'indexing' | 'done' | 'error'
  found_count: number
  indexed_count: number
  sources: Record<string, {
    status: string
    found_count: number
    query?: string
    message?: string
  }>
  latest_papers: SearchGraphPaper[]
}

export interface SearchGraphState {
  phase: string
  status: string
  domain: string
  goal: string
  message: string
  found_count: number
  indexed_count: number
  branches: Record<string, SearchGraphBranch>
}

interface AgentState {
  agents: Record<string, AgentStatus>
  agentLogs: Record<string, string[]>
  agentCollapsed: Record<string, boolean>
  searchGraph: SearchGraphState
  updateAgent: (update: AgentStatus) => void
  updateSearchGraph: (update: Record<string, any>) => void
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

const defaultSearchGraph: SearchGraphState = {
  phase: 'idle',
  status: 'idle',
  domain: '',
  goal: '',
  message: '',
  found_count: 0,
  indexed_count: 0,
  branches: {},
}

export const useAgentStore = create<AgentState>((set) => ({
  agents: { ...defaultAgents },
  agentLogs: {},
  agentCollapsed: {},
  searchGraph: { ...defaultSearchGraph },
  updateAgent: (update) =>
    set((state) => ({
      agents: {
        ...state.agents,
        [update.agent]: update,
      },
    })),
  updateSearchGraph: (update) =>
    set((state) => {
      const branches = { ...state.searchGraph.branches }

      if (Array.isArray(update.subtopics)) {
        update.subtopics.forEach((item: any) => {
          const name = item?.name
          if (!name) return
          branches[name] = branches[name] || {
            name,
            intent: item.intent,
            status: 'pending',
            found_count: 0,
            indexed_count: 0,
            sources: {},
            latest_papers: [],
          }
          branches[name] = { ...branches[name], intent: item.intent || branches[name].intent }
        })
      }

      if (update.subtopic) {
        const name = update.subtopic
        const existing = branches[name] || {
          name,
          status: 'pending',
          found_count: 0,
          indexed_count: 0,
          sources: {},
          latest_papers: [],
        }
        const sources = { ...existing.sources }
        if (update.source) {
          const sourceState = sources[update.source] || { status: 'pending', found_count: 0 }
          sources[update.source] = {
            ...sourceState,
            status: update.status || sourceState.status,
            query: update.query || sourceState.query,
            message: update.message || sourceState.message,
            found_count: update.found_count ?? sourceState.found_count,
          }
        }
        const latest = update.latest_papers
          ? [...update.latest_papers, ...existing.latest_papers].filter((paper, index, arr) => arr.findIndex((p) => p.id === paper.id) === index).slice(0, 8)
          : existing.latest_papers
        branches[name] = {
          ...existing,
          status: update.status || existing.status,
          found_count: update.branch_found_count ?? existing.found_count,
          indexed_count: update.indexed_count ?? existing.indexed_count,
          sources,
          latest_papers: latest,
        }
      }

      return {
        searchGraph: {
          ...state.searchGraph,
          phase: update.phase || state.searchGraph.phase,
          status: update.status || state.searchGraph.status,
          domain: update.domain || state.searchGraph.domain,
          goal: update.goal || state.searchGraph.goal,
          message: update.message || state.searchGraph.message,
          found_count: update.found_count ?? state.searchGraph.found_count,
          indexed_count: update.indexed_count ?? state.searchGraph.indexed_count,
          branches,
        },
      }
    }),
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
  resetAgents: () => set({ agents: { ...defaultAgents }, agentLogs: {}, agentCollapsed: {}, searchGraph: { ...defaultSearchGraph } }),
}))
