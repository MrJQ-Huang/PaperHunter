import { useState, useEffect } from 'react'
import { Settings as SettingsIcon, Save, RefreshCw } from 'lucide-react'

interface Config {
  llm_model: string
  llm_base_url: string
  download_dir: string
}

export default function Settings() {
  const [config, setConfig] = useState<Config | null>(null)
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch('/api/config').then((r) => r.json()),
      fetch('/api/stats').then((r) => r.json()),
    ])
      .then(([cfg, st]) => {
        setConfig(cfg)
        setStats(st)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="text-center py-12 text-gray-400">
        <RefreshCw size={24} className="mx-auto mb-2 animate-spin" />
        加载中...
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-2 mb-6">
        <SettingsIcon size={24} className="text-primary-500" />
        <h1 className="text-xl font-bold text-gray-800">系统设置</h1>
      </div>

      {/* LLM 配置 */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="font-semibold text-gray-800 mb-4">LLM 配置</h2>
        <div className="space-y-3">
          <div>
            <label className="text-sm text-gray-500 block mb-1">模型</label>
            <input
              type="text"
              value={config?.llm_model || ''}
              readOnly
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg bg-gray-50"
            />
          </div>
          <div>
            <label className="text-sm text-gray-500 block mb-1">API 地址</label>
            <input
              type="text"
              value={config?.llm_base_url || ''}
              readOnly
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg bg-gray-50"
            />
          </div>
        </div>
        <p className="text-xs text-gray-400 mt-3">
          配置通过 .env 文件管理，修改后重启后端生效
        </p>
      </div>

      {/* 存储配置 */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="font-semibold text-gray-800 mb-4">存储配置</h2>
        <div>
          <label className="text-sm text-gray-500 block mb-1">下载目录</label>
          <input
            type="text"
            value={config?.download_dir || ''}
            readOnly
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg bg-gray-50"
          />
        </div>
      </div>

      {/* 统计信息 */}
      {stats && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-800 mb-4">系统统计</h2>
          <div className="grid grid-cols-3 gap-4 text-center">
            <div className="bg-blue-50 rounded-lg p-4">
              <div className="text-2xl font-bold text-blue-600">{stats.total_papers}</div>
              <div className="text-xs text-gray-500">论文总数</div>
            </div>
            <div className="bg-green-50 rounded-lg p-4">
              <div className="text-2xl font-bold text-green-600">{stats.downloaded_papers}</div>
              <div className="text-xs text-gray-500">已下载</div>
            </div>
            <div className="bg-purple-50 rounded-lg p-4">
              <div className="text-2xl font-bold text-purple-600">{stats.total_tasks}</div>
              <div className="text-xs text-gray-500">任务总数</div>
            </div>
          </div>
        </div>
      )}

      {/* 数据源说明 */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="font-semibold text-gray-800 mb-4">支持的数据源</h2>
        <div className="space-y-2">
          {[
            { name: 'arXiv', desc: '预印本 (物理/CS/Math/生物)', key: '无需', limit: '无' },
            { name: 'Semantic Scholar', desc: '2亿+ 论文，含引用关系', key: '可选', limit: '100 req/5min' },
            { name: 'OpenAlex', desc: '2.5亿+ 学术作品', key: '无需', limit: '100k req/day' },
            { name: 'CrossRef', desc: 'DOI 元数据 (出版商)', key: '无需', limit: '50 req/s' },
            { name: 'Google Scholar', desc: '最广泛覆盖', key: '需代理', limit: '易被封' },
          ].map((src) => (
            <div key={src.name} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
              <div>
                <span className="font-medium text-sm text-gray-800">{src.name}</span>
                <span className="text-xs text-gray-400 ml-2">{src.desc}</span>
              </div>
              <div className="text-xs text-gray-500">
                Key: {src.key} | 限制: {src.limit}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
