import { AlertTriangle, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import api from '../api'

export default function Announcement() {
  const [announcement, setAnnouncement] = useState(null)
  const [show, setShow] = useState(false)
  const [countdown, setCountdown] = useState(0)
  const [canClose, setCanClose] = useState(false)

  useEffect(() => {
    // 检查是否已经阅读过（用 localStorage 存储）
    const lastReadTime = localStorage.getItem('announcement_read_time')
    const lastReadContent = localStorage.getItem('announcement_read_content')
    
    fetchAnnouncement(lastReadContent)
  }, [])

  const fetchAnnouncement = async (lastReadContent) => {
    try {
      const res = await api.get('/api/manage/announcement')
      if (res.data.enabled) {
        // 如果内容变了，重新显示
        const contentHash = btoa(encodeURIComponent(res.data.title + res.data.content))
        if (lastReadContent !== contentHash) {
          setAnnouncement(res.data)
          setShow(true)
          setCountdown(res.data.read_seconds || 5)
          setCanClose(false)
        }
      }
    } catch (err) {
      // 忽略错误
    }
  }

  useEffect(() => {
    if (show && countdown > 0) {
      const timer = setTimeout(() => {
        setCountdown(countdown - 1)
      }, 1000)
      return () => clearTimeout(timer)
    } else if (countdown === 0 && show) {
      setCanClose(true)
    }
  }, [countdown, show])

  const handleClose = () => {
    if (!canClose) return
    
    // 记录已阅读
    const contentHash = btoa(encodeURIComponent(announcement.title + announcement.content))
    localStorage.setItem('announcement_read_time', Date.now().toString())
    localStorage.setItem('announcement_read_content', contentHash)
    setShow(false)
  }

  if (!show || !announcement) return null

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-dark-800 border border-dark-600 rounded-2xl max-w-2xl w-full max-h-[80vh] flex flex-col shadow-2xl">
        {/* 标题栏 */}
        <div className="flex items-center justify-between p-4 border-b border-dark-600">
          <div className="flex items-center gap-2 text-amber-400">
            <AlertTriangle size={20} />
            <span className="text-sm font-medium">公告</span>
          </div>
          <button
            onClick={handleClose}
            disabled={!canClose}
            className={`p-1 rounded ${canClose ? 'hover:bg-dark-700 text-gray-400' : 'text-gray-600 cursor-not-allowed'}`}
          >
            <X size={20} />
          </button>
        </div>

        {/* 标题 */}
        <div className="px-6 pt-4">
          <h2 className="text-xl font-bold text-white">{announcement.title}</h2>
          {!canClose && (
            <p className="text-amber-400 text-sm mt-1">
              请仔细阅读，{countdown} 秒后可关闭
            </p>
          )}
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          <div 
            className="prose prose-invert prose-sm max-w-none text-gray-300 whitespace-pre-wrap"
            style={{ lineHeight: '1.8' }}
          >
            {announcement.content}
          </div>
        </div>

        {/* 底部 */}
        <div className="p-4 border-t border-dark-600 flex items-center justify-between">
          <span className="text-gray-500 text-sm">
            {canClose ? '已阅读，可以关闭' : `阅读中... ${countdown}s`}
          </span>
          <button
            onClick={handleClose}
            disabled={!canClose}
            className={`px-6 py-2 rounded-lg font-medium transition-colors ${
              canClose 
                ? 'bg-blue-600 hover:bg-blue-700 text-white' 
                : 'bg-dark-700 text-gray-500 cursor-not-allowed'
            }`}
          >
            {canClose ? '我已阅读' : `${countdown}s`}
          </button>
        </div>
      </div>
    </div>
  )
}
