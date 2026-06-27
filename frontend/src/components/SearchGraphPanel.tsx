import { useAgentStore } from '../stores/agentStore'
import { Activity, CheckCircle2, Circle, Database, GitBranch, Loader2, Network, Search } from 'lucide-react'

const statusStyles: Record<string, string> = {
  pending: 'bg-gray-50 text-gray-400 border-gray-200',
  searching: 'bg-blue-50 text-blue-600 border-blue-200',
  found: 'bg-violet-50 text-violet-600 border-violet-200',
  indexing: 'bg-amber-50 text-amber-700 border-amber-200',
  done: 'bg-emerald-50 text-emerald-600 border-emerald-200',
  error: 'bg-red-50 text-red-500 border-red-200',
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'searching' || status === 'indexing') return <Loader2 size={13} className="animate-spin" />
  if (status === 'done' || status === 'found') return <CheckCircle2 size={13} />
  return <Circle size={12} />
}

export default function SearchGraphPanel() {
  const graph = useAgentStore((s) => s.searchGraph)
  const branches = Object.values(graph.branches)

  if (!graph.domain && branches.length === 0 && graph.phase === 'idle') return null

  return (
    <div className="rounded-2xl border border-violet-100 bg-white p-4 shadow-sm msg-enter">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Network size={15} className="text-violet-500" />
            <span className="text-xs font-semibold text-gray-800">实时检索图谱</span>
            <span className={`text-[10px] px-2 py-0.5 rounded-full border ${statusStyles[graph.status] || statusStyles.pending}`}>
              {graph.phase || '准备中'}
            </span>
          </div>
          <div className="text-sm font-semibold text-gray-900 truncate">{graph.domain || '正在构建研究图谱'}</div>
          {graph.goal && <div className="text-[11px] text-gray-400 truncate mt-0.5">{graph.goal}</div>}
        </div>
        <div className="grid grid-cols-2 gap-2 text-right shrink-0">
          <div>
            <div className="text-[10px] text-gray-400">发现</div>
            <div className="text-sm font-semibold text-gray-700">{graph.found_count}</div>
          </div>
          <div>
            <div className="text-[10px] text-gray-400">入库</div>
            <div className="text-sm font-semibold text-gray-700">{graph.indexed_count}</div>
          </div>
        </div>
      </div>

      {graph.message && (
        <div className="mb-3 flex items-center gap-2 text-[11px] text-gray-500 bg-gray-50 rounded-lg px-2.5 py-1.5">
          <Activity size={12} className="text-violet-400" />
          <span className="truncate">{graph.message}</span>
        </div>
      )}

      <div className="flex gap-3 overflow-x-auto pb-1">
        {branches.length === 0 ? (
          <div className="text-xs text-gray-300 py-5">等待 Search Agent 下发分支...</div>
        ) : branches.slice(0, 8).map((branch) => {
          const sourceList = Object.entries(branch.sources)
          return (
            <div key={branch.name} className="w-64 shrink-0 rounded-xl border border-gray-100 bg-gray-50/40 p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <GitBranch size={13} className="text-violet-400 shrink-0" />
                    <span className="text-xs font-semibold text-gray-800 truncate">{branch.name}</span>
                  </div>
                  {branch.intent && <p className="text-[10px] text-gray-400 line-clamp-2 mt-1">{branch.intent}</p>}
                </div>
                <span className={`shrink-0 flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border ${statusStyles[branch.status] || statusStyles.pending}`}>
                  <StatusIcon status={branch.status} />
                  {branch.found_count}
                </span>
              </div>

              <div className="mt-2 space-y-1">
                {sourceList.length === 0 ? (
                  <div className="text-[11px] text-gray-300">等待数据源...</div>
                ) : sourceList.slice(0, 4).map(([source, state]) => (
                  <div key={source} className="flex items-center justify-between gap-2 text-[11px]">
                    <span className="flex items-center gap-1 text-gray-500 truncate">
                      <Search size={10} className="text-gray-300" />
                      {source}
                    </span>
                    <span className={`px-1.5 py-0.5 rounded ${state.status === 'searching' ? 'bg-blue-50 text-blue-500' : state.status === 'error' ? 'bg-red-50 text-red-500' : 'bg-white text-gray-400'}`}>
                      {state.status === 'searching' ? '检索中' : state.status === 'error' ? '失败' : `${state.found_count || 0} 篇`}
                    </span>
                  </div>
                ))}
              </div>

              {branch.latest_papers.length > 0 && (
                <div className="mt-2 border-t border-gray-100 pt-2 space-y-1">
                  {branch.latest_papers.slice(0, 3).map((paper) => (
                    <div key={paper.id} className="flex items-start gap-1.5 text-[10px] text-gray-500">
                      <Database size={10} className="mt-0.5 text-gray-300 shrink-0" />
                      <span className="line-clamp-1">{paper.year ? `${paper.year} · ` : ''}{paper.title}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
