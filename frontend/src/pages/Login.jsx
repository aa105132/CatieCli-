import { Eye, EyeOff, Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../api'
import { useAuth, useTheme } from '../App'

// 太极图标组件 - 支持日间/夜间模式
const TaijiIcon = ({ className = "w-8 h-8", darkMode = false }) => (
  <svg viewBox="0 0 1024 1024" className={className} fill="currentColor">
    <path d="M803.4816 515.84c-1.9968 159.2576-131.712 287.744-291.456 287.744S222.5664 675.0976 220.5696 515.84c-0.0256-1.2544-0.0512-2.5088-0.0512-3.7632 0-80.4864 65.2544-145.7664 145.7408-145.7664s145.7664 65.28 145.7664 145.7664 65.2544 145.7664 145.7664 145.7664 143.6928-63.2576 145.6896-142.0032z" />
    <path d="M366.2592 512.1024m-43.8016 0a43.8016 43.8016 0 1 0 87.6032 0 43.8016 43.8016 0 1 0-87.6032 0Z" fill={darkMode ? "#1c1814" : "#f5efe0"} />
    <path d="M220.5184 508.16c1.9968-159.2576 131.712-287.744 291.456-287.744s289.4592 128.4864 291.456 287.744c0.0256 1.2544 0.0512 2.5088 0.0512 3.7632 0 80.4864-65.2544 145.7664-145.7408 145.7664s-145.7664-65.28-145.7664-145.7664-65.2544-145.7664-145.7664-145.7664-143.6928 63.2576-145.6896 142.0032z" fill={darkMode ? "#1c1814" : "#f5efe0"} />
    <path d="M657.7408 511.8976m-43.8016 0a43.8016 43.8016 0 1 0 87.6032 0 43.8016 43.8016 0 1 0-87.6032 0Z" />
  </svg>
);

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [discordEnabled, setDiscordEnabled] = useState(false)
  const { login } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()

  // 检查 Discord 登录是否启用
  useEffect(() => {
    api.get('/api/auth/discord/config').then(res => {
      setDiscordEnabled(res.data.enabled)
    }).catch(() => {})

    // 监听 Discord 登录回调
    const handleMessage = (event) => {
      if (event.data?.type === 'discord_login') {
        login(event.data.token, event.data.user)
        navigate('/dashboard')
      }
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [login, navigate])

  const handleDiscordLogin = async () => {
    try {
      const res = await api.get('/api/auth/discord/login')
      window.open(res.data.url, 'discord_login', 'width=500,height=700')
    } catch (err) {
      setError('Discord 登录不可用')
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const res = await api.post('/api/auth/login', { username, password })
      login(res.data.access_token, res.data.user)
      navigate('/dashboard')
    } catch (err) {
      setError(err.response?.data?.detail || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 parchment-wash dark:night-wash bg-parchment-200 dark:bg-night-200">
      {/* 主题切换按钮 */}
      <button
        onClick={toggleTheme}
        className="fixed top-4 right-4 p-2 text-inkbrown-300 dark:text-sand-400 hover:text-goldenrod-500 dark:hover:text-goldenrod-400 bg-parchment-100 dark:bg-night-100 border border-parchment-400 dark:border-night-50 rounded-md transition-all z-10"
        title={theme === "dark" ? "切换到日间模式" : "切换到夜间模式"}
      >
        {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
      </button>
      
      <div className="w-full max-w-md">
        {/* Logo - 支持暗色模式，加大图标 */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-parchment-300 dark:bg-night-50 mb-4 parchment-glow">
            <TaijiIcon className="w-14 h-14 text-inkbrown-500 dark:text-sand-200" darkMode={theme === "dark"} />
          </div>
          <h1 className="text-3xl font-bold text-inkbrown-600 dark:text-sand-100">同尘</h1>
          <p className="text-inkbrown-300 dark:text-sand-400 mt-2">Gemini API 多用户代理服务</p>
        </div>

        {/* 登录卡片 - 支持暗色模式 */}
        <div className="card parchment-border dark:bg-night-100 dark:border-night-50">
          <h2 className="text-xl font-semibold mb-6 text-center text-inkbrown-500 dark:text-sand-200">登录账户</h2>

          {error && (
            <div className="bg-cinnabar-100 dark:bg-cinnabar-600/20 border border-cinnabar-300 dark:border-cinnabar-500/50 text-cinnabar-600 dark:text-cinnabar-400 px-4 py-3 rounded-lg mb-4">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-inkbrown-400 dark:text-sand-300 mb-2">
                用户名
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-4 py-3 bg-parchment-50 dark:bg-night-50 border border-parchment-400 dark:border-night-50 rounded-lg text-inkbrown-500 dark:text-sand-200 placeholder-inkbrown-200 dark:placeholder-sand-500"
                placeholder="请输入用户名"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-inkbrown-400 dark:text-sand-300 mb-2">
                密码
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-3 bg-parchment-50 dark:bg-night-50 border border-parchment-400 dark:border-night-50 rounded-lg text-inkbrown-500 dark:text-sand-200 placeholder-inkbrown-200 dark:placeholder-sand-500 pr-12"
                  placeholder="请输入密码"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-inkbrown-300 dark:text-sand-500 hover:text-inkbrown-500 dark:hover:text-sand-300"
                >
                  {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 flex items-center justify-center rounded-lg font-medium transition-all bg-cinnabar-500 hover:bg-cinnabar-600 text-white dark:bg-goldenrod-500 dark:hover:bg-goldenrod-600 dark:text-night-200 disabled:opacity-70 disabled:cursor-not-allowed"
            >
              {loading ? (
                <span className="animate-spin rounded-full h-5 w-5 border-b-2 border-current"></span>
              ) : (
                '登录'
              )}
            </button>
          </form>

          {/* Discord 登录 */}
          {discordEnabled && (
            <>
              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-parchment-400 dark:border-night-50"></div>
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-4 bg-parchment-100 dark:bg-night-100 text-inkbrown-300 dark:text-sand-400">或</span>
                </div>
              </div>
              
              <button
                type="button"
                onClick={handleDiscordLogin}
                className="w-full py-3 bg-[#5865F2] hover:bg-[#4752C4] text-white rounded-lg font-medium flex items-center justify-center gap-2 transition-colors"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
                </svg>
                使用 Discord 登录
              </button>
            </>
          )}

          <p className="text-center text-inkbrown-300 dark:text-sand-400 mt-6">
            还没有账号？{' '}
            <Link to="/register" className="text-cinnabar-500 hover:text-cinnabar-600 dark:text-cinnabar-400 dark:hover:text-cinnabar-300">
              立即注册
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
