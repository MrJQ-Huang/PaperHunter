import { Paper } from '../stores/paperStore'
import { ExternalLink, Download, FileText, Copy, CheckCircle2, Pencil, Trash2 } from 'lucide-react'
import { useState } from 'react'

interface Props {
  paper: Paper
  onDownload?: (id: string) => void
  onEdit?: (paper: Paper) => void
  onDelete?: (id: string) => void
  selected?: boolean
  onToggleSelect?: (id: string) => void
}

const sourceColors: Record<string, string> = {
  arxiv: 'bg-red-50 text-red-600',
  semantic_scholar: 'bg-blue-50 text-blue-600',
  openalex: 'bg-green-50 text-green-600',
  crossref: 'bg-purple-50 text-purple-600',
  google_scholar: 'bg-yellow-50 text-yellow-600',
}

export default function PaperCard({ paper, onDownload, onEdit, onDelete, selected, onToggleSelect }: Props) {
  const [copied, setCopied] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const copyDoi = () => {
    if (paper.doi) {
      navigator.clipboard.writeText(paper.doi)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleDelete = () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      setTimeout(() => setConfirmDelete(false), 3000)
      return
    }
    onDelete?.(paper.id)
    setConfirmDelete(false)
  }

  return (
    <div className={`bg-white rounded-xl border p-4 hover:shadow-md transition-shadow group ${selected ? 'border-violet-300 ring-1 ring-violet-200' : 'border-gray-200'}`}>
      {/* 标题 + 管理按钮 */}
      <div className="flex items-start justify-between gap-2 mb-2">
        {onToggleSelect && (
          <input
            type="checkbox"
            checked={selected || false}
            onChange={() => onToggleSelect(paper.id)}
            className="mt-1 rounded border-gray-300 text-violet-500 shrink-0"
          />
        )}
        <h3 className="font-semibold text-gray-900 text-sm leading-snug line-clamp-2 flex-1">
          {paper.title}
        </h3>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          {onEdit && (
            <button
              onClick={() => onEdit(paper)}
              className="p-1 text-gray-400 hover:text-primary-500 transition-colors"
              title="编辑"
            >
              <Pencil size={13} />
            </button>
          )}
          {onDelete && (
            <button
              onClick={handleDelete}
              className={`p-1 transition-colors ${
                confirmDelete ? 'text-red-600 bg-red-50 rounded' : 'text-gray-400 hover:text-red-500'
              }`}
              title={confirmDelete ? '再次点击确认删除' : '删除'}
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      </div>

      {/* 作者 */}
      <p className="text-xs text-gray-500 mb-2 line-clamp-1">
        {paper.authors.slice(0, 3).join(', ')}
        {paper.authors.length > 3 && ` et al.`}
      </p>

      {/* 元信息 */}
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <span className={`px-2 py-0.5 rounded text-xs font-medium ${sourceColors[paper.source] || 'bg-gray-50 text-gray-600'}`}>
          {paper.source}
        </span>
        {paper.published_date && (
          <span className="text-xs text-gray-400">
            {new Date(paper.published_date).getFullYear()}
          </span>
        )}
        {paper.citation_count !== null && paper.citation_count !== undefined && (
          <span className="text-xs text-gray-400">
            引用: {paper.citation_count}
          </span>
        )}
        {paper.is_open_access && (
          <span className="text-xs text-green-500 font-medium">OA</span>
        )}
        {paper.relevance_score !== null && paper.relevance_score !== undefined && (
          <span className="text-xs text-primary-500 font-medium">
            评分: {paper.relevance_score.toFixed(1)}
          </span>
        )}
      </div>

      {/* 摘要 */}
      <p className="text-xs text-gray-600 line-clamp-3 mb-3">{paper.abstract}</p>

      {/* 操作按钮 */}
      <div className="flex items-center gap-2">
        {paper.download_status === 'done' ? (
          <span className="flex items-center gap-1 text-xs text-green-600">
            <CheckCircle2 size={14} />
            已下载
          </span>
        ) : (
          <button
            onClick={() => onDownload?.(paper.id)}
            className="flex items-center gap-1 px-2 py-1 text-xs bg-primary-50 text-primary-600 rounded hover:bg-primary-100 transition-colors"
          >
            <Download size={12} />
            下载
          </button>
        )}
        {paper.url && (
          <a
            href={paper.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 hover:text-gray-700"
          >
            <ExternalLink size={12} />
            原文
          </a>
        )}
        {paper.doi && (
          <button
            onClick={copyDoi}
            className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 hover:text-gray-700"
          >
            {copied ? <CheckCircle2 size={12} /> : <Copy size={12} />}
            DOI
          </button>
        )}
        {paper.local_pdf_path && (
          <a
            href={`/api/papers/${paper.id}/pdf`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 hover:text-gray-700"
          >
            <FileText size={12} />
            PDF
          </a>
        )}
      </div>
    </div>
  )
}
