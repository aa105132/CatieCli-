import { createContext, useContext, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import api from "./api";
import Announcement from "./components/Announcement";
import Admin from "./pages/Admin";
import AnthropicCredentials from "./pages/AnthropicCredentials";
import AntigravityCredentials from "./pages/AntigravityCredentials";
import AntigravityOAuth from "./pages/AntigravityOAuth";
import Credentials from "./pages/Credentials";
import Dashboard from "./pages/Dashboard";
import ErrorMessages from "./pages/ErrorMessages";
import Login from "./pages/Login";
import OAuth from "./pages/OAuth";
import Register from "./pages/Register";
import Settings from "./pages/Settings";
import Stats from "./pages/Stats";
import Tutorial from "./pages/Tutorial";

// 认证上下文
export const AuthContext = createContext(null);

// 主题上下文
export const ThemeContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}

export function useTheme() {
  return useContext(ThemeContext);
}

function ProtectedRoute({ children, adminOnly = false }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" />;
  }

  if (adminOnly && !user.is_admin) {
    return <Navigate to="/dashboard" />;
  }

  return children;
}

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // 主题状态 - 默认为夜间模式
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem("theme");
    return saved || "dark"; // 默认夜间模式
  });

  // 初始化主题
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "dark") {
      root.classList.add("dark");
      document.body.classList.add("dark");
    } else {
      root.classList.remove("dark");
      document.body.classList.remove("dark");
    }
    localStorage.setItem("theme", theme);
  }, [theme]);

  // 切换主题
  const toggleTheme = () => {
    setTheme(prev => prev === "dark" ? "light" : "dark");
  };

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) {
      api
        .get("/api/auth/me")
        .then((res) => setUser(res.data))
        .catch(() => localStorage.removeItem("token"))
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = (token, userData) => {
    localStorage.setItem("token", token);
    setUser(userData);
  };

  const logout = () => {
    localStorage.removeItem("token");
    setUser(null);
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      <AuthContext.Provider value={{ user, login, logout, loading }}>
        <BrowserRouter>
          <Announcement />
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <Dashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin"
              element={
                <ProtectedRoute adminOnly>
                  <Admin />
                </ProtectedRoute>
              }
            />
            <Route
              path="/oauth"
              element={
                <ProtectedRoute>
                  <OAuth />
                </ProtectedRoute>
              }
            />
            <Route
              path="/credentials"
              element={
                <ProtectedRoute>
                  <Credentials />
                </ProtectedRoute>
              }
            />
            <Route
              path="/antigravity-credentials"
              element={
                <ProtectedRoute>
                  <AntigravityCredentials />
                </ProtectedRoute>
              }
            />
            <Route
              path="/antigravity-oauth"
              element={
                <ProtectedRoute>
                  <AntigravityOAuth />
                </ProtectedRoute>
              }
            />
            <Route
              path="/stats"
              element={
                <ProtectedRoute adminOnly>
                  <Stats />
                </ProtectedRoute>
              }
            />
            <Route
              path="/settings"
              element={
                <ProtectedRoute adminOnly>
                  <Settings />
                </ProtectedRoute>
              }
            />
            <Route
              path="/error-messages"
              element={
                <ProtectedRoute adminOnly>
                  <ErrorMessages />
                </ProtectedRoute>
              }
            />
            <Route
              path="/tutorial"
              element={
                <ProtectedRoute>
                  <Tutorial />
                </ProtectedRoute>
              }
            />
            <Route
              path="/anthropic-credentials"
              element={
                <ProtectedRoute>
                  <AnthropicCredentials />
                </ProtectedRoute>
              }
            />
            <Route path="/" element={<Navigate to="/dashboard" />} />
          </Routes>
        </BrowserRouter>
      </AuthContext.Provider>
    </ThemeContext.Provider>
  );
}

export default App;
