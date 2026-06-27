import { create } from 'zustand'

export interface Paper {
  id: string
  title: string
  authors: string[]
  abstract: string
  doi: string | null
  url: string
  pdf_url: string | null
  source: string
  published_date: string | null
  citation_count: number | null
  venue: string | null
  is_open_access: boolean
  topics: string[]
  paper_type: string | null
  subtopics: string[]
  learning_role: string | null
  difficulty: string | null
  method_tags: string[]
  quality_tags: string[]
  annotation_reason: string | null
  search_subtopic: string | null
  local_pdf_path: string | null
  download_status: string
  relevance_score: number | null
  created_at: string
}

export interface Task {
  id: string
  query: string
  sources: string[]
  filters: Record<string, any>
  status: string
  total_papers_found: number
  papers_after_filter: number
  papers_downloaded: number
  papers_failed: number
  search_plan: {
    query: string
    sources: string[]
    filters: Record<string, any>
    summary: string
    search_mode?: string
    goal?: string
    domain?: string
    core_concepts?: string[]
    field_terms?: string[]
    exclude_terms?: string[]
    preferred_paper_types?: string[]
    subtopics?: Array<{
      name: string
      intent?: string
      required_terms?: string[]
      optional_terms?: string[]
      queries?: Record<string, string>
    }>
    clarifying_questions?: string[]
  } | null
  created_at: string
  updated_at: string
  error_message: string | null
}

export interface ChatMessage {
  id?: string
  type: 'chat' | 'agent_status' | 'agent_log' | 'search_graph_update' | 'pong'
  from?: 'user' | 'agent'
  content?: string
  timestamp?: string
  suggestions?: string[]
  agent?: string
  status?: string
  message?: string
  progress?: number
}

interface PaperState {
  papers: Paper[]
  total: number
  currentTask: Task | null
  tasks: Task[]
  messagesByTask: Record<string, ChatMessage[]>
  setPapers: (papers: Paper[], total: number) => void
  setCurrentTask: (task: Task | null) => void
  setTasks: (tasks: Task[]) => void
  addMessage: (taskId: string, msg: ChatMessage) => void
  getMessages: (taskId: string) => ChatMessage[]
  setMessages: (taskId: string, msgs: ChatMessage[]) => void
  clearMessages: (taskId: string) => void
  updateTask: (task: Task) => void
  removePaper: (paperId: string) => void
  updatePaper: (paper: Paper) => void
}

export const usePaperStore = create<PaperState>((set, get) => ({
  papers: [],
  total: 0,
  currentTask: null,
  tasks: [],
  messagesByTask: {},
  setPapers: (papers, total) => set({ papers, total }),
  setCurrentTask: (task) => set({ currentTask: task }),
  setTasks: (tasks) => set({ tasks }),
  addMessage: (taskId, msg) =>
    set((state) => ({
      messagesByTask: {
        ...state.messagesByTask,
        [taskId]: [...(state.messagesByTask[taskId] || []), msg],
      },
    })),
  getMessages: (taskId) => get().messagesByTask[taskId] || [],
  setMessages: (taskId, msgs) =>
    set((state) => ({
      messagesByTask: { ...state.messagesByTask, [taskId]: msgs },
    })),
  clearMessages: (taskId) =>
    set((state) => ({
      messagesByTask: {
        ...state.messagesByTask,
        [taskId]: [],
      },
    })),
  updateTask: (task) =>
    set((state) => {
      const hasTask = state.tasks.some((t) => t.id === task.id)
      return {
        currentTask: state.currentTask?.id === task.id ? task : state.currentTask,
        tasks: hasTask ? state.tasks.map((t) => (t.id === task.id ? task : t)) : [task, ...state.tasks],
      }
    }),
  removePaper: (paperId) =>
    set((state) => ({
      papers: state.papers.filter((p) => p.id !== paperId),
      total: Math.max(0, state.total - 1),
    })),
  updatePaper: (paper) =>
    set((state) => ({
      papers: state.papers.map((p) => (p.id === paper.id ? paper : p)),
    })),
}))
