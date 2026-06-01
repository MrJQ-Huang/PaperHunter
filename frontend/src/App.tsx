import { Routes, Route, Link, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import PaperList from './pages/PaperList'
import Settings from './pages/Settings'
import { BookOpen, LayoutDashboard, Settings as SettingsIcon } from 'lucide-react'

function App() {
  const location = useLocation()

  const navItems = [
    { path: '/', label: '任务监控', icon: LayoutDashboard },
    { path: '/papers', label: '论文库', icon: BookOpen },
    { path: '/settings', label: '设置', icon: SettingsIcon },
  ]

  return (
    <div className="min-h-screen flex flex-col">
      {/* 顶部导航 */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-screen-2xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-xl font-bold text-primary-600">PaperHunter</span>
            <span className="text-sm text-gray-400">论文搜索 Agent 团队</span>
          </div>
          <nav className="flex items-center gap-1">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-primary-50 text-primary-600'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  <Icon size={16} />
                  {item.label}
                </Link>
              )
            })}
          </nav>
        </div>
      </header>

      {/* 主内容 */}
      <main className="flex-1 max-w-screen-2xl mx-auto w-full px-4 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/papers" element={<PaperList />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
