import { Task } from '../stores/paperStore'

interface Props {
  task: Task
}

const statusLabels: Record<string, { label: string; color: string }> = {
  pending: { label: '等待中', color: 'bg-gray-100 text-gray-600' },
  running: { label: '执行中', color: 'bg-blue-100 text-blue-600' },
  reviewing: { label: '待筛选', color: 'bg-purple-100 text-purple-600' },
  paused: { label: '已暂停', color: 'bg-yellow-100 text-yellow-600' },
  completed: { label: '已完成', color: 'bg-green-100 text-green-600' },
  failed: { label: '失败', color: 'bg-red-100 text-red-600' },
  cancelled: { label: '已取消', color: 'bg-gray-100 text-gray-600' },
}

export default function TaskProgress({ task }: Props) {
  const statusInfo =
    task.status === 'running' && (task.total_papers_found || 0) > 0
      ? { label: '标注中', color: 'bg-sky-100 text-sky-600' }
      : statusLabels[task.status] || statusLabels.pending
  const total = task.total_papers_found || 0
  const filtered = task.papers_after_filter || 0
  const downloaded = task.papers_downloaded || 0
  const failed = task.papers_failed || 0

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-gray-800 truncate flex-1">{task.query}</h3>
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusInfo.color}`}>
          {statusInfo.label}
        </span>
      </div>

      <div className="grid grid-cols-4 gap-3 text-center">
        <div>
          <div className="text-2xl font-bold text-blue-600">{total}</div>
          <div className="text-xs text-gray-500">搜索到</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-purple-600">{filtered}</div>
          <div className="text-xs text-gray-500">推荐</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-green-600">{downloaded}</div>
          <div className="text-xs text-gray-500">已下载</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-red-500">{failed}</div>
          <div className="text-xs text-gray-500">失败</div>
        </div>
      </div>

      {task.error_message && (
        <p className="mt-2 text-xs text-red-500 bg-red-50 rounded p-2">{task.error_message}</p>
      )}
    </div>
  )
}
