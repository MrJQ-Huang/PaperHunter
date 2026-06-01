import { useState } from 'react'
import { SlidersHorizontal } from 'lucide-react'

interface FilterState {
  year_min: number | null
  citations_min: number | null
  only_oa: boolean
  exclude_reviews: boolean
}

interface Props {
  onApply: (filters: FilterState) => void
}

export default function FilterPanel({ onApply }: Props) {
  const [filters, setFilters] = useState<FilterState>({
    year_min: null,
    citations_min: null,
    only_oa: false,
    exclude_reviews: false,
  })

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-3">
        <SlidersHorizontal size={16} className="text-gray-500" />
        <span className="font-medium text-sm text-gray-800">筛选条件</span>
      </div>

      <div className="space-y-3">
        <div>
          <label className="text-xs text-gray-500 block mb-1">最早年份</label>
          <input
            type="number"
            value={filters.year_min || ''}
            onChange={(e) => setFilters({ ...filters, year_min: e.target.value ? Number(e.target.value) : null })}
            placeholder="如: 2022"
            className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>

        <div>
          <label className="text-xs text-gray-500 block mb-1">最低引用数</label>
          <input
            type="number"
            value={filters.citations_min || ''}
            onChange={(e) => setFilters({ ...filters, citations_min: e.target.value ? Number(e.target.value) : null })}
            placeholder="如: 10"
            className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={filters.only_oa}
            onChange={(e) => setFilters({ ...filters, only_oa: e.target.checked })}
            className="rounded text-primary-500"
          />
          <span className="text-sm text-gray-700">仅开放获取</span>
        </label>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={filters.exclude_reviews}
            onChange={(e) => setFilters({ ...filters, exclude_reviews: e.target.checked })}
            className="rounded text-primary-500"
          />
          <span className="text-sm text-gray-700">排除综述</span>
        </label>

        <button
          onClick={() => onApply(filters)}
          className="w-full py-2 bg-primary-500 text-white text-sm rounded-lg hover:bg-primary-600 transition-colors"
        >
          应用筛选
        </button>
      </div>
    </div>
  )
}
