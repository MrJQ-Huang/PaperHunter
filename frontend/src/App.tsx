import { Routes, Route, Link, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import PaperList from './pages/PaperList'
import Settings from './pages/Settings'
import { BookOpen, LayoutDashboard, Settings as SettingsIcon, Sparkles } from 'lucide-react'

function App() {
  const location = useLocation()

  const navItems = [
    { path: '/', label: '任务', icon: LayoutDashboard },
    { path: '/papers', label: '论文库', icon: BookOpen },
    { path: '/settings', label: '设置', icon: SettingsIcon },
  ]

  return (
    <div className="min-h-screen flex flex-col bg-[#fafafa]">
      {/* 顶部导航 */}
      <header className="bg-white/80 backdrop-blur border-b border-gray-100 sticky top-0 z-40">
        <div className="max-w-screen-2xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-xl bg-gradient-to-br from-violet-500 to-purple-500 flex items-center justify-center shadow-sm shadow-violet-200/40">
              <Sparkles size={14} className="text-white" />
            </div>
            <span className="text-sm font-bold text-gray-800">PaperHunter</span>
          </div>
          <nav className="flex items-center gap-0.5 bg-gray-50 rounded-xl p-0.5">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    isActive
                      ? 'bg-white text-violet-600 shadow-sm'
                      : 'text-gray-400 hover:text-gray-600'
                  }`}
                >
                  <Icon size={13} />
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
