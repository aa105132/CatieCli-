import {
  Activity,
  BarChart2,
  Check,
  CheckCircle,
  Copy,
  Download,
  ExternalLink,
  Gift,
  Github,
  HelpCircle,
  Key,
  LogOut,
  RefreshCcw,
  RefreshCw,
  Rocket,
  Server,
  Settings,
  Shield,
  Trash2,
  Users,
  X,
  Zap,
  AlertCircle,
  Info,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "../api";
import { useAuth } from "../App";
import { useWebSocket } from "../hooks/useWebSocket";

// 太极图标组件
const TaijiIcon = ({ className = "w-8 h-8" }) => (
  <svg viewBox="0 0 1024 1024" className={className} fill="currentColor">
    <path d="M803.4816 515.84c-1.9968 159.2576-131.712 287.744-291.456 287.744S222.5664 675.0976 220.5696 515.84c-0.0256-1.2544-0.0512-2.5088-0.0512-3.7632 0-80.4864 65.2544-145.7664 145.7408-145.7664s145.7664 65.28 145.7664 145.7664 65.2544 145.7664 145.7664 145.7664 143.6928-63.2576 145.6896-142.0032z" />
    <path d="M366.2592 512.1024m-43.8016 0a43.8016 43.8016 0 1 0 87.6032 0 43.8016 43.8016 0 1 0-87.6032 0Z" fill="#1e1e2e" />
    <path d="M220.5184 508.16c1.9968-159.2576 131.712-287.744 291.456-287.744s289.4592 128.4864 291.456 287.744c0.0256 1.2544 0.0512 2.5088 0.0512 3.7632 0 80.4864-65.2544 145.7664-145.7408 145.7664s-145.7664-65.28-145.7664-145.7664-65.2544-145.7664-145.7664-145.7664-143.6928 63.2576-145.6896 142.0032z" fill="#1e1e2e" />
    <path d="M657.7408 511.8976m-43.8016 0a43.8016 43.8016 0 1 0 87.6032 0 43.8016 43.8016 0 1 0-87.6032 0Z" />
  </svg>
);

export default function Dashboard() {
  const { user, logout } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [userInfo, setUserInfo] = useState(null);
  const [oauthMessage, setOauthMessage] = useState(null);
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [helpLink, setHelpLink] = useState(null);
  const [anthropicEnabled, setAnthropicEnabled] = useState(false);

  // API Key 相关
  const [myKey, setMyKey] = useState(null);
  const [keyLoading, setKeyLoading] = useState(false);
  const [keyCopied, setKeyCopied] = useState(false);

  // 凭证管理相关
  const [myCredentials, setMyCredentials] = useState([]);
  const [credLoading, setCredLoading] = useState(false);
  const [verifyResult, setVerifyResult] = useState(null);
  const [forceDonate, setForceDonate] = useState(false);
  const [rpmConfig, setRpmConfig] = useState({ base: 5, contributor: 10 });
  const [allowExportCredentials, setAllowExportCredentials] = useState(true);

  // Antigravity 凭证相关
  const [agyCredentials, setAgyCredentials] = useState([]);
  const [agyCredLoading, setAgyCredLoading] = useState(false);
  const [agyStats, setAgyStats] = useState(null);
  const [agyQuotaResult, setAgyQuotaResult] = useState(null);
  const [agyLoadingQuota, setAgyLoadingQuota] = useState(null);
  const [agyVerifyResult, setAgyVerifyResult] = useState(null);
  const [agyVerifying, setAgyVerifying] = useState(null);
  const [agyMessage, setAgyMessage] = useState({ type: "", text: "" });
  const [exportModal, setExportModal] = useState(null);

  // 文件上传相关
  const [cliUploading, setCliUploading] = useState(false);
  const [cliUploadResult, setCliUploadResult] = useState(null);
  const [agyUploading, setAgyUploading] = useState(false);
  const [agyUploadResult, setAgyUploadResult] = useState(null);
  const cliFileInputRef = useRef(null);
  const agyFileInputRef = useRef(null);

  // 获取捐赠配置
  useEffect(() => {
    api
      .get("/api/manage/public-config")
      .then((res) => {
        setForceDonate(res.data.force_donate || false);
        setRpmConfig({
          base: res.data.base_rpm || 5,
          contributor: res.data.contributor_rpm || 10,
        });
        // 默认为 true，如果后端返回 false 则禁用导出
        setAllowExportCredentials(res.data.allow_export_credentials !== false);
      })
      .catch(() => {});
  }, []);

  // 处理 OAuth 回调消息
  useEffect(() => {
    const oauth = searchParams.get("oauth");
    if (oauth === "success") {
      setOauthMessage({ type: "success", text: "凭证上传成功！" });
      setSearchParams({});
    } else if (oauth === "error") {
      const msg = searchParams.get("msg") || "未知错误";
      setOauthMessage({ type: "error", text: `凭证获取失败: ${msg}` });
      setSearchParams({});
    }
  }, [searchParams, setSearchParams]);

  // WebSocket 实时更新
  const handleWsMessage = useCallback((data) => {
    if (data.type === "stats_update" || data.type === "log_update") {
      api
        .get("/api/auth/me")
        .then((res) => setUserInfo(res.data))
        .catch(() => {});
      fetchStats();
    }
  }, []);

  const { connected } = useWebSocket(handleWsMessage);

  // 获取公共统计
  const fetchStats = async () => {
    try {
      const res = await api.get("/api/public/stats");
      setStats(res.data);
    } catch (err) {
      // 忽略
    }
  };

  useEffect(() => {
    setStatsLoading(true);
    Promise.all([
      api.get("/api/auth/me").catch(() => null),
      api.get("/api/public/stats").catch(() => null),
      api.get("/api/manage/public-config").catch(() => null),
    ])
      .then(([meRes, statsRes, configRes]) => {
        if (meRes?.data) setUserInfo(meRes.data);
        if (statsRes?.data) setStats(statsRes.data);

        if (
          configRes?.data?.tutorial_enabled &&
          configRes?.data?.tutorial_force_first_visit
        ) {
          const hasReadTutorial = localStorage.getItem("hasReadTutorial");
          if (!hasReadTutorial) {
            window.location.href = "/tutorial";
            return;
          }
        }

        if (configRes?.data?.tutorial_enabled) {
          setHelpLink({
            url: "/tutorial",
            text: configRes.data.help_link_text || "使用教程",
            isInternal: true,
          });
        } else if (
          configRes?.data?.help_link_enabled &&
          configRes?.data?.help_link_url
        ) {
          setHelpLink({
            url: configRes.data.help_link_url,
            text: configRes.data.help_link_text || "使用教程",
            isInternal: false,
          });
        }
        if (configRes?.data?.anthropic_enabled) {
          setAnthropicEnabled(true);
        }
      })
      .finally(() => setStatsLoading(false));
  }, []);

  // 获取或创建 API Key
  const fetchOrCreateKey = async () => {
    setKeyLoading(true);
    try {
      const res = await api.get("/api/auth/api-keys");
      if (res.data.length > 0) {
        setMyKey(res.data[0]);
      } else {
        const createRes = await api.post("/api/auth/api-keys", {
          name: "default",
        });
        setMyKey({ key: createRes.data.key, name: "default" });
      }
    } catch (err) {
      console.error("获取Key失败", err);
    } finally {
      setKeyLoading(false);
    }
  };

  const copyKey = async () => {
    if (myKey?.key) {
      try {
        await navigator.clipboard.writeText(myKey.key);
      } catch {
        const textarea = document.createElement("textarea");
        textarea.value = myKey.key;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      setKeyCopied(true);
      setTimeout(() => setKeyCopied(false), 2000);
    }
  };

  const [regenerating, setRegenerating] = useState(false);
  const regenerateKey = async () => {
    if (!myKey?.id) return;
    if (!confirm("确定要重新生成 API 密钥吗？旧密钥将立即失效！")) return;
    setRegenerating(true);
    try {
      const res = await api.post(`/api/auth/api-keys/${myKey.id}/regenerate`);
      setMyKey({ ...myKey, key: res.data.key });
      alert("密钥已重新生成！");
    } catch (err) {
      alert("重新生成失败: " + (err.response?.data?.detail || err.message));
    } finally {
      setRegenerating(false);
    }
  };

  // 凭证管理函数
  const fetchMyCredentials = async () => {
    setCredLoading(true);
    try {
      const res = await api.get("/api/auth/credentials");
      setMyCredentials(res.data);
    } catch (err) {
      console.error("获取凭证失败", err);
    } finally {
      setCredLoading(false);
    }
  };

  const deleteCred = async (id) => {
    if (!confirm("确定删除此凭证？")) return;
    try {
      await api.delete(`/api/auth/credentials/${id}`);
      fetchMyCredentials();
    } catch (err) {
      console.error("删除失败", err);
    }
  };

  const exportCred = async (id, email) => {
    try {
      const res = await api.get(`/api/auth/credentials/${id}/export`);
      const blob = new Blob([JSON.stringify(res.data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `credential_${email || id}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert("导出失败: " + (err.response?.data?.detail || err.message));
    }
  };

  const [verifyingCred, setVerifyingCred] = useState(null);
  const verifyCred = async (id, email) => {
    setVerifyingCred(id);
    try {
      const res = await api.post(`/api/auth/credentials/${id}/verify`);
      setVerifyResult({ ...res.data, email });
      fetchMyCredentials();
    } catch (err) {
      setVerifyResult({
        error: err.response?.data?.detail || err.message,
        is_valid: false,
        email,
      });
    } finally {
      setVerifyingCred(null);
    }
  };

  // ========== Antigravity 相关函数 ==========
  const fetchAgyCredentials = async () => {
    setAgyCredLoading(true);
    try {
      const res = await api.get("/api/antigravity/credentials");
      setAgyCredentials(res.data);
    } catch (err) {
      setAgyMessage({ type: "error", text: "获取凭证失败" });
    } finally {
      setAgyCredLoading(false);
    }
  };

  const fetchAgyStats = async () => {
    try {
      const res = await api.get("/api/antigravity/stats");
      setAgyStats(res.data);
    } catch (err) {
      console.error("获取统计失败", err);
    }
  };

  const toggleAgyActive = async (id, currentActive) => {
    try {
      await api.patch(`/api/antigravity/credentials/${id}`, null, {
        params: { is_active: !currentActive },
      });
      fetchAgyCredentials();
    } catch (err) {
      setAgyMessage({ type: "error", text: "操作失败" });
    }
  };

  const deleteAgyCred = async (id) => {
    if (!confirm("确定删除此凭证？此操作不可恢复！")) return;
    try {
      await api.delete(`/api/antigravity/credentials/${id}`);
      setAgyMessage({ type: "success", text: "删除成功" });
      fetchAgyCredentials();
      fetchAgyStats();
    } catch (err) {
      setAgyMessage({ type: "error", text: "删除失败" });
    }
  };

  const exportAgyCred = async (format = "full") => {
    if (!exportModal) return;
    const { id, email } = exportModal;
    try {
      const res = await api.get(`/api/antigravity/credentials/${id}/export`, {
        params: { format },
      });
      const blob = new Blob([JSON.stringify(res.data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download =
        format === "simple"
          ? `simple_${email || id}.json`
          : `antigravity_${email || id}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setAgyMessage({ type: "success", text: "凭证已导出！" });
      setExportModal(null);
    } catch (err) {
      setAgyMessage({
        type: "error",
        text: "导出失败: " + (err.response?.data?.detail || err.message),
      });
    }
  };

  const verifyAgyCred = async (id, email) => {
    setAgyVerifying(id);
    try {
      const res = await api.post(`/api/antigravity/credentials/${id}/verify`);
      setAgyVerifyResult({ ...res.data, email });
      fetchAgyCredentials();
    } catch (err) {
      setAgyVerifyResult({
        error: err.response?.data?.detail || err.message,
        is_valid: false,
        email,
      });
    } finally {
      setAgyVerifying(null);
    }
  };

  const fetchAgyQuota = async (id, email) => {
    setAgyLoadingQuota(id);
    try {
      const res = await api.get(`/api/antigravity/credentials/${id}/quota`);
      setAgyQuotaResult({ ...res.data, email });
    } catch (err) {
      setAgyQuotaResult({
        success: false,
        error: err.response?.data?.detail || err.message,
        email,
      });
    } finally {
      setAgyLoadingQuota(null);
    }
  };

  const deleteAllAgyInactive = async () => {
    if (!confirm("确定删除所有失效的凭证？此操作不可恢复！"))
      return;
    try {
      const res = await api.delete(
        "/api/antigravity/credentials/inactive/batch",
      );
      setAgyMessage({ type: "success", text: res.data.message });
      fetchAgyCredentials();
      fetchAgyStats();
    } catch (err) {
      setAgyMessage({
        type: "error",
        text: err.response?.data?.detail || "删除失败",
      });
    }
  };

  // ========== CLI 文件上传 ==========
  const handleCliFileUpload = async (event) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    setCliUploading(true);
    setCliUploadResult(null);

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append("files", files[i]);
    }
    formData.append("is_public", forceDonate ? "true" : "false");

    try {
      const res = await api.post("/api/auth/credentials/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setCliUploadResult({
        type: "success",
        message: `成功上传 ${res.data.uploaded_count}/${res.data.total_count} 个凭证`,
        results: res.data.results,
      });
      fetchMyCredentials();
    } catch (err) {
      setCliUploadResult({
        type: "error",
        message: err.response?.data?.detail || "上传失败",
      });
    } finally {
      setCliUploading(false);
      if (cliFileInputRef.current) {
        cliFileInputRef.current.value = "";
      }
    }
  };

  // ========== AGY 文件上传 ==========
  const handleAgyFileUpload = async (event) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    setAgyUploading(true);
    setAgyUploadResult(null);

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append("files", files[i]);
    }
    formData.append("is_public", forceDonate ? "true" : "false");

    try {
      const res = await api.post("/api/antigravity/credentials/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setAgyUploadResult({
        type: "success",
        message: `成功上传 ${res.data.uploaded_count}/${res.data.total_count} 个凭证`,
        results: res.data.results,
      });
      fetchAgyCredentials();
      fetchAgyStats();
    } catch (err) {
      setAgyUploadResult({
        type: "error",
        message: err.response?.data?.detail || "上传失败",
      });
    } finally {
      setAgyUploading(false);
      if (agyFileInputRef.current) {
        agyFileInputRef.current.value = "";
      }
    }
  };

  // ========== 导出所有凭证 ==========
  const exportAllCliCredentials = async () => {
    try {
      const res = await api.get("/api/auth/credentials/export-all");
      const blob = new Blob([JSON.stringify(res.data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cli_credentials_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert("导出失败: " + (err.response?.data?.detail || err.message));
    }
  };

  const exportAllAgyCredentials = async () => {
    try {
      const res = await api.get("/api/antigravity/credentials/export-all");
      const blob = new Blob([JSON.stringify(res.data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `agy_credentials_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert("导出失败: " + (err.response?.data?.detail || err.message));
    }
  };

  // 主标签页状态：cli, antigravity, apikey
  const [mainTab, setMainTab] = useState("cli");

  const apiEndpoint = `${window.location.origin}/v1`;

  // 自动获取 API Key
  useEffect(() => {
    fetchOrCreateKey();
  }, []);

  // 当切换标签时加载数据
  useEffect(() => {
    if (mainTab === "antigravity" && agyCredentials.length === 0) {
      fetchAgyCredentials();
      fetchAgyStats();
    }
    if (mainTab === "cli" && myCredentials.length === 0) {
      fetchMyCredentials();
    }
  }, [mainTab]);

  return (
    <div className="min-h-screen" style={{ background: '#12121a', color: '#d4d4dc' }}>
      {/* 顶部导航 */}
      <header className="border-b" style={{ borderColor: '#2a2a3a', background: '#18181f' }}>
        <div className="max-w-5xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <TaijiIcon className="w-9 h-9 text-violet-400" />
              <span className="text-lg font-semibold text-violet-300">同尘</span>
              {connected && (
                <span className="flex items-center gap-1 text-xs text-emerald-400">
                  <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse"></span>
                  实时
                </span>
              )}
            </div>
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-400 hidden sm:inline">
                {user?.discord_name || user?.username}
              </span>
              <button
                onClick={logout}
                className="px-3 py-1.5 text-sm text-gray-400 hover:text-red-400 bg-gray-800/50 hover:bg-red-500/10 border border-gray-700 hover:border-red-500/50 rounded-md transition-all"
              >
                <LogOut size={14} className="inline mr-1" />
                登出
              </button>
            </div>
          </div>
          
          {/* 管理员链接 */}
          {user?.is_admin && (
            <div className="flex items-center gap-4 mt-2 pt-2 border-t border-gray-800 text-xs">
              <Link to="/stats" className="text-gray-500 hover:text-violet-400 flex items-center gap-1 transition-colors">
                <Activity size={12} /> 统计
              </Link>
              <Link to="/settings" className="text-gray-500 hover:text-violet-400 flex items-center gap-1 transition-colors">
                <Settings size={12} /> 设置
              </Link>
              <Link to="/admin" className="text-gray-500 hover:text-violet-400 flex items-center gap-1 transition-colors">
                <Users size={12} /> 用户
              </Link>
            </div>
          )}
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-4 py-5">
        {/* OAuth 消息提示 */}
        {oauthMessage && (
          <div className={`mb-4 p-3 rounded-lg border text-sm ${
            oauthMessage.type === "success"
              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
              : "bg-red-500/10 border-red-500/30 text-red-400"
          }`}>
            <div className="flex items-center justify-between">
              <span>{oauthMessage.text}</span>
              <button onClick={() => setOauthMessage(null)} className="text-gray-400 hover:text-white">
                <X size={14} />
              </button>
            </div>
          </div>
        )}

        {/* 标签页导航 - 更明显的按钮样式 */}
        <div className="flex gap-2 mb-5">
          <button
            onClick={() => setMainTab("cli")}
            className={`flex-1 px-4 py-3 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2 border ${
              mainTab === "cli"
                ? "bg-violet-600/20 text-violet-300 border-violet-500/50 shadow-lg shadow-violet-500/10"
                : "bg-gray-800/30 text-gray-400 border-gray-700/50 hover:bg-gray-800/50 hover:text-gray-300 hover:border-gray-600"
            }`}
          >
            <Server size={18} />
            CLI
          </button>
          <button
            onClick={() => setMainTab("antigravity")}
            className={`flex-1 px-4 py-3 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2 border ${
              mainTab === "antigravity"
                ? "bg-amber-600/20 text-amber-300 border-amber-500/50 shadow-lg shadow-amber-500/10"
                : "bg-gray-800/30 text-gray-400 border-gray-700/50 hover:bg-gray-800/50 hover:text-gray-300 hover:border-gray-600"
            }`}
          >
            <Rocket size={18} />
            反重力
          </button>
          <button
            onClick={() => setMainTab("apikey")}
            className={`flex-1 px-4 py-3 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2 border ${
              mainTab === "apikey"
                ? "bg-rose-600/20 text-rose-300 border-rose-500/50 shadow-lg shadow-rose-500/10"
                : "bg-gray-800/30 text-gray-400 border-gray-700/50 hover:bg-gray-800/50 hover:text-gray-300 hover:border-gray-600"
            }`}
          >
            <Key size={18} />
            密钥
          </button>
        </div>

        {/* ========== CLI 标签页 ========== */}
        {mainTab === "cli" && (
          <div className="space-y-5">
            {/* 使用提示卡片 */}
            <div className="rounded-lg border p-4" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-lg bg-violet-500/10">
                  <Info size={20} className="text-violet-400" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-medium text-gray-200 mb-2">CLI 使用说明</h3>
                  <ul className="text-xs text-gray-400 space-y-1.5">
                    <li className="flex items-start gap-2">
                      <span className="text-violet-400 mt-0.5">1.</span>
                      <span>CLI 凭证用于调用 Gemini 模型（Flash / 2.5 Pro / 3.0）</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-violet-400 mt-0.5">2.</span>
                      <span>上传凭证后可获得更高的调用配额</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-violet-400 mt-0.5">3.</span>
                      <span>API 端点：<code className="px-1.5 py-0.5 rounded bg-gray-800 text-violet-300">{apiEndpoint}</code></span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-violet-400 mt-0.5">4.</span>
                      <span>支持上传 JSON 凭证文件（格式：access_token, refresh_token, client_id, client_secret, project_id）</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            {/* 统计卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-4 rounded-lg border" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
                <div className="text-2xl font-bold text-cyan-400">{userInfo?.usage_by_model?.flash?.used || 0}</div>
                <div className="text-xs text-gray-500 mt-1">Flash 用量</div>
                <div className="text-xs text-gray-600">/ {userInfo?.usage_by_model?.flash?.quota || 0}</div>
              </div>
              <div className="p-4 rounded-lg border" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
                <div className="text-2xl font-bold text-amber-400">{userInfo?.usage_by_model?.pro25?.used || 0}</div>
                <div className="text-xs text-gray-500 mt-1">2.5 Pro 用量</div>
                <div className="text-xs text-gray-600">/ {userInfo?.usage_by_model?.pro25?.quota || 0}</div>
              </div>
              <div className="p-4 rounded-lg border" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
                <div className="text-2xl font-bold text-pink-400">{userInfo?.usage_by_model?.pro30?.used || 0}</div>
                <div className="text-xs text-gray-500 mt-1">3.0 用量</div>
                <div className="text-xs text-gray-600">/ {userInfo?.usage_by_model?.pro30?.quota || 0}</div>
              </div>
              <div className="p-4 rounded-lg border" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
                <div className="text-2xl font-bold text-emerald-400">{userInfo?.credential_count || 0}</div>
                <div className="text-xs text-gray-500 mt-1">有效凭证</div>
              </div>
            </div>

            {/* 凭证列表 */}
            <div className="rounded-lg border" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
              <div className="p-4 border-b flex items-center justify-between flex-wrap gap-2" style={{ borderColor: '#2a2a3a' }}>
                <h3 className="text-sm font-medium text-gray-200 flex items-center gap-2">
                  <Shield size={16} className="text-violet-400" />
                  CLI 凭证 ({myCredentials.length})
                </h3>
                <div className="flex gap-2 flex-wrap">
                  {myCredentials.some((c) => !c.is_active) && (
                    <button
                      onClick={async () => {
                        if (!confirm("确定删除所有失效凭证？")) return;
                        try {
                          const res = await api.delete("/api/auth/credentials/inactive/batch");
                          alert(res.data.message);
                          fetchMyCredentials();
                        } catch (err) {
                          alert(err.response?.data?.detail || "删除失败");
                        }
                      }}
                      className="text-xs px-3 py-1.5 text-red-400 bg-red-500/10 border border-red-500/30 rounded-md hover:bg-red-500/20 transition-all"
                    >
                      清理失效
                    </button>
                  )}
                  <Link
                    to="/oauth"
                    className="text-xs px-3 py-1.5 text-violet-300 bg-violet-500/20 border border-violet-500/30 rounded-md hover:bg-violet-500/30 transition-all"
                  >
                    获取凭证
                  </Link>
                  <button
                    onClick={() => cliFileInputRef.current?.click()}
                    disabled={cliUploading}
                    className="text-xs px-3 py-1.5 text-emerald-300 bg-emerald-500/20 border border-emerald-500/30 rounded-md hover:bg-emerald-500/30 transition-all flex items-center gap-1"
                  >
                    <Upload size={12} />
                    {cliUploading ? "上传中..." : "上传"}
                  </button>
                  {myCredentials.length > 0 && allowExportCredentials && (
                    <button
                      onClick={exportAllCliCredentials}
                      className="text-xs px-3 py-1.5 text-cyan-300 bg-cyan-500/20 border border-cyan-500/30 rounded-md hover:bg-cyan-500/30 transition-all flex items-center gap-1"
                    >
                      <Download size={12} />
                      导出全部
                    </button>
                  )}
                  <input
                    ref={cliFileInputRef}
                    type="file"
                    accept=".json,.zip"
                    multiple
                    onChange={handleCliFileUpload}
                    className="hidden"
                  />
                </div>
              </div>

              {/* CLI 上传结果提示 */}
              {cliUploadResult && (
                <div className={`mx-3 mt-3 p-3 rounded-lg border text-sm ${
                  cliUploadResult.type === "success"
                    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                    : "bg-red-500/10 border-red-500/30 text-red-400"
                }`}>
                  <div className="flex items-center justify-between mb-2">
                    <span>{cliUploadResult.message}</span>
                    <button onClick={() => setCliUploadResult(null)} className="text-gray-400 hover:text-white">
                      <X size={14} />
                    </button>
                  </div>
                  {cliUploadResult.results && (
                    <div className="text-xs space-y-1 max-h-32 overflow-y-auto">
                      {cliUploadResult.results.map((r, i) => (
                        <div key={i} className={`${r.status === 'success' ? 'text-emerald-400' : r.status === 'error' ? 'text-red-400' : r.status === 'skip' ? 'text-yellow-400' : 'text-gray-400'}`}>
                          {r.filename}: {r.message}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              
              <div className="p-3 max-h-[350px] overflow-y-auto">
                {credLoading ? (
                  <div className="text-center py-8 text-gray-500 text-sm">
                    <RefreshCw className="animate-spin mx-auto mb-2" size={20} />
                    加载中...
                  </div>
                ) : myCredentials.length === 0 ? (
                  <div className="text-center py-8 text-gray-500 text-sm">
                    暂无凭证，点击上方按钮获取或上传
                  </div>
                ) : (
                  <div className="space-y-2">
                    {myCredentials.map((cred) => (
                      <div
                        key={cred.id}
                        className="p-3 rounded-lg border flex items-center justify-between"
                        style={{ background: '#16161e', borderColor: '#252530' }}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-gray-300 truncate">{cred.email || cred.name}</div>
                          <div className="flex items-center gap-2 mt-1">
                            <span className={`text-xs px-1.5 py-0.5 rounded ${cred.is_active ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                              {cred.is_active ? '启用' : '禁用'}
                            </span>
                            {cred.model_tier === "3" && (
                              <span className="text-xs px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-400">3.0</span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => verifyCred(cred.id, cred.email)}
                            disabled={verifyingCred === cred.id}
                            className="p-2 text-cyan-400 hover:bg-cyan-400/10 rounded-md transition-all"
                            title="检测"
                          >
                            {verifyingCred === cred.id ? <RefreshCw size={14} className="animate-spin" /> : <CheckCircle size={14} />}
                          </button>
                          {allowExportCredentials && (
                            <button
                              onClick={() => exportCred(cred.id, cred.email)}
                              className="p-2 text-violet-400 hover:bg-violet-400/10 rounded-md transition-all"
                              title="导出"
                            >
                              <Download size={14} />
                            </button>
                          )}
                          <button
                            onClick={() => deleteCred(cred.id)}
                            className="p-2 text-red-400 hover:bg-red-400/10 rounded-md transition-all"
                            title="删除"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ========== 反重力标签页 ========== */}
        {mainTab === "antigravity" && (
          <div className="space-y-5">
            {/* 使用提示卡片 */}
            <div className="rounded-lg border p-4" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-lg bg-amber-500/10">
                  <Rocket size={20} className="text-amber-400" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-medium text-gray-200 mb-2">反重力 使用说明</h3>
                  <ul className="text-xs text-gray-400 space-y-1.5">
                    <li className="flex items-start gap-2">
                      <span className="text-amber-400 mt-0.5">1.</span>
                      <span>反重力凭证用于调用 Claude、Gemini 等多种模型</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-amber-400 mt-0.5">2.</span>
                      <span>与 CLI 凭证<strong className="text-amber-400">独立</strong>，需单独获取</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-amber-400 mt-0.5">3.</span>
                      <span>API 端点：<code className="px-1.5 py-0.5 rounded bg-gray-800 text-amber-300">{window.location.origin}/agy/v1</code></span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-amber-400 mt-0.5">4.</span>
                      <span>支持上传 JSON 凭证文件（格式：access_token, refresh_token, client_id, client_secret, project_id）</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            {/* 统计卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-4 rounded-lg border" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
                <div className="text-2xl font-bold text-amber-400">{userInfo?.usage_by_provider?.claude || 0}</div>
                <div className="text-xs text-gray-500 mt-1">Claude 调用</div>
              </div>
              <div className="p-4 rounded-lg border" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
                <div className="text-2xl font-bold text-blue-400">{userInfo?.usage_by_provider?.gemini || 0}</div>
                <div className="text-xs text-gray-500 mt-1">Gemini 调用</div>
              </div>
              <div className="p-4 rounded-lg border" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
                <div className="text-2xl font-bold text-orange-400">{userInfo?.usage_by_api_type?.antigravity || 0}</div>
                <div className="text-xs text-gray-500 mt-1">AGY 总调用</div>
              </div>
              <div className="p-4 rounded-lg border" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
                <div className="text-2xl font-bold text-emerald-400">{agyStats?.user_active || 0}</div>
                <div className="text-xs text-gray-500 mt-1">有效凭证</div>
              </div>
            </div>

            {/* 消息提示 */}
            {agyMessage.text && (
              <div className={`p-3 rounded-lg border text-sm ${
                agyMessage.type === "success"
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                  : "bg-red-500/10 border-red-500/30 text-red-400"
              }`}>
                {agyMessage.text}
              </div>
            )}

            {/* 凭证列表 */}
            <div className="rounded-lg border" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
              <div className="p-4 border-b flex items-center justify-between flex-wrap gap-2" style={{ borderColor: '#2a2a3a' }}>
                <h3 className="text-sm font-medium text-gray-200 flex items-center gap-2">
                  <Rocket size={16} className="text-amber-400" />
                  反重力凭证 ({agyCredentials.length})
                </h3>
                <div className="flex gap-2 flex-wrap">
                  {agyCredentials.some((c) => !c.is_active) && (
                    <button
                      onClick={deleteAllAgyInactive}
                      className="text-xs px-3 py-1.5 text-red-400 bg-red-500/10 border border-red-500/30 rounded-md hover:bg-red-500/20 transition-all"
                    >
                      清理失效
                    </button>
                  )}
                  <Link
                    to="/antigravity-oauth"
                    className="text-xs px-3 py-1.5 text-amber-300 bg-amber-500/20 border border-amber-500/30 rounded-md hover:bg-amber-500/30 transition-all"
                  >
                    获取凭证
                  </Link>
                  <button
                    onClick={() => agyFileInputRef.current?.click()}
                    disabled={agyUploading}
                    className="text-xs px-3 py-1.5 text-emerald-300 bg-emerald-500/20 border border-emerald-500/30 rounded-md hover:bg-emerald-500/30 transition-all flex items-center gap-1"
                  >
                    <Upload size={12} />
                    {agyUploading ? "上传中..." : "上传"}
                  </button>
                  {agyCredentials.length > 0 && allowExportCredentials && (
                    <button
                      onClick={exportAllAgyCredentials}
                      className="text-xs px-3 py-1.5 text-cyan-300 bg-cyan-500/20 border border-cyan-500/30 rounded-md hover:bg-cyan-500/30 transition-all flex items-center gap-1"
                    >
                      <Download size={12} />
                      导出全部
                    </button>
                  )}
                  <input
                    ref={agyFileInputRef}
                    type="file"
                    accept=".json,.zip"
                    multiple
                    onChange={handleAgyFileUpload}
                    className="hidden"
                  />
                  <button
                    onClick={() => { fetchAgyCredentials(); fetchAgyStats(); }}
                    className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-700/50 rounded-md transition-all"
                    title="刷新"
                  >
                    <RefreshCw size={14} />
                  </button>
                </div>
              </div>

              {/* AGY 上传结果提示 */}
              {agyUploadResult && (
                <div className={`mx-3 mt-3 p-3 rounded-lg border text-sm ${
                  agyUploadResult.type === "success"
                    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                    : "bg-red-500/10 border-red-500/30 text-red-400"
                }`}>
                  <div className="flex items-center justify-between mb-2">
                    <span>{agyUploadResult.message}</span>
                    <button onClick={() => setAgyUploadResult(null)} className="text-gray-400 hover:text-white">
                      <X size={14} />
                    </button>
                  </div>
                  {agyUploadResult.results && (
                    <div className="text-xs space-y-1 max-h-32 overflow-y-auto">
                      {agyUploadResult.results.map((r, i) => (
                        <div key={i} className={`${r.status === 'success' ? 'text-emerald-400' : r.status === 'error' ? 'text-red-400' : r.status === 'skip' ? 'text-yellow-400' : 'text-gray-400'}`}>
                          {r.filename}: {r.message}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              
              <div className="p-3 max-h-[350px] overflow-y-auto">
                {agyCredLoading ? (
                  <div className="text-center py-8 text-gray-500 text-sm">
                    <RefreshCw className="animate-spin mx-auto mb-2" size={20} />
                    加载中...
                  </div>
                ) : agyCredentials.length === 0 ? (
                  <div className="text-center py-8 text-gray-500 text-sm">
                    暂无凭证，点击上方按钮获取或上传
                  </div>
                ) : (
                  <div className="space-y-2">
                    {agyCredentials.map((cred, index) => (
                      <div
                        key={cred.id}
                        className="p-3 rounded-lg border"
                        style={{ background: '#16161e', borderColor: '#252530' }}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className={`text-xs px-1.5 py-0.5 rounded ${cred.is_active ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                                {cred.is_active ? '启用' : '禁用'}
                              </span>
                              <span className="text-xs px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400">AGY</span>
                              <span className="text-xs text-gray-600">#{index + 1}</span>
                            </div>
                            {cred.project_id && (
                              <div className="text-xs text-emerald-400/80 font-mono truncate">{cred.project_id}</div>
                            )}
                            <div className="text-sm text-gray-400 truncate">{cred.email || cred.name}</div>
                          </div>
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => fetchAgyQuota(cred.id, cred.email || cred.name)}
                              disabled={agyLoadingQuota === cred.id || !cred.is_active}
                              className="p-2 text-cyan-400 hover:bg-cyan-400/10 rounded-md disabled:opacity-50 transition-all"
                              title="详情"
                            >
                              {agyLoadingQuota === cred.id ? <RefreshCw size={14} className="animate-spin" /> : <BarChart2 size={14} />}
                            </button>
                            <button
                              onClick={() => toggleAgyActive(cred.id, cred.is_active)}
                              className={`p-2 rounded-md transition-all ${cred.is_active ? 'text-amber-400 hover:bg-amber-400/10' : 'text-emerald-400 hover:bg-emerald-400/10'}`}
                              title={cred.is_active ? "禁用" : "启用"}
                            >
                              {cred.is_active ? <X size={14} /> : <Check size={14} />}
                            </button>
                            <button
                              onClick={() => deleteAgyCred(cred.id)}
                              className="p-2 text-red-400 hover:bg-red-400/10 rounded-md transition-all"
                              title="删除"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ========== API密钥标签页 ========== */}
        {mainTab === "apikey" && (
          <div className="space-y-5">
            {/* 使用提示卡片 */}
            <div className="rounded-lg border p-4" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-lg bg-rose-500/10">
                  <Key size={20} className="text-rose-400" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-medium text-gray-200 mb-2">API 密钥说明</h3>
                  <ul className="text-xs text-gray-400 space-y-1.5">
                    <li className="flex items-start gap-2">
                      <span className="text-rose-400 mt-0.5">1.</span>
                      <span>此密钥用于调用 CLI 和反重力 API</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-rose-400 mt-0.5">2.</span>
                      <span>请妥善保管，不要泄露给他人</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-rose-400 mt-0.5">3.</span>
                      <span>如需更换可点击「更换」按钮重新生成</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            {/* API 密钥卡片 */}
            <div className="rounded-lg border" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
              <div className="p-4 border-b" style={{ borderColor: '#2a2a3a' }}>
                <h3 className="text-sm font-medium text-gray-200 flex items-center gap-2">
                  <Key size={16} className="text-rose-400" />
                  API 密钥
                </h3>
              </div>
              
              <div className="p-4">
                {keyLoading ? (
                  <div className="text-center py-8 text-gray-500 text-sm">
                    <RefreshCw className="animate-spin mx-auto mb-2" size={20} />
                    加载中...
                  </div>
                ) : myKey ? (
                  <div className="space-y-4">
                    <div className="p-3 rounded-lg border" style={{ background: '#16161e', borderColor: '#252530' }}>
                      <code className="block text-violet-300 text-sm font-mono break-all">{myKey.key}</code>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={copyKey}
                        className="flex-1 px-4 py-2.5 bg-violet-600/20 text-violet-300 border border-violet-500/30 rounded-lg hover:bg-violet-600/30 flex items-center justify-center gap-2 text-sm transition-all"
                      >
                        {keyCopied ? <Check size={16} /> : <Copy size={16} />}
                        {keyCopied ? "已复制" : "复制"}
                      </button>
                      <button
                        onClick={regenerateKey}
                        disabled={regenerating}
                        className="flex-1 px-4 py-2.5 bg-amber-600/20 text-amber-300 border border-amber-500/30 rounded-lg hover:bg-amber-600/30 disabled:opacity-50 flex items-center justify-center gap-2 text-sm transition-all"
                      >
                        <RefreshCcw size={16} className={regenerating ? "animate-spin" : ""} />
                        更换
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8 text-red-400 text-sm">
                    获取失败，请刷新重试
                  </div>
                )}
              </div>
            </div>

            {/* 端点信息 */}
            <div className="rounded-lg border" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
              <div className="p-4 border-b" style={{ borderColor: '#2a2a3a' }}>
                <h3 className="text-sm font-medium text-gray-200">API 端点</h3>
              </div>
              <div className="p-4 space-y-3">
                <div>
                  <div className="text-xs text-gray-500 mb-1.5">CLI 端点</div>
                  <code className="block p-2.5 rounded-lg text-sm text-violet-300 font-mono" style={{ background: '#16161e' }}>
                    {apiEndpoint}
                  </code>
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-1.5">反重力端点</div>
                  <code className="block p-2.5 rounded-lg text-sm text-amber-300 font-mono" style={{ background: '#16161e' }}>
                    {window.location.origin}/agy/v1
                  </code>
                </div>
              </div>
            </div>

            {/* 使用说明 */}
            <div className="rounded-lg border" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
              <div className="p-4 border-b" style={{ borderColor: '#2a2a3a' }}>
                <h3 className="text-sm font-medium text-gray-200">在 SillyTavern 中使用</h3>
              </div>
              <div className="p-4 text-sm text-gray-400">
                <ol className="space-y-2 list-decimal list-inside">
                  <li>打开 SillyTavern 连接设置</li>
                  <li>选择 <span className="text-violet-300">兼容OpenAI</span> 或 <span className="text-violet-300">Gemini反代</span></li>
                  <li>填入上方 API 端点和密钥</li>
                  <li>选择模型：gemini-3.0-flash / gemini-3.0-pro</li>
                </ol>
              </div>
            </div>

            {/* 提示 */}
            {!userInfo?.has_public_credentials && (
              <div className="p-4 rounded-lg border flex items-start gap-3" style={{ background: 'rgba(245,158,11,0.05)', borderColor: 'rgba(245,158,11,0.2)' }}>
                <AlertCircle size={18} className="text-amber-400 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-sm text-amber-400">
                    未上传凭证，调用频率限制为 {rpmConfig.base} 次/分钟
                  </div>
                  <div className="text-xs text-amber-400/70 mt-1">
                    上传凭证可提升至 {rpmConfig.contributor} 次/分钟
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 底部 */}
      <footer className="border-t py-4 mt-8" style={{ borderColor: '#2a2a3a', background: '#18181f' }}>
        <div className="max-w-5xl mx-auto px-4 text-center">
          <a
            href="https://github.com/mzrodyu/CatieCli"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-gray-500 hover:text-violet-400 flex items-center justify-center gap-2 transition-colors"
          >
            <Github size={14} />
            改自：https://github.com/mzrodyu/CatieCli
          </a>
        </div>
      </footer>

      {/* ========== 弹窗 ========== */}

      {/* 导出格式选择 */}
      {exportModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 backdrop-blur-sm">
          <div className="rounded-lg p-5 max-w-sm w-full mx-4 border" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
            <h3 className="text-base font-medium mb-3 text-gray-200">导出格式</h3>
            <p className="text-xs text-gray-500 mb-4">{exportModal.email}</p>
            <div className="space-y-2">
              <button
                onClick={() => exportAgyCred("full")}
                className="w-full p-3 rounded-lg text-left bg-violet-500/10 text-violet-300 border border-violet-500/30 hover:bg-violet-500/20 transition-all"
              >
                <div className="text-sm font-medium">完整格式</div>
                <div className="text-xs text-violet-300/60 mt-1">包含全部字段</div>
              </button>
              <button
                onClick={() => exportAgyCred("simple")}
                className="w-full p-3 rounded-lg text-left bg-amber-500/10 text-amber-300 border border-amber-500/30 hover:bg-amber-500/20 transition-all"
              >
                <div className="text-sm font-medium">简化格式</div>
                <div className="text-xs text-amber-300/60 mt-1">仅 email + refresh_token</div>
              </button>
            </div>
            <button
              onClick={() => setExportModal(null)}
              className="w-full mt-3 p-2.5 rounded-lg text-sm text-gray-400 hover:text-white bg-gray-800/50 border border-gray-700 hover:border-gray-600 transition-all"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* CLI 检测结果 */}
      {verifyResult && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 backdrop-blur-sm">
          <div className="rounded-lg w-full max-w-md mx-4 border overflow-hidden" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
            <div className="p-4 border-b flex items-center justify-between" style={{ borderColor: '#2a2a3a' }}>
              <h3 className="text-base font-medium flex items-center gap-2 text-gray-200">
                <CheckCircle className={verifyResult.is_valid ? "text-emerald-400" : "text-red-400"} size={18} />
                检测结果
              </h3>
              <button onClick={() => setVerifyResult(null)} className="text-gray-400 hover:text-white">
                <X size={16} />
              </button>
            </div>
            <div className="p-4 space-y-3">
              <div className="text-sm text-gray-400">{verifyResult.email}</div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">状态</span>
                <span className={`text-xs px-2 py-0.5 rounded ${verifyResult.is_valid ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                  {verifyResult.is_valid ? "有效" : "无效"}
                </span>
              </div>
              {verifyResult.error && (
                <div className="p-3 rounded-lg border text-xs text-red-400" style={{ background: 'rgba(239,68,68,0.1)', borderColor: 'rgba(239,68,68,0.2)' }}>
                  {verifyResult.error}
                </div>
              )}
            </div>
            <div className="p-4 border-t flex justify-end" style={{ borderColor: '#2a2a3a' }}>
              <button onClick={() => setVerifyResult(null)} className="px-4 py-2 text-sm text-gray-300 hover:text-white bg-gray-700/50 border border-gray-600 rounded-lg transition-all">
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AGY 检测结果 */}
      {agyVerifyResult && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 backdrop-blur-sm">
          <div className="rounded-lg w-full max-w-md mx-4 border overflow-hidden" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
            <div className="p-4 border-b flex items-center justify-between" style={{ borderColor: '#2a2a3a' }}>
              <h3 className="text-base font-medium flex items-center gap-2 text-gray-200">
                <CheckCircle className={agyVerifyResult.is_valid ? "text-emerald-400" : "text-red-400"} size={18} />
                检测结果
              </h3>
              <button onClick={() => setAgyVerifyResult(null)} className="text-gray-400 hover:text-white">
                <X size={16} />
              </button>
            </div>
            <div className="p-4 space-y-3">
              <div className="text-sm text-gray-400">{agyVerifyResult.email}</div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">状态</span>
                <span className={`text-xs px-2 py-0.5 rounded ${agyVerifyResult.is_valid ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                  {agyVerifyResult.is_valid ? "有效" : "无效"}
                </span>
              </div>
              {agyVerifyResult.project_id && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">Project ID</span>
                  <span className="text-xs px-2 py-0.5 rounded bg-amber-500/20 text-amber-400 truncate max-w-[180px]">
                    {agyVerifyResult.project_id}
                  </span>
                </div>
              )}
              {agyVerifyResult.error && (
                <div className="p-3 rounded-lg border text-xs text-red-400" style={{ background: 'rgba(239,68,68,0.1)', borderColor: 'rgba(239,68,68,0.2)' }}>
                  {agyVerifyResult.error}
                </div>
              )}
            </div>
            <div className="p-4 border-t flex justify-end" style={{ borderColor: '#2a2a3a' }}>
              <button onClick={() => setAgyVerifyResult(null)} className="px-4 py-2 text-sm text-gray-300 hover:text-white bg-gray-700/50 border border-gray-600 rounded-lg transition-all">
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AGY 额度弹窗 */}
      {agyQuotaResult && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 backdrop-blur-sm">
          <div className="rounded-lg w-full max-w-lg mx-4 border overflow-hidden" style={{ background: '#1e1e28', borderColor: '#2a2a3a' }}>
            <div className="p-4 border-b flex items-center justify-between" style={{ borderColor: '#2a2a3a' }}>
              <h3 className="text-base font-medium flex items-center gap-2 text-amber-400">
                <BarChart2 size={18} />
                额度详情
              </h3>
              <button onClick={() => setAgyQuotaResult(null)} className="text-gray-400 hover:text-white">
                <X size={16} />
              </button>
            </div>
            <div className="p-4">
              <div className="text-xs text-gray-500 mb-4">{agyQuotaResult.filename || agyQuotaResult.email}</div>
              {agyQuotaResult.success ? (
                <div className="space-y-4">
                  {/* 模型配额列表 */}
                  {Object.entries(agyQuotaResult.models || {}).length > 0 ? (
                    <div className="grid grid-cols-1 gap-3">
                      {Object.entries(agyQuotaResult.models).map(([modelId, quota]) => {
                        // 解析模型名称
                        const modelNames = {
                          'gemini-2.5-flash-thinking': 'Flash Thinking',
                          'gemini-2.5-pro': '2.5 Pro',
                          'gemini-3.0-pro': '3.0 Pro',
                          'chat_23310': 'Claude',
                        };
                        const displayName = modelNames[modelId] || modelId.replace(/-/g, ' ').replace('gemini ', '').trim();
                        const remaining = quota.remaining || 0;
                        const used = Math.round(100 - remaining);
                        const resetTime = quota.resetTime;
                        
                        // 根据剩余量确定颜色
                        const getColor = (rem) => {
                          if (rem >= 70) return 'text-emerald-400';
                          if (rem >= 30) return 'text-amber-400';
                          return 'text-red-400';
                        };
                        
                        return (
                          <div key={modelId} className="p-3 rounded-lg border" style={{ background: '#16161e', borderColor: '#252530' }}>
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-sm text-gray-300 font-medium">{displayName}</span>
                              {resetTime && resetTime !== 'N/A' && (
                                <span className="text-xs text-gray-500">重置: {resetTime}</span>
                              )}
                            </div>
                            <div className="flex items-baseline gap-2">
                              <span className={`text-2xl font-bold ${getColor(remaining)}`}>
                                {used}%
                              </span>
                              <span className="text-gray-500 text-sm">/ 100%</span>
                              <span className={`text-xs ml-auto ${getColor(remaining)}`}>
                                剩余 {remaining}%
                              </span>
                            </div>
                            {/* 进度条 */}
                            <div className="mt-2 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                              <div
                                className={`h-full transition-all ${remaining >= 70 ? 'bg-emerald-500' : remaining >= 30 ? 'bg-amber-500' : 'bg-red-500'}`}
                                style={{ width: `${remaining}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="text-center py-6 text-gray-500 text-sm">
                      暂无配额数据
                    </div>
                  )}
                </div>
              ) : (
                <div className="p-3 rounded-lg border text-sm text-red-400" style={{ background: 'rgba(239,68,68,0.1)', borderColor: 'rgba(239,68,68,0.2)' }}>
                  {agyQuotaResult.error || "获取失败"}
                </div>
              )}
            </div>
            <div className="p-4 border-t flex justify-end" style={{ borderColor: '#2a2a3a' }}>
              <button onClick={() => setAgyQuotaResult(null)} className="px-4 py-2 text-sm text-gray-300 hover:text-white bg-gray-700/50 border border-gray-600 rounded-lg transition-all">
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
