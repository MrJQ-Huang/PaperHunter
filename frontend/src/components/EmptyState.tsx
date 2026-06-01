import { Sparkles } from 'lucide-react'

interface Props {
  onSelectTopic: (topic: string) => void
}

const topics = [
  { text: 'transformer NLP 应用', emoji: '🤖' },
  { text: '时域天线测量 探头补偿', emoji: '📡' },
  { text: 'deep learning 医学影像', emoji: '🏥' },
  { text: 'ROS2 机器人导航', emoji: '🤖' },
  { text: '量子计算 纠错', emoji: '⚛️' },
]

export default function EmptyState({ onSelectTopic }: Props) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 pb-8 select-none">
      {/* Logo */}
      <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-violet-100 to-purple-100 flex items-center justify-center mb-5 shadow-lg shadow-violet-200/30">
        <Sparkles size={32} className="text-violet-500" />
      </div>

      <h2 className="text-lg font-bold text-gray-800 mb-1.5">PaperHunter</h2>
      <p className="text-sm text-gray-400 mb-8 text-center max-w-xs leading-relaxed">
        告诉我你的研究方向<br />我帮你从全球学术数据库搜索论文
      </p>

      {/* 推荐主题 */}
      <div className="w-full max-w-sm">
        <p className="text-[11px] text-gray-300 mb-3 text-center font-medium uppercase tracking-wider">试试这些</p>
        <div className="flex flex-wrap justify-center gap-2">
          {topics.map((t) => (
            <button
              key={t.text}
              onClick={() => onSelectTopic(t.text)}
              className="flex items-center gap-1.5 px-3.5 py-2 text-xs bg-white border border-gray-100 text-gray-600 rounded-2xl hover:border-violet-200 hover:bg-violet-50 hover:text-violet-600 transition-all shadow-sm hover:shadow-md hover:shadow-violet-100/40 active:scale-95"
            >
              <span>{t.emoji}</span>
              {t.text}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
