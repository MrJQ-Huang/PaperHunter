import { useState, useEffect } from 'react'
import { Settings as SettingsIcon, Save, RefreshCw, PlugZap, Upload, CheckCircle2, AlertCircle } from 'lucide-react'

interface Config {
  llm_api_type: 'anthropic' | 'openai'
  llm_model: string
  llm_base_url: string
  llm_api_key?: string
  llm_api_key_masked?: string
  has_llm_api_key?: boolean
  cc_switch_config_path?: string
  provider_name?: string
  source?: string
  download_dir: string
}

type TestResult = {
  ok: boolean
  response?: string
  error?: string
  api_type?: string
  model?: string
  base_url?: string
}

export default function Settings() {
  const [config, setConfig] = useState<Config | null>(null)
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [importing, setImporting] = useState(false)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [saveMessage, setSaveMessage] = useState('')

  const load = () => {
    setLoading(true)
    Promise.all([
      fetch('/api/settings/llm').then((r) => r.json()),
      fetch('/api/stats').then((r) => r.json()),
    ])
      .then(([cfg, st]) => {
        setConfig({ ...cfg, llm_api_key: '' })
        setStats(st)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const updateConfig = (patch: Partial<Config>) => {
    setConfig((prev) => prev ? { ...prev, ...patch } : prev)
    setSaveMessage('')
    setTestResult(null)
  }

  const testConnection = async () => {
    if (!config) return
    setTesting(true)
    setTestResult(null)
    try {
      const resp = await fetch('/api/settings/llm/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          llm_api_type: config.llm_api_type,
          llm_model: config.llm_model,
          llm_base_url: config.llm_base_url,
          llm_api_key: config.llm_api_key || undefined,
        }),
      })
      setTestResult(await resp.json())
    } catch (e: any) {
      setTestResult({ ok: false, error: e?.message || '测试失败' })
    } finally {
      setTesting(false)
    }
  }

  const saveConfig = async () => {
    if (!config) return
    setSaving(true)
    setSaveMessage('')
    try {
      const resp = await fetch('/api/settings/llm', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          llm_api_type: config.llm_api_type,
          llm_model: config.llm_model,
          llm_base_url: config.llm_base_url,
          llm_api_key: config.llm_api_key || undefined,
          cc_switch_config_path: config.cc_switch_config_path || '',
        }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || '保存失败')
      setConfig({ ...data.config, llm_api_key: '' })
      setSaveMessage('已保存，并已更新当前后端运行时配置')
    } catch (e: any) {
      setSaveMessage(e?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const importCCSwitch = async () => {
    if (!config) return
    setImporting(true)
    setSaveMessage('')
    setTestResult(null)
    try {
      const resp = await fetch('/api/settings/llm/import-ccswitch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: config.cc_switch_config_path || undefined, save: true, test: true }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || '导入失败')
      setConfig((prev) => prev ? { ...prev, ...data.config } : data.config)
      if (data.connection_test) setTestResult(data.connection_test)
      setSaveMessage(data.config?.provider_name ? `已连接并保存 CC Switch 当前大脑：${data.config.provider_name}` : '已读取并保存外部模型配置')
    } catch (e: any) {
      setSaveMessage(e?.message || '导入失败')
    } finally {
      setImporting(false)
    }
  }

  if (loading) {
    return (
      <div className="text-center py-12 text-gray-400">
        <RefreshCw size={24} className="mx-auto mb-2 animate-spin" />
        加载中...
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-2 mb-6">
        <SettingsIcon size={24} className="text-primary-500" />
        <h1 className="text-xl font-bold text-gray-800">系统设置</h1>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-semibold text-gray-800">LLM 大脑配置</h2>
          <span className={`text-xs px-2 py-1 rounded-full ${config?.has_llm_api_key ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
            {config?.provider_name ? `CC Switch: ${config.provider_name}` : config?.has_llm_api_key ? `已配置 Key ${config.llm_api_key_masked || ''}` : '未配置有效 Key'}
          </span>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <label className="text-sm text-gray-500 block mb-1">接口类型</label>
            <select
              value={config?.llm_api_type || 'anthropic'}
              onChange={(e) => updateConfig({ llm_api_type: e.target.value as Config['llm_api_type'] })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-violet-100"
            >
              <option value="anthropic">Anthropic Messages 兼容</option>
              <option value="openai">OpenAI Chat Completions 兼容</option>
            </select>
          </div>
          <div>
            <label className="text-sm text-gray-500 block mb-1">模型</label>
            <input
              type="text"
              value={config?.llm_model || ''}
              onChange={(e) => updateConfig({ llm_model: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-100"
            />
          </div>
          <div className="md:col-span-2">
            <label className="text-sm text-gray-500 block mb-1">API 地址</label>
            <input
              type="text"
              value={config?.llm_base_url || ''}
              onChange={(e) => updateConfig({ llm_base_url: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-100"
            />
          </div>
          <div className="md:col-span-2">
            <label className="text-sm text-gray-500 block mb-1">API Key</label>
            <input
              type="password"
              value={config?.llm_api_key || ''}
              onChange={(e) => updateConfig({ llm_api_key: e.target.value })}
              placeholder={config?.has_llm_api_key ? `留空则继续使用 ${config.llm_api_key_masked}` : '输入 API Key'}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-100"
            />
          </div>
          <div className="md:col-span-2">
            <label className="text-sm text-gray-500 block mb-1">CC Switch 配置路径</label>
            <input
              type="text"
              value={config?.cc_switch_config_path || ''}
              onChange={(e) => updateConfig({ cc_switch_config_path: e.target.value })}
              placeholder="可选：默认会自动读取当前用户的 .cc-switch；也可填写 CC Switch 目录或配置文件路径"
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-100"
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mt-5">
          <button onClick={testConnection} disabled={testing || !config?.llm_model || !config?.llm_base_url}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-50 text-blue-600 text-sm font-medium rounded-lg hover:bg-blue-100 disabled:opacity-40">
            {testing ? <RefreshCw size={15} className="animate-spin" /> : <PlugZap size={15} />} 测试连接
          </button>
          <button onClick={importCCSwitch} disabled={importing}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-violet-50 text-violet-600 text-sm font-medium rounded-lg hover:bg-violet-100 disabled:opacity-40">
            {importing ? <RefreshCw size={15} className="animate-spin" /> : <Upload size={15} />} 连接当前 CC Switch 大脑
          </button>
          <button onClick={saveConfig} disabled={saving || !config?.llm_model || !config?.llm_base_url}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-emerald-50 text-emerald-600 text-sm font-medium rounded-lg hover:bg-emerald-100 disabled:opacity-40">
            {saving ? <RefreshCw size={15} className="animate-spin" /> : <Save size={15} />} 保存配置
          </button>
        </div>

        {testResult && (
          <div className={`mt-4 rounded-lg px-3 py-2 text-sm flex items-start gap-2 ${testResult.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
            {testResult.ok ? <CheckCircle2 size={16} className="mt-0.5 shrink-0" /> : <AlertCircle size={16} className="mt-0.5 shrink-0" />}
            <div>
              <div className="font-medium">{testResult.ok ? '连接成功' : '连接失败'}</div>
              <div className="text-xs opacity-80 break-all">{testResult.ok ? testResult.response : testResult.error}</div>
            </div>
          </div>
        )}

        {saveMessage && (
          <div className="mt-4 text-sm text-gray-500 bg-gray-50 rounded-lg px-3 py-2">{saveMessage}</div>
        )}
      </div>

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

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="font-semibold text-gray-800 mb-4">支持的数据源</h2>
        <div className="space-y-2">
          {[
            { name: 'arXiv', desc: '预印本', key: '无需', limit: '无' },
            { name: 'Semantic Scholar', desc: '论文与引用关系', key: '可选', limit: '100 req/5min' },
            { name: 'OpenAlex', desc: '开放学术元数据', key: '无需', limit: '100k req/day' },
            { name: 'CrossRef', desc: 'DOI 元数据', key: '无需', limit: '50 req/s' },
            { name: 'Google Scholar', desc: '广覆盖检索', key: '需代理', limit: '易被封' },
          ].map((src) => (
            <div key={src.name} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
              <div>
                <span className="font-medium text-sm text-gray-800">{src.name}</span>
                <span className="text-xs text-gray-400 ml-2">{src.desc}</span>
              </div>
              <div className="text-xs text-gray-500">Key: {src.key} | 限制: {src.limit}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
