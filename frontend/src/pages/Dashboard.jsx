import {
  Activity,
  BarChart2,
  Check,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Code,
  Copy,
  Download,
  ExternalLink,
  Gift,
  Github,
  Globe,
  Lock,
  HelpCircle,
  Key,
  LogOut,
  Moon,
  RefreshCcw,
  RefreshCw,
  Rocket,
  Server,
  Settings,
  Shield,
  Sun,
  Trash2,
  Users,
  X,
  Zap,
  AlertCircle,
  AlertTriangle,
  Info,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "../api";
import { useAuth, useTheme } from "../App";
import { useWebSocket } from "../hooks/useWebSocket";

// 太极图标组件 - 支持日间/夜间模式
const TaijiIcon = ({ className = "w-8 h-8", darkMode = false }) => (
  <svg viewBox="0 0 1024 1024" className={className} fill="currentColor">
    <path d="M803.4816 515.84c-1.9968 159.2576-131.712 287.744-291.456 287.744S222.5664 675.0976 220.5696 515.84c-0.0256-1.2544-0.0512-2.5088-0.0512-3.7632 0-80.4864 65.2544-145.7664 145.7408-145.7664s145.7664 65.28 145.7664 145.7664 65.2544 145.7664 145.7664 145.7664 143.6928-63.2576 145.6896-142.0032z" />
    <path d="M366.2592 512.1024m-43.8016 0a43.8016 43.8016 0 1 0 87.6032 0 43.8016 43.8016 0 1 0-87.6032 0Z" fill={darkMode ? "#1c1814" : "#f5efe0"} />
    <path d="M220.5184 508.16c1.9968-159.2576 131.712-287.744 291.456-287.744s289.4592 128.4864 291.456 287.744c0.0256 1.2544 0.0512 2.5088 0.0512 3.7632 0 80.4864-65.2544 145.7664-145.7408 145.7664s-145.7664-65.28-145.7664-145.7664-65.2544-145.7664-145.7664-145.7664-143.6928 63.2576-145.6896 142.0032z" fill={darkMode ? "#1c1814" : "#f5efe0"} />
    <path d="M657.7408 511.8976m-43.8016 0a43.8016 43.8016 0 1 0 87.6032 0 43.8016 43.8016 0 1 0-87.6032 0Z" />
  </svg>
);

export default function Dashboard() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
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

  // Antigravity 额度预览相关
  const [agyExpandedQuota, setAgyExpandedQuota] = useState(null);
  const [agyQuotaCache, setAgyQuotaCache] = useState({});
  const [agyLoadingQuotaPreview, setAgyLoadingQuotaPreview] = useState(null);

  // Codex 凭证相关
  const [codexCredentials, setCodexCredentials] = useState([]);
  const [codexCredLoading, setCodexCredLoading] = useState(false);
  const [codexStats, setCodexStats] = useState(null);
  const [codexMessage, setCodexMessage] = useState({ type: "", text: "" });
  const [codexVerifying, setCodexVerifying] = useState(null);
  const [codexRefreshing, setCodexRefreshing] = useState(null);
  const [codexOauthState, setCodexOauthState] = useState(null);
  const [codexCallbackUrl, setCodexCallbackUrl] = useState("");
  const [codexIsPublic, setCodexIsPublic] = useState(false);
  const [codexProcessing, setCodexProcessing] = useState(false);
  const [codexUploading, setCodexUploading] = useState(false);
  const codexFileInputRef = useRef(null);
  
  // Codex 配额预览相关
  const [codexExpandedQuota, setCodexExpandedQuota] = useState(null);
  const [codexQuotaCache, setCodexQuotaCache] = useState({});
  const [codexLoadingQuotaPreview, setCodexLoadingQuotaPreview] = useState(null);

  // 文件上传相关
  const [cliUploading, setCliUploading] = useState(false);
  const [cliUploadResult, setCliUploadResult] = useState(null);
  const [agyUploading, setAgyUploading] = useState(false);
  const [agyUploadResult, setAgyUploadResult] = useState(null);
  const cliFileInputRef = useRef(null);
  const agyFileInputRef = useRef(null);

  // Antigravity 配置
  const [agyPoolMode, setAgyPoolMode] = useState("private");
  const [agyQuotaEnabled, setAgyQuotaEnabled] = useState(false);

  // 奖励配置（从后端获取）
  const [rewardConfig, setRewardConfig] = useState({
    // CLI 奖励
    quota_flash: 1000,
    quota_25pro: 500,
    quota_30pro: 200,
    contributor_rpm: 10,
    // Antigravity 奖励
    antigravity_quota_per_cred: 500,
    antigravity_contributor_rpm: 10,
    // Banana 奖励
    banana_quota_enabled: true,
    banana_quota_per_cred: 50,
  });

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
        setAllowExportCredentials(res.data.allow_export_credentials !== false);
        setAgyPoolMode(res.data.antigravity_pool_mode || "private");
        setAgyQuotaEnabled(res.data.antigravity_quota_enabled || false);
        // 设置奖励配置
        setRewardConfig({
          quota_flash: res.data.quota_flash || 1000,
          quota_25pro: res.data.quota_25pro || 500,
          quota_30pro: res.data.quota_30pro || 200,
          contributor_rpm: res.data.contributor_rpm || 10,
          antigravity_quota_per_cred: res.data.antigravity_quota_per_cred || 500,
          antigravity_contributor_rpm: res.data.antigravity_contributor_rpm || 10,
          banana_quota_enabled: res.data.banana_quota_enabled !== false,
          banana_quota_per_cred: res.data.banana_quota_per_cred || 50,
        });
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

  // CLI 凭证切换公开状态
  const toggleCliPublic = async (id, currentPublic) => {
    try {
      await api.patch(`/api/auth/credentials/${id}`, null, {
        params: { is_public: !currentPublic },
      });
      fetchMyCredentials();
      const meRes = await api.get("/api/auth/me");
      if (meRes?.data) setUserInfo(meRes.data);
    } catch (err) {
      alert(err.response?.data?.detail || "操作失败");
    }
  };

  // CLI 凭证切换启用状态
  const toggleCliActive = async (id, currentActive) => {
    try {
      await api.patch(`/api/auth/credentials/${id}`, null, {
        params: { is_active: !currentActive },
      });
      fetchMyCredentials();
    } catch (err) {
      alert(err.response?.data?.detail || "操作失败");
    }
  };

  // CLI 凭证批量检测
  const [verifyingAllCli, setVerifyingAllCli] = useState(false);
  const verifyAllCliCredentials = async () => {
    if (myCredentials.length === 0) return;
    if (!confirm(`确定要检测全部 ${myCredentials.length} 个凭证？这可能需要一些时间。\n\n验证成功的凭证将自动启用。`)) return;
    
    setVerifyingAllCli(true);
    let validCount = 0;
    let invalidCount = 0;
    
    for (const cred of myCredentials) {
      try {
        const res = await api.post(`/api/auth/credentials/${cred.id}/verify`);
        // 根据API返回的 is_valid 判断凭证是否有效
        if (res.data?.is_valid) {
          validCount++;
        } else {
          invalidCount++;
        }
      } catch {
        invalidCount++;
      }
    }
    
    setVerifyingAllCli(false);
    fetchMyCredentials();
    alert(`检测完成：${validCount} 个有效（已启用），${invalidCount} 个无效`);
  };

  // CLI 凭证全部切换公开/私有
  const toggleAllCliPublic = async (setPublic) => {
    const targetCreds = myCredentials.filter(c => c.is_public !== setPublic && c.is_active);
    if (targetCreds.length === 0) {
      alert(setPublic ? "没有可以公开的凭证" : "没有可以私有化的凭证");
      return;
    }
    
    if (!confirm(`确定要将 ${targetCreds.length} 个凭证设为${setPublic ? "公开" : "私有"}？`)) return;
    
    for (const cred of targetCreds) {
      try {
        await api.patch(`/api/auth/credentials/${cred.id}`, null, {
          params: { is_public: setPublic },
        });
      } catch (err) {
        console.error("切换失败", err);
      }
    }
    
    fetchMyCredentials();
    const meRes = await api.get("/api/auth/me");
    if (meRes?.data) setUserInfo(meRes.data);
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

  const refreshAgyProjectId = async (id, email) => {
    setAgyVerifying(id);
    try {
      const res = await api.post(
        `/api/antigravity/credentials/${id}/refresh-project-id`,
      );
      setAgyVerifyResult({
        ...res.data,
        email,
        is_project_id_refresh: true,
        is_valid: res.data.success,
      });
      if (res.data.success) {
        fetchAgyCredentials();
      }
    } catch (err) {
      setAgyVerifyResult({
        error: err.response?.data?.detail || err.message,
        is_valid: false,
        email,
        is_project_id_refresh: true,
      });
    } finally {
      setAgyVerifying(null);
    }
  };

  const toggleAgyPublic = async (id, currentPublic) => {
    try {
      await api.patch(`/api/antigravity/credentials/${id}`, null, {
        params: { is_public: !currentPublic },
      });
      fetchAgyCredentials();
      const meRes = await api.get("/api/auth/me");
      if (meRes?.data) setUserInfo(meRes.data);
    } catch (err) {
      setAgyMessage({
        type: "error",
        text: err.response?.data?.detail || "操作失败",
      });
    }
  };

  // Antigravity 凭证批量检测
  const [verifyingAllAgy, setVerifyingAllAgy] = useState(false);
  const verifyAllAgyCredentials = async () => {
    if (agyCredentials.length === 0) return;
    if (!confirm(`确定要检测全部 ${agyCredentials.length} 个凭证？这可能需要一些时间。\n\n验证成功的凭证将自动启用。`)) return;
    
    setVerifyingAllAgy(true);
    let validCount = 0;
    let invalidCount = 0;
    
    for (const cred of agyCredentials) {
      try {
        const res = await api.post(`/api/antigravity/credentials/${cred.id}/verify`);
        // 根据API返回的 is_valid 判断凭证是否有效
        if (res.data?.is_valid) {
          validCount++;
        } else {
          invalidCount++;
        }
      } catch {
        invalidCount++;
      }
    }
    
    setVerifyingAllAgy(false);
    fetchAgyCredentials();
    alert(`检测完成：${validCount} 个有效（已启用），${invalidCount} 个无效`);
  };

  // Antigravity 凭证全部切换公开/私有
  const toggleAllAgyPublic = async (setPublic) => {
    const targetCreds = agyCredentials.filter(c => c.is_public !== setPublic && c.is_active);
    if (targetCreds.length === 0) {
      alert(setPublic ? "没有可以公开的凭证" : "没有可以私有化的凭证");
      return;
    }
    
    if (!confirm(`确定要将 ${targetCreds.length} 个凭证设为${setPublic ? "公开" : "私有"}？`)) return;
    
    for (const cred of targetCreds) {
      try {
        await api.patch(`/api/antigravity/credentials/${cred.id}`, null, {
          params: { is_public: setPublic },
        });
      } catch (err) {
        console.error("切换失败", err);
      }
    }
    
    fetchAgyCredentials();
    const meRes = await api.get("/api/auth/me");
    if (meRes?.data) setUserInfo(meRes.data);
  };

  // ========== Antigravity 额度预览相关函数 ==========
  const aggregateAgyQuota = (models) => {
    const result = {
      claude: { remaining: 0, count: 0, resetTime: "" },
      gemini: { remaining: 0, count: 0, resetTime: "" },
      banana: { remaining: 0, count: 0, resetTime: "" },
    };
    
    Object.entries(models).forEach(([modelId, data]) => {
      const lower = modelId.toLowerCase();
      const remaining = data.remaining || 0;
      const resetTime = data.resetTime || "";
      
      if (lower.includes("claude")) {
        result.claude.remaining += remaining;
        result.claude.count += 1;
        if (!result.claude.resetTime && resetTime) result.claude.resetTime = resetTime;
      } else if (lower.includes("gemini") || lower.includes("flash") || lower.includes("pro")) {
        if (!lower.includes("image") && !lower.includes("banana")) {
          result.gemini.remaining += remaining;
          result.gemini.count += 1;
          if (!result.gemini.resetTime && resetTime) result.gemini.resetTime = resetTime;
        }
      }
      
      if (lower.includes("image") || lower.includes("banana")) {
        result.banana.remaining += remaining;
        result.banana.count += 1;
        if (!result.banana.resetTime && resetTime) result.banana.resetTime = resetTime;
      }
    });
    
    if (result.claude.count > 0) result.claude.remaining = Math.round(result.claude.remaining / result.claude.count);
    if (result.gemini.count > 0) result.gemini.remaining = Math.round(result.gemini.remaining / result.gemini.count);
    if (result.banana.count > 0) result.banana.remaining = Math.round(result.banana.remaining / result.banana.count);
    
    return result;
  };

  const getAgyQuotaColor = (remaining) => {
    if (remaining >= 80) return { bar: "bg-jade-500", text: "text-jade-500" };
    if (remaining >= 40) return { bar: "bg-goldenrod-400", text: "text-goldenrod-400" };
    if (remaining >= 20) return { bar: "bg-goldenrod-500", text: "text-goldenrod-500" };
    return { bar: "bg-cinnabar-500", text: "text-cinnabar-500" };
  };

  const toggleAgyQuotaPreview = async (credId) => {
    if (agyExpandedQuota === credId) {
      setAgyExpandedQuota(null);
      return;
    }
    
    setAgyExpandedQuota(credId);
    
    if (!agyQuotaCache[credId]) {
      await fetchAgyQuotaPreview(credId);
    }
  };

  const fetchAgyQuotaPreview = async (credId) => {
    setAgyLoadingQuotaPreview(credId);
    try {
      const res = await api.get(`/api/antigravity/credentials/${credId}/quota`);
      if (res.data.success) {
        const models = res.data.models || {};
        const aggregated = aggregateAgyQuota(models);
        setAgyQuotaCache(prev => ({ ...prev, [credId]: aggregated }));
      } else {
        setAgyQuotaCache(prev => ({ ...prev, [credId]: { error: res.data.error || "获取失败" } }));
      }
    } catch (err) {
      setAgyQuotaCache(prev => ({ ...prev, [credId]: { error: "获取额度失败" } }));
    } finally {
      setAgyLoadingQuotaPreview(null);
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

  // ========== Codex 相关函数 ==========
  const fetchCodexCredentials = async () => {
    setCodexCredLoading(true);
    try {
      const res = await api.get("/api/codex/credentials");
      setCodexCredentials(res.data);
    } catch (err) {
      setCodexMessage({ type: "error", text: "获取凭证失败" });
    } finally {
      setCodexCredLoading(false);
    }
  };

  const fetchCodexStats = async () => {
    try {
      const res = await api.get("/api/codex/stats");
      setCodexStats(res.data);
    } catch (err) {
      console.error("获取统计失败", err);
    }
  };

  const toggleCodexActive = async (id, currentActive) => {
    try {
      await api.patch(`/api/codex/credentials/${id}`, null, {
        params: { is_active: !currentActive },
      });
      fetchCodexCredentials();
    } catch (err) {
      setCodexMessage({ type: "error", text: "操作失败" });
    }
  };

  const toggleCodexPublic = async (id, currentPublic) => {
    try {
      await api.patch(`/api/codex/credentials/${id}`, null, {
        params: { is_public: !currentPublic },
      });
      fetchCodexCredentials();
    } catch (err) {
      setCodexMessage({ type: "error", text: "操作失败" });
    }
  };

  const deleteCodexCred = async (id) => {
    if (!confirm("确定删除此凭证？此操作不可恢复！")) return;
    try {
      await api.delete(`/api/codex/credentials/${id}`);
      setCodexMessage({ type: "success", text: "删除成功" });
      fetchCodexCredentials();
      fetchCodexStats();
    } catch (err) {
      setCodexMessage({ type: "error", text: "删除失败" });
    }
  };

  const verifyCodexCred = async (id) => {
    setCodexVerifying(id);
    try {
      const res = await api.post(`/api/codex/credentials/${id}/verify`);
      if (res.data.is_valid) {
        setCodexMessage({ type: "success", text: "凭证验证有效" });
      } else {
        setCodexMessage({ type: "error", text: res.data.error || "凭证无效" });
      }
      fetchCodexCredentials();
    } catch (err) {
      setCodexMessage({ type: "error", text: err.response?.data?.detail || "验证失败" });
    } finally {
      setCodexVerifying(null);
    }
  };

  const refreshCodexToken = async (id) => {
    setCodexRefreshing(id);
    try {
      const res = await api.post(`/api/codex/credentials/${id}/refresh`);
      if (res.data.success) {
        setCodexMessage({ type: "success", text: "Token 刷新成功" });
      } else {
        setCodexMessage({ type: "error", text: res.data.error || "刷新失败" });
      }
      fetchCodexCredentials();
    } catch (err) {
      setCodexMessage({ type: "error", text: err.response?.data?.detail || "刷新失败" });
    } finally {
      setCodexRefreshing(null);
    }
  };

  // Codex OAuth 流程
  const startCodexOAuth = async () => {
    try {
      const res = await api.get("/api/codex-oauth/auth-url");
      setCodexOauthState(res.data);
      window.open(res.data.auth_url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setCodexMessage({
        type: "error",
        text: err.response?.data?.detail || "获取授权链接失败",
      });
    }
  };

  const submitCodexCallback = async () => {
    if (!codexCallbackUrl.trim()) {
      setCodexMessage({ type: "error", text: "请输入回调 URL" });
      return;
    }
    
    setCodexProcessing(true);
    try {
      const res = await api.post("/api/codex-oauth/from-callback-url", {
        callback_url: codexCallbackUrl,
        is_public: codexIsPublic,
      });
      
      setCodexMessage({ type: "success", text: res.data.message });
      setCodexOauthState(null);
      setCodexCallbackUrl("");
      fetchCodexCredentials();
      fetchCodexStats();
    } catch (err) {
      setCodexMessage({
        type: "error",
        text: err.response?.data?.detail || "处理失败",
      });
    } finally {
      setCodexProcessing(false);
    }
  };

  // Codex 文件上传
  const handleCodexFileUpload = async (event) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    setCodexUploading(true);

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append("files", files[i]);
    }
    formData.append("is_public", codexIsPublic ? "true" : "false");

    try {
      const res = await api.post("/api/codex/credentials/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setCodexMessage({
        type: "success",
        text: `成功上传 ${res.data.success_count}/${res.data.total_count} 个凭证`,
      });
      fetchCodexCredentials();
      fetchCodexStats();
    } catch (err) {
      setCodexMessage({
        type: "error",
        text: err.response?.data?.detail || "上传失败",
      });
    } finally {
      setCodexUploading(false);
      if (codexFileInputRef.current) {
        codexFileInputRef.current.value = "";
      }
    }
  };

  // ========== Codex 配额查询 ==========
  const getCodexQuotaColor = (remaining) => {
    if (remaining >= 80) return { bar: "bg-emerald-500", text: "text-emerald-500" };
    if (remaining >= 40) return { bar: "bg-goldenrod-400", text: "text-goldenrod-400" };
    if (remaining >= 20) return { bar: "bg-goldenrod-500", text: "text-goldenrod-500" };
    return { bar: "bg-cinnabar-500", text: "text-cinnabar-500" };
  };

  const toggleCodexQuotaPreview = async (credId) => {
    if (codexExpandedQuota === credId) {
      setCodexExpandedQuota(null);
      return;
    }
    
    setCodexExpandedQuota(credId);
    
    if (!codexQuotaCache[credId]) {
      await fetchCodexQuotaPreview(credId);
    }
  };

  const fetchCodexQuotaPreview = async (credId) => {
    setCodexLoadingQuotaPreview(credId);
    try {
      const res = await api.get(`/api/codex/credentials/${credId}/quota`);
      if (res.data.success) {
        setCodexQuotaCache(prev => ({ ...prev, [credId]: res.data }));
      } else {
        setCodexQuotaCache(prev => ({ ...prev, [credId]: { error: res.data.error || "获取失败" } }));
      }
    } catch (err) {
      setCodexQuotaCache(prev => ({ ...prev, [credId]: { error: "获取配额失败" } }));
    } finally {
      setCodexLoadingQuotaPreview(null);
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
    if (mainTab === "codex" && codexCredentials.length === 0) {
      fetchCodexCredentials();
      fetchCodexStats();
    }
  }, [mainTab]);

  return (
    <div className="min-h-screen bg-parchment-200 dark:bg-night-200">
      {/* 顶部导航 */}
      <header className="border-b border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
        <div className="max-w-5xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <TaijiIcon className="w-9 h-9 text-inkbrown-500 dark:text-sand-200" darkMode={theme === "dark"} />
              <span className="text-lg font-semibold text-inkbrown-500 dark:text-sand-200">同尘</span>
              {connected && (
                <span className="flex items-center gap-1 text-xs text-jade-500">
                  <span className="w-1.5 h-1.5 bg-jade-500 rounded-full animate-pulse"></span>
                  实时
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {/* 主题切换按钮 */}
              <button
                onClick={toggleTheme}
                className="p-2 text-inkbrown-300 dark:text-sand-400 hover:text-goldenrod-500 dark:hover:text-goldenrod-400 bg-parchment-200 dark:bg-night-50 border border-parchment-400 dark:border-night-50 rounded-md transition-all"
                title={theme === "dark" ? "切换到日间模式" : "切换到夜间模式"}
              >
                {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
              </button>
              <span className="text-sm text-inkbrown-300 dark:text-sand-400 hidden sm:inline">
                {user?.discord_name || user?.username}
              </span>
              <button
                onClick={logout}
                className="px-3 py-1.5 text-sm text-inkbrown-300 dark:text-sand-400 hover:text-cinnabar-500 bg-parchment-200 dark:bg-night-50 hover:bg-cinnabar-100 dark:hover:bg-cinnabar-600/20 border border-parchment-400 dark:border-night-50 hover:border-cinnabar-300 rounded-md transition-all"
              >
                <LogOut size={14} className="inline mr-1" />
                登出
              </button>
            </div>
          </div>
          
          {/* 管理员链接 */}
          {user?.is_admin && (
            <div className="flex items-center gap-4 mt-2 pt-2 border-t border-parchment-300 dark:border-night-50 text-xs">
              <Link to="/stats" className="text-inkbrown-200 dark:text-sand-500 hover:text-wisteria-500 flex items-center gap-1 transition-colors">
                <Activity size={12} /> 统计
              </Link>
              <Link to="/settings" className="text-inkbrown-200 dark:text-sand-500 hover:text-wisteria-500 flex items-center gap-1 transition-colors">
                <Settings size={12} /> 设置
              </Link>
              <Link to="/admin" className="text-inkbrown-200 dark:text-sand-500 hover:text-wisteria-500 flex items-center gap-1 transition-colors">
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
              ? "bg-jade-100 border-jade-300 text-jade-600"
              : "bg-cinnabar-100 border-cinnabar-300 text-cinnabar-600"
          }`}>
            <div className="flex items-center justify-between">
              <span>{oauthMessage.text}</span>
              <button onClick={() => setOauthMessage(null)} className="text-inkbrown-300 hover:text-inkbrown-500">
                <X size={14} />
              </button>
            </div>
          </div>
        )}

        {/* 标签页导航 */}
        <div className="flex gap-2 mb-5">
          <button
            onClick={() => setMainTab("cli")}
            className={`flex-1 px-4 py-3 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2 border ${
              mainTab === "cli"
                ? "bg-wisteria-100 dark:bg-wisteria-600/20 text-wisteria-600 dark:text-wisteria-400 border-wisteria-300 dark:border-wisteria-500/50 shadow-md"
                : "bg-parchment-100 dark:bg-night-100 text-inkbrown-300 dark:text-sand-400 border-parchment-400 dark:border-night-50 hover:bg-parchment-200 dark:hover:bg-night-50 hover:text-inkbrown-400 dark:hover:text-sand-300"
            }`}
          >
            <Server size={18} />
            CLI
          </button>
          <button
            onClick={() => setMainTab("antigravity")}
            className={`flex-1 px-4 py-3 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2 border ${
              mainTab === "antigravity"
                ? "bg-goldenrod-100 dark:bg-goldenrod-600/20 text-goldenrod-600 dark:text-goldenrod-400 border-goldenrod-300 dark:border-goldenrod-500/50 shadow-md"
                : "bg-parchment-100 dark:bg-night-100 text-inkbrown-300 dark:text-sand-400 border-parchment-400 dark:border-night-50 hover:bg-parchment-200 dark:hover:bg-night-50 hover:text-inkbrown-400 dark:hover:text-sand-300"
            }`}
          >
            <Rocket size={18} />
            反重力
          </button>
          <button
            onClick={() => setMainTab("codex")}
            className={`flex-1 px-4 py-3 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2 border ${
              mainTab === "codex"
                ? "bg-emerald-100 dark:bg-emerald-600/20 text-emerald-600 dark:text-emerald-400 border-emerald-300 dark:border-emerald-500/50 shadow-md"
                : "bg-parchment-100 dark:bg-night-100 text-inkbrown-300 dark:text-sand-400 border-parchment-400 dark:border-night-50 hover:bg-parchment-200 dark:hover:bg-night-50 hover:text-inkbrown-400 dark:hover:text-sand-300"
            }`}
          >
            <Code size={18} />
            Codex
          </button>
          <button
            onClick={() => setMainTab("apikey")}
            className={`flex-1 px-4 py-3 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2 border ${
              mainTab === "apikey"
                ? "bg-cinnabar-100 dark:bg-cinnabar-600/20 text-cinnabar-600 dark:text-cinnabar-400 border-cinnabar-300 dark:border-cinnabar-500/50 shadow-md"
                : "bg-parchment-100 dark:bg-night-100 text-inkbrown-300 dark:text-sand-400 border-parchment-400 dark:border-night-50 hover:bg-parchment-200 dark:hover:bg-night-50 hover:text-inkbrown-400 dark:hover:text-sand-300"
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
            <div className="rounded-lg border border-parchment-400 dark:border-night-50 p-4 bg-parchment-100 dark:bg-night-100">
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-lg bg-wisteria-100 dark:bg-wisteria-600/20">
                  <Info size={20} className="text-wisteria-500 dark:text-wisteria-400" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-medium text-inkbrown-500 dark:text-sand-200 mb-2">CLI 使用说明</h3>
                  <ul className="text-xs text-inkbrown-300 dark:text-sand-400 space-y-1.5">
                    <li className="flex items-start gap-2">
                      <span className="text-wisteria-500 dark:text-wisteria-400 mt-0.5">1.</span>
                      <span>CLI 凭证用于调用 Gemini 模型（Flash / 2.5 Pro / 3.0）</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-wisteria-500 dark:text-wisteria-400 mt-0.5">2.</span>
                      <span>上传凭证后可获得更高的调用配额</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-wisteria-500 dark:text-wisteria-400 mt-0.5">3.</span>
                      <span>API 端点：<code className="px-1.5 py-0.5 rounded bg-parchment-300 dark:bg-night-50 text-wisteria-600 dark:text-wisteria-400">{apiEndpoint}</code></span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-wisteria-500 dark:text-wisteria-400 mt-0.5">4.</span>
                      <span>支持上传 JSON 凭证文件（格式：access_token, refresh_token, client_id, client_secret, project_id）</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            {/* CLI 凭证奖励说明 */}
            <div className="rounded-lg border border-wisteria-300 dark:border-wisteria-500/50 p-4 bg-wisteria-50 dark:bg-wisteria-600/10">
              <h3 className="text-sm font-medium text-wisteria-600 dark:text-wisteria-400 mb-3 flex items-center gap-2">
                <Gift size={16} />
                上传 CLI 凭证额度说明
              </h3>
              <div className="space-y-2 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-wisteria-600 dark:text-wisteria-400 font-medium">上传 2.5 的有效凭证：</span>
                  <span className="text-inkbrown-400 dark:text-sand-400">每个额外增加</span>
                  <span className="px-1.5 py-0.5 rounded bg-wisteria-200 dark:bg-wisteria-600/30 text-wisteria-700 dark:text-wisteria-300 font-medium">{rewardConfig.quota_flash}</span>
                  <span className="text-inkbrown-400 dark:text-sand-400">次 Flash /</span>
                  <span className="px-1.5 py-0.5 rounded bg-wisteria-200 dark:bg-wisteria-600/30 text-wisteria-700 dark:text-wisteria-300 font-medium">{rewardConfig.quota_25pro}</span>
                  <span className="text-inkbrown-400 dark:text-sand-400">次 2.5 Pro /</span>
                  <span className="px-1.5 py-0.5 rounded bg-parchment-300 dark:bg-night-50 text-inkbrown-300 dark:text-sand-500 font-medium">0</span>
                  <span className="text-inkbrown-400 dark:text-sand-400">次 3.0 Pro</span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-wisteria-600 dark:text-wisteria-400 font-medium">上传 3.0 的有效凭证：</span>
                  <span className="text-inkbrown-400 dark:text-sand-400">每个额外增加</span>
                  <span className="px-1.5 py-0.5 rounded bg-wisteria-200 dark:bg-wisteria-600/30 text-wisteria-700 dark:text-wisteria-300 font-medium">{rewardConfig.quota_flash}</span>
                  <span className="text-inkbrown-400 dark:text-sand-400">次 Flash /</span>
                  <span className="px-1.5 py-0.5 rounded bg-wisteria-200 dark:bg-wisteria-600/30 text-wisteria-700 dark:text-wisteria-300 font-medium">{rewardConfig.quota_25pro}</span>
                  <span className="text-inkbrown-400 dark:text-sand-400">次 2.5 Pro /</span>
                  <span className="px-1.5 py-0.5 rounded bg-wisteria-200 dark:bg-wisteria-600/30 text-wisteria-700 dark:text-wisteria-300 font-medium">{rewardConfig.quota_30pro}</span>
                  <span className="text-inkbrown-400 dark:text-sand-400">次 3.0 Pro</span>
                </div>
              </div>
              {/* RPM 提示 */}
              <div className="mt-3 pt-3 border-t border-wisteria-200 dark:border-wisteria-500/30">
                <div className="flex items-center gap-2 text-xs">
                  <Zap size={14} className="text-goldenrod-500" />
                  <span className="text-inkbrown-400 dark:text-sand-400">RPM 速率：上传可用凭证（CLI 或反重力）后增加对应速率至</span>
                  <span className="px-1.5 py-0.5 rounded bg-goldenrod-200 dark:bg-goldenrod-600/30 text-goldenrod-700 dark:text-goldenrod-300 font-medium">{rewardConfig.contributor_rpm}</span>
                  <span className="text-inkbrown-400 dark:text-sand-400">RPM</span>
                </div>
              </div>
            </div>

            {/* 统计卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
                <div className="text-2xl font-bold text-indigo-500 dark:text-indigo-400">
                  {userInfo?.usage_by_model?.flash?.used || 0}
                  <span className="text-sm font-normal text-inkbrown-200 dark:text-sand-500">/{userInfo?.usage_by_model?.flash?.quota || 0}</span>
                </div>
                <div className="text-xs text-inkbrown-200 dark:text-sand-500 mt-1">Flash</div>
              </div>
              <div className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
                <div className="text-2xl font-bold text-goldenrod-500 dark:text-goldenrod-400">
                  {userInfo?.usage_by_model?.pro25?.used || 0}
                  <span className="text-sm font-normal text-inkbrown-200 dark:text-sand-500">/{userInfo?.usage_by_model?.pro25?.quota || 0}</span>
                </div>
                <div className="text-xs text-inkbrown-200 dark:text-sand-500 mt-1">2.5 Pro</div>
              </div>
              <div className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
                <div className="text-2xl font-bold text-cinnabar-500 dark:text-cinnabar-400">
                  {userInfo?.usage_by_model?.pro30?.used || 0}
                  <span className="text-sm font-normal text-inkbrown-200 dark:text-sand-500">/{userInfo?.usage_by_model?.pro30?.quota || 0}</span>
                </div>
                <div className="text-xs text-inkbrown-200 dark:text-sand-500 mt-1">3.0</div>
              </div>
              <div className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
                <div className="text-2xl font-bold text-jade-500 dark:text-jade-400">{userInfo?.credential_count || 0}</div>
                <div className="text-xs text-inkbrown-200 dark:text-sand-500 mt-1">有效凭证</div>
              </div>
              <div className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
                <div className="text-2xl font-bold text-wisteria-500 dark:text-wisteria-400">{myCredentials.filter(c => c.is_public).length}</div>
                <div className="text-xs text-inkbrown-200 dark:text-sand-500 mt-1">公开凭证</div>
              </div>
            </div>

            {/* 凭证列表 */}
            <div className="rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
              <div className="p-4 border-b border-parchment-400 dark:border-night-50 flex items-center justify-between flex-wrap gap-2">
                <h3 className="text-sm font-medium text-inkbrown-500 dark:text-sand-200 flex items-center gap-2">
                  <Shield size={16} className="text-wisteria-500 dark:text-wisteria-400" />
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
                      className="text-xs px-3 py-1.5 text-cinnabar-600 dark:text-cinnabar-400 bg-cinnabar-100 dark:bg-cinnabar-600/20 border border-cinnabar-300 dark:border-cinnabar-500/50 rounded-md hover:bg-cinnabar-200 dark:hover:bg-cinnabar-600/30 transition-all"
                    >
                      清理失效
                    </button>
                  )}
                  <Link
                    to="/oauth"
                    className="text-xs px-3 py-1.5 text-wisteria-600 dark:text-wisteria-400 bg-wisteria-100 dark:bg-wisteria-600/20 border border-wisteria-300 dark:border-wisteria-500/50 rounded-md hover:bg-wisteria-200 dark:hover:bg-wisteria-600/30 transition-all"
                  >
                    获取凭证
                  </Link>
                  <button
                    onClick={() => cliFileInputRef.current?.click()}
                    disabled={cliUploading}
                    className="text-xs px-3 py-1.5 text-jade-600 dark:text-jade-400 bg-jade-100 dark:bg-jade-600/20 border border-jade-300 dark:border-jade-500/50 rounded-md hover:bg-jade-200 dark:hover:bg-jade-600/30 transition-all flex items-center gap-1"
                  >
                    <Upload size={12} />
                    {cliUploading ? "上传中..." : "上传"}
                  </button>
                  {myCredentials.length > 0 && allowExportCredentials && (
                    <button
                      onClick={exportAllCliCredentials}
                      className="text-xs px-3 py-1.5 text-indigo-600 dark:text-indigo-400 bg-indigo-100 dark:bg-indigo-600/20 border border-indigo-300 dark:border-indigo-500/50 rounded-md hover:bg-indigo-200 dark:hover:bg-indigo-600/30 transition-all flex items-center gap-1"
                    >
                      <Download size={12} />
                      导出全部
                    </button>
                  )}
                  {myCredentials.length > 0 && (
                    <>
                      <button
                        onClick={verifyAllCliCredentials}
                        disabled={verifyingAllCli}
                        className="text-xs px-3 py-1.5 text-cyan-600 dark:text-cyan-400 bg-cyan-100 dark:bg-cyan-600/20 border border-cyan-300 dark:border-cyan-500/50 rounded-md hover:bg-cyan-200 dark:hover:bg-cyan-600/30 transition-all flex items-center gap-1 disabled:opacity-50"
                      >
                        <CheckCircle size={12} />
                        {verifyingAllCli ? "检测中..." : "检测全部"}
                      </button>
                      <button
                        onClick={() => toggleAllCliPublic(true)}
                        className="text-xs px-3 py-1.5 text-purple-600 dark:text-purple-400 bg-purple-100 dark:bg-purple-600/20 border border-purple-300 dark:border-purple-500/50 rounded-md hover:bg-purple-200 dark:hover:bg-purple-600/30 transition-all flex items-center gap-1"
                      >
                        <Globe size={12} />
                        全部公开
                      </button>
                      <button
                        onClick={() => toggleAllCliPublic(false)}
                        className="text-xs px-3 py-1.5 text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-600/20 border border-gray-300 dark:border-gray-500/50 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600/30 transition-all flex items-center gap-1"
                      >
                        <Lock size={12} />
                        全部私有
                      </button>
                    </>
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
                    ? "bg-jade-100 dark:bg-jade-600/20 border-jade-300 dark:border-jade-500/50 text-jade-600 dark:text-jade-400"
                    : "bg-cinnabar-100 dark:bg-cinnabar-600/20 border-cinnabar-300 dark:border-cinnabar-500/50 text-cinnabar-600 dark:text-cinnabar-400"
                }`}>
                  <div className="flex items-center justify-between mb-2">
                    <span>{cliUploadResult.message}</span>
                    <button onClick={() => setCliUploadResult(null)} className="text-inkbrown-300 dark:text-sand-500 hover:text-inkbrown-500 dark:hover:text-sand-300">
                      <X size={14} />
                    </button>
                  </div>
                  {cliUploadResult.results && (
                    <div className="text-xs space-y-1 max-h-32 overflow-y-auto">
                      {cliUploadResult.results.map((r, i) => (
                        <div key={i} className={`${r.status === 'success' ? 'text-jade-600 dark:text-jade-400' : r.status === 'error' ? 'text-cinnabar-600 dark:text-cinnabar-400' : r.status === 'skip' ? 'text-goldenrod-600 dark:text-goldenrod-400' : 'text-inkbrown-300 dark:text-sand-500'}`}>
                          {r.filename}: {r.message}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              
              <div className="p-3">
                {credLoading ? (
                  <div className="text-center py-8 text-inkbrown-300 dark:text-sand-500 text-sm">
                    <RefreshCw className="animate-spin mx-auto mb-2" size={20} />
                    加载中...
                  </div>
                ) : myCredentials.length === 0 ? (
                  <div className="text-center py-8 text-inkbrown-300 dark:text-sand-500 text-sm">
                    暂无凭证，点击上方按钮获取或上传
                  </div>
                ) : (
                  <div className="space-y-2">
                    {myCredentials.map((cred) => (
                      <div
                        key={cred.id}
                        className="p-3 rounded-lg border border-parchment-400 dark:border-night-50 flex items-center justify-between bg-parchment-50 dark:bg-night-200"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-inkbrown-500 dark:text-sand-200 truncate">{cred.email || cred.name}</div>
                          <div className="flex items-center gap-2 mt-1">
                            <span className={`text-xs px-1.5 py-0.5 rounded ${cred.is_active ? 'bg-jade-100 dark:bg-jade-600/20 text-jade-600 dark:text-jade-400' : 'bg-cinnabar-100 dark:bg-cinnabar-600/20 text-cinnabar-600 dark:text-cinnabar-400'}`}>
                              {cred.is_active ? '启用' : '禁用'}
                            </span>
                            {cred.model_tier === "3" && (
                              <span className="text-xs px-1.5 py-0.5 rounded bg-wisteria-100 dark:bg-wisteria-600/20 text-wisteria-600 dark:text-wisteria-400">3.0</span>
                            )}
                            {cred.is_public && (
                              <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-600/20 text-indigo-600 dark:text-indigo-400">公开</span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => verifyCred(cred.id, cred.email)}
                            disabled={verifyingCred === cred.id}
                            className="p-2 text-indigo-500 dark:text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-600/20 rounded-md transition-all"
                            title="检测"
                          >
                            {verifyingCred === cred.id ? <RefreshCw size={14} className="animate-spin" /> : <CheckCircle size={14} />}
                          </button>
                          {allowExportCredentials && (
                            <button
                              onClick={() => exportCred(cred.id, cred.email)}
                              className="p-2 text-wisteria-500 dark:text-wisteria-400 hover:bg-wisteria-100 dark:hover:bg-wisteria-600/20 rounded-md transition-all"
                              title="导出"
                            >
                              <Download size={14} />
                            </button>
                          )}
                          <button
                            onClick={() => toggleCliPublic(cred.id, cred.is_public)}
                            disabled={!cred.is_public && !cred.is_active}
                            className={`p-2 rounded-md transition-all disabled:opacity-50 ${
                              cred.is_public
                                ? 'text-indigo-500 dark:text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-600/20'
                                : 'text-inkbrown-200 dark:text-sand-600 hover:bg-parchment-200 dark:hover:bg-night-50'
                            }`}
                            title={cred.is_public ? "取消公开" : "公开"}
                          >
                            {cred.is_public ? <Globe size={14} /> : <Lock size={14} />}
                          </button>
                          <button
                            onClick={() => toggleCliActive(cred.id, cred.is_active)}
                            className={`p-2 rounded-md transition-all ${cred.is_active ? 'text-goldenrod-500 dark:text-goldenrod-400 hover:bg-goldenrod-100 dark:hover:bg-goldenrod-600/20' : 'text-jade-500 dark:text-jade-400 hover:bg-jade-100 dark:hover:bg-jade-600/20'}`}
                            title={cred.is_active ? "禁用" : "启用"}
                          >
                            {cred.is_active ? <X size={14} /> : <Check size={14} />}
                          </button>
                          <button
                            onClick={() => deleteCred(cred.id)}
                            className="p-2 text-cinnabar-500 dark:text-cinnabar-400 hover:bg-cinnabar-100 dark:hover:bg-cinnabar-600/20 rounded-md transition-all"
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
            <div className="rounded-lg border border-parchment-400 dark:border-night-50 p-4 bg-parchment-100 dark:bg-night-100">
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-lg bg-goldenrod-100 dark:bg-goldenrod-600/20">
                  <Rocket size={20} className="text-goldenrod-500 dark:text-goldenrod-400" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-medium text-inkbrown-500 dark:text-sand-200 mb-2">反重力 使用说明</h3>
                  <ul className="text-xs text-inkbrown-300 dark:text-sand-400 space-y-1.5">
                    <li className="flex items-start gap-2">
                      <span className="text-goldenrod-500 dark:text-goldenrod-400 mt-0.5">1.</span>
                      <span>反重力凭证用于调用 Claude、Gemini 等多种模型</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-goldenrod-500 dark:text-goldenrod-400 mt-0.5">2.</span>
                      <span>与 CLI 凭证<strong className="text-goldenrod-600 dark:text-goldenrod-400">独立</strong>，需单独获取</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-goldenrod-500 dark:text-goldenrod-400 mt-0.5">3.</span>
                      <span>API 端点：<code className="px-1.5 py-0.5 rounded bg-parchment-300 dark:bg-night-50 text-goldenrod-600 dark:text-goldenrod-400">{window.location.origin}/agy/v1</code></span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-goldenrod-500 dark:text-goldenrod-400 mt-0.5">4.</span>
                      <span>支持上传 JSON 凭证文件（格式：access_token, refresh_token, client_id, client_secret, project_id）</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            {/* 反重力凭证奖励说明 */}
            <div className="rounded-lg border border-goldenrod-300 dark:border-goldenrod-500/50 p-4 bg-goldenrod-50 dark:bg-goldenrod-600/10">
              <h3 className="text-sm font-medium text-goldenrod-600 dark:text-goldenrod-400 mb-3 flex items-center gap-2">
                <Rocket size={16} />
                上传反重力凭证额度说明
              </h3>
              <div className="space-y-2 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-goldenrod-600 dark:text-goldenrod-400 font-medium">上传有效反重力凭证：</span>
                  <span className="text-inkbrown-400 dark:text-sand-400">Claude 额外增加</span>
                  <span className="px-1.5 py-0.5 rounded bg-goldenrod-200 dark:bg-goldenrod-600/30 text-goldenrod-700 dark:text-goldenrod-300 font-medium">{rewardConfig.antigravity_quota_per_cred}</span>
                  <span className="text-inkbrown-400 dark:text-sand-400">次 / Gemini 额外增加</span>
                  <span className="px-1.5 py-0.5 rounded bg-goldenrod-200 dark:bg-goldenrod-600/30 text-goldenrod-700 dark:text-goldenrod-300 font-medium">{rewardConfig.antigravity_quota_per_cred}</span>
                  <span className="text-inkbrown-400 dark:text-sand-400">次</span>
                  {rewardConfig.banana_quota_enabled && (
                    <>
                      <span className="text-inkbrown-400 dark:text-sand-400">/ Banana(image系列模型) 额外增加</span>
                      <span className="px-1.5 py-0.5 rounded bg-yellow-200 dark:bg-yellow-600/30 text-yellow-700 dark:text-yellow-300 font-medium">{rewardConfig.banana_quota_per_cred}</span>
                      <span className="text-inkbrown-400 dark:text-sand-400">次</span>
                    </>
                  )}
                </div>
                {rewardConfig.banana_quota_enabled && (
                  <div className="flex items-center gap-2 text-goldenrod-600 dark:text-goldenrod-400">
                    <AlertTriangle size={14} />
                    <span>image系列模型只能用于生图，不能用于文字输出！</span>
                  </div>
                )}
              </div>
              {/* RPM 提示 */}
              <div className="mt-3 pt-3 border-t border-goldenrod-200 dark:border-goldenrod-500/30">
                <div className="flex items-center gap-2 text-xs">
                  <Zap size={14} className="text-goldenrod-500" />
                  <span className="text-inkbrown-400 dark:text-sand-400">RPM 速率：上传可用凭证（CLI 或反重力）后增加对应速率至</span>
                  <span className="px-1.5 py-0.5 rounded bg-goldenrod-200 dark:bg-goldenrod-600/30 text-goldenrod-700 dark:text-goldenrod-300 font-medium">{rewardConfig.antigravity_contributor_rpm}</span>
                  <span className="text-inkbrown-400 dark:text-sand-400">RPM</span>
                </div>
              </div>
            </div>

            {/* 统计卡片 */}
            <div className={`grid gap-3 ${agyStats?.banana_enabled ? 'grid-cols-2 md:grid-cols-5' : 'grid-cols-2 md:grid-cols-4'}`}>
              <div className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
                <div className="text-2xl font-bold text-goldenrod-500 dark:text-goldenrod-400">
                  {userInfo?.usage_by_provider?.claude || 0}
                  {agyQuotaEnabled && userInfo?.quota_by_provider?.claude && (
                    <span className="text-sm font-normal text-inkbrown-200 dark:text-sand-500">/{userInfo.quota_by_provider.claude}</span>
                  )}
                </div>
                <div className="text-xs text-inkbrown-200 dark:text-sand-500 mt-1">Claude 调用</div>
              </div>
              <div className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
                <div className="text-2xl font-bold text-indigo-500 dark:text-indigo-400">
                  {userInfo?.usage_by_provider?.gemini || 0}
                  {agyQuotaEnabled && userInfo?.quota_by_provider?.gemini && (
                    <span className="text-sm font-normal text-inkbrown-200 dark:text-sand-500">/{userInfo.quota_by_provider.gemini}</span>
                  )}
                </div>
                <div className="text-xs text-inkbrown-200 dark:text-sand-500 mt-1">Gemini 调用</div>
              </div>
              {agyStats?.banana_enabled && (
                <div className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
                  <div className="text-2xl font-bold text-yellow-600 dark:text-yellow-400">
                    {agyStats?.banana_used || 0}
                    <span className="text-sm font-normal text-inkbrown-200 dark:text-sand-500">/{agyStats?.banana_quota || 0}</span>
                  </div>
                  <div className="text-xs text-inkbrown-200 dark:text-sand-500 mt-1">Banana 额度</div>
                </div>
              )}
              <div className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
                <div className="text-2xl font-bold text-jade-500 dark:text-jade-400">{agyStats?.user_active || 0}</div>
                <div className="text-xs text-inkbrown-200 dark:text-sand-500 mt-1">有效凭证</div>
              </div>
              <div className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
                <div className="text-2xl font-bold text-wisteria-500 dark:text-wisteria-400">{agyCredentials.filter(c => c.is_public).length}</div>
                <div className="text-xs text-inkbrown-200 dark:text-sand-500 mt-1">公开凭证</div>
              </div>
            </div>

            {/* 消息提示 */}
            {agyMessage.text && (
              <div className={`p-3 rounded-lg border text-sm ${
                agyMessage.type === "success"
                  ? "bg-jade-100 dark:bg-jade-600/20 border-jade-300 dark:border-jade-500/50 text-jade-600 dark:text-jade-400"
                  : "bg-cinnabar-100 dark:bg-cinnabar-600/20 border-cinnabar-300 dark:border-cinnabar-500/50 text-cinnabar-600 dark:text-cinnabar-400"
              }`}>
                {agyMessage.text}
              </div>
            )}

            {/* 凭证列表 */}
            <div className="rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
              <div className="p-4 border-b border-parchment-400 dark:border-night-50 flex items-center justify-between flex-wrap gap-2">
                <h3 className="text-sm font-medium text-inkbrown-500 dark:text-sand-200 flex items-center gap-2">
                  <Rocket size={16} className="text-goldenrod-500 dark:text-goldenrod-400" />
                  反重力凭证 ({agyCredentials.length})
                </h3>
                <div className="flex gap-2 flex-wrap">
                  {agyCredentials.some((c) => !c.is_active) && (
                    <button
                      onClick={deleteAllAgyInactive}
                      className="text-xs px-3 py-1.5 text-cinnabar-600 dark:text-cinnabar-400 bg-cinnabar-100 dark:bg-cinnabar-600/20 border border-cinnabar-300 dark:border-cinnabar-500/50 rounded-md hover:bg-cinnabar-200 dark:hover:bg-cinnabar-600/30 transition-all"
                    >
                      清理失效
                    </button>
                  )}
                  <Link
                    to="/antigravity-oauth"
                    className="text-xs px-3 py-1.5 text-goldenrod-600 dark:text-goldenrod-400 bg-goldenrod-100 dark:bg-goldenrod-600/20 border border-goldenrod-300 dark:border-goldenrod-500/50 rounded-md hover:bg-goldenrod-200 dark:hover:bg-goldenrod-600/30 transition-all"
                  >
                    获取凭证
                  </Link>
                  <button
                    onClick={() => agyFileInputRef.current?.click()}
                    disabled={agyUploading}
                    className="text-xs px-3 py-1.5 text-jade-600 dark:text-jade-400 bg-jade-100 dark:bg-jade-600/20 border border-jade-300 dark:border-jade-500/50 rounded-md hover:bg-jade-200 dark:hover:bg-jade-600/30 transition-all flex items-center gap-1"
                  >
                    <Upload size={12} />
                    {agyUploading ? "上传中..." : "上传"}
                  </button>
                  {agyCredentials.length > 0 && allowExportCredentials && (
                    <button
                      onClick={exportAllAgyCredentials}
                      className="text-xs px-3 py-1.5 text-indigo-600 dark:text-indigo-400 bg-indigo-100 dark:bg-indigo-600/20 border border-indigo-300 dark:border-indigo-500/50 rounded-md hover:bg-indigo-200 dark:hover:bg-indigo-600/30 transition-all flex items-center gap-1"
                    >
                      <Download size={12} />
                      导出全部
                    </button>
                  )}
                  {agyCredentials.length > 0 && (
                    <>
                      <button
                        onClick={verifyAllAgyCredentials}
                        disabled={verifyingAllAgy}
                        className="text-xs px-3 py-1.5 text-cyan-600 dark:text-cyan-400 bg-cyan-100 dark:bg-cyan-600/20 border border-cyan-300 dark:border-cyan-500/50 rounded-md hover:bg-cyan-200 dark:hover:bg-cyan-600/30 transition-all flex items-center gap-1 disabled:opacity-50"
                      >
                        <CheckCircle size={12} />
                        {verifyingAllAgy ? "检测中..." : "检测全部"}
                      </button>
                      <button
                        onClick={() => toggleAllAgyPublic(true)}
                        className="text-xs px-3 py-1.5 text-purple-600 dark:text-purple-400 bg-purple-100 dark:bg-purple-600/20 border border-purple-300 dark:border-purple-500/50 rounded-md hover:bg-purple-200 dark:hover:bg-purple-600/30 transition-all flex items-center gap-1"
                      >
                        <Globe size={12} />
                        全部公开
                      </button>
                      <button
                        onClick={() => toggleAllAgyPublic(false)}
                        className="text-xs px-3 py-1.5 text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-600/20 border border-gray-300 dark:border-gray-500/50 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600/30 transition-all flex items-center gap-1"
                      >
                        <Lock size={12} />
                        全部私有
                      </button>
                    </>
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
                    className="p-1.5 text-inkbrown-300 dark:text-sand-500 hover:text-inkbrown-500 dark:hover:text-sand-300 hover:bg-parchment-200 dark:hover:bg-night-50 rounded-md transition-all"
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
                    ? "bg-jade-100 dark:bg-jade-600/20 border-jade-300 dark:border-jade-500/50 text-jade-600 dark:text-jade-400"
                    : "bg-cinnabar-100 dark:bg-cinnabar-600/20 border-cinnabar-300 dark:border-cinnabar-500/50 text-cinnabar-600 dark:text-cinnabar-400"
                }`}>
                  <div className="flex items-center justify-between mb-2">
                    <span>{agyUploadResult.message}</span>
                    <button onClick={() => setAgyUploadResult(null)} className="text-inkbrown-300 dark:text-sand-500 hover:text-inkbrown-500 dark:hover:text-sand-300">
                      <X size={14} />
                    </button>
                  </div>
                  {agyUploadResult.results && (
                    <div className="text-xs space-y-1 max-h-32 overflow-y-auto">
                      {agyUploadResult.results.map((r, i) => (
                        <div key={i} className={`${r.status === 'success' ? 'text-jade-600 dark:text-jade-400' : r.status === 'error' ? 'text-cinnabar-600 dark:text-cinnabar-400' : r.status === 'skip' ? 'text-goldenrod-600 dark:text-goldenrod-400' : 'text-inkbrown-300 dark:text-sand-500'}`}>
                          {r.filename}: {r.message}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              
              <div className="p-3">
                {agyCredLoading ? (
                  <div className="text-center py-8 text-inkbrown-300 dark:text-sand-500 text-sm">
                    <RefreshCw className="animate-spin mx-auto mb-2" size={20} />
                    加载中...
                  </div>
                ) : agyCredentials.length === 0 ? (
                  <div className="text-center py-8 text-inkbrown-300 dark:text-sand-500 text-sm">
                    暂无凭证，点击上方按钮获取或上传
                  </div>
                ) : (
                  <div className="space-y-2">
                    {agyCredentials.map((cred, index) => (
                      <div
                        key={cred.id}
                        className="p-3 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-50 dark:bg-night-200"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className={`text-xs px-1.5 py-0.5 rounded ${cred.is_active ? 'bg-jade-100 dark:bg-jade-600/20 text-jade-600 dark:text-jade-400' : 'bg-cinnabar-100 dark:bg-cinnabar-600/20 text-cinnabar-600 dark:text-cinnabar-400'}`}>
                                {cred.is_active ? '启用' : '禁用'}
                              </span>
                              <span className="text-xs px-1.5 py-0.5 rounded bg-goldenrod-100 dark:bg-goldenrod-600/20 text-goldenrod-600 dark:text-goldenrod-400">AGY</span>
                              {cred.is_public && (
                                <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-600/20 text-indigo-600 dark:text-indigo-400">公开</span>
                              )}
                              <span className="text-xs text-inkbrown-200 dark:text-sand-600">#{index + 1}</span>
                            </div>
                            {cred.project_id && (
                              <div className="text-xs text-jade-500 dark:text-jade-400 font-mono truncate">{cred.project_id}</div>
                            )}
                            <div className="text-sm text-inkbrown-400 dark:text-sand-400 truncate">{cred.email || cred.name}</div>
                          </div>
                          <div className="flex items-center gap-0.5">
                            <button
                              onClick={() => fetchAgyQuota(cred.id, cred.email || cred.name)}
                              disabled={agyLoadingQuota === cred.id || !cred.is_active}
                              className="p-1.5 text-indigo-500 dark:text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-600/20 rounded-md disabled:opacity-50 transition-all"
                              title="额度详情"
                            >
                              {agyLoadingQuota === cred.id ? <RefreshCw size={14} className="animate-spin" /> : <BarChart2 size={14} />}
                            </button>
                            <button
                              onClick={() => verifyAgyCred(cred.id, cred.email || cred.name)}
                              disabled={agyVerifying === cred.id}
                              className="p-1.5 text-jade-500 dark:text-jade-400 hover:bg-jade-100 dark:hover:bg-jade-600/20 rounded-md disabled:opacity-50 transition-all"
                              title="检测有效性"
                            >
                              {agyVerifying === cred.id ? <RefreshCw size={14} className="animate-spin" /> : <CheckCircle size={14} />}
                            </button>
                            <button
                              onClick={() => refreshAgyProjectId(cred.id, cred.email || cred.name)}
                              disabled={agyVerifying === cred.id}
                              className="p-1.5 text-goldenrod-500 dark:text-goldenrod-400 hover:bg-goldenrod-100 dark:hover:bg-goldenrod-600/20 rounded-md disabled:opacity-50 transition-all"
                              title="刷新 Project ID"
                            >
                              <RefreshCcw size={14} />
                            </button>
                            {allowExportCredentials && (
                              <button
                                onClick={() => setExportModal({ id: cred.id, email: cred.email || cred.name })}
                                className="p-1.5 text-wisteria-500 dark:text-wisteria-400 hover:bg-wisteria-100 dark:hover:bg-wisteria-600/20 rounded-md transition-all"
                                title="导出凭证"
                              >
                                <Download size={14} />
                              </button>
                            )}
                            <button
                              onClick={() => toggleAgyPublic(cred.id, cred.is_public)}
                              disabled={!cred.is_public && !cred.is_active}
                              className={`p-1.5 rounded-md transition-all disabled:opacity-50 ${
                                cred.is_public
                                  ? 'text-indigo-500 dark:text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-600/20'
                                  : 'text-inkbrown-200 dark:text-sand-600 hover:bg-parchment-200 dark:hover:bg-night-50'
                              }`}
                              title={cred.is_public ? "取消公开" : "公开"}
                            >
                              {cred.is_public ? <Globe size={14} /> : <Lock size={14} />}
                            </button>
                            <button
                              onClick={() => toggleAgyActive(cred.id, cred.is_active)}
                              className={`p-1.5 rounded-md transition-all ${cred.is_active ? 'text-goldenrod-500 dark:text-goldenrod-400 hover:bg-goldenrod-100 dark:hover:bg-goldenrod-600/20' : 'text-jade-500 dark:text-jade-400 hover:bg-jade-100 dark:hover:bg-jade-600/20'}`}
                              title={cred.is_active ? "禁用" : "启用"}
                            >
                              {cred.is_active ? <X size={14} /> : <Check size={14} />}
                            </button>
                            <button
                              onClick={() => deleteAgyCred(cred.id)}
                              className="p-1.5 text-cinnabar-500 dark:text-cinnabar-400 hover:bg-cinnabar-100 dark:hover:bg-cinnabar-600/20 rounded-md transition-all"
                              title="删除"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </div>

                        {/* 额度预览按钮和展开区域 */}
                        <div className="mt-2 border-t border-parchment-300 dark:border-night-50 pt-2">
                          <button
                            onClick={() => cred.is_active && toggleAgyQuotaPreview(cred.id)}
                            disabled={!cred.is_active}
                            className={`w-full flex items-center justify-between px-2 py-1.5 rounded-lg text-sm transition-colors ${
                              cred.is_active
                                ? "bg-parchment-200 dark:bg-night-50 hover:bg-parchment-300 dark:hover:bg-night-100 cursor-pointer"
                                : "bg-parchment-300/50 dark:bg-night-200/50 text-inkbrown-200 dark:text-sand-600 cursor-not-allowed"
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <BarChart2 size={14} className="text-indigo-500 dark:text-indigo-400" />
                              <span className="text-inkbrown-300 dark:text-sand-500 text-xs">
                                {agyLoadingQuotaPreview === cred.id
                                  ? "加载中..."
                                  : agyQuotaCache[cred.id]
                                    ? "额度信息"
                                    : "暂无额度"}
                              </span>
                            </div>
                            {cred.is_active && (
                              agyExpandedQuota === cred.id
                                ? <ChevronUp size={14} className="text-inkbrown-300 dark:text-sand-500" />
                                : <ChevronDown size={14} className="text-inkbrown-300 dark:text-sand-500" />
                            )}
                          </button>

                          {/* 展开的额度详情 */}
                          {agyExpandedQuota === cred.id && cred.is_active && (
                            <div className="mt-2 space-y-2 px-1">
                              {agyLoadingQuotaPreview === cred.id ? (
                                <div className="flex items-center justify-center py-3 text-inkbrown-300 dark:text-sand-500 text-xs">
                                  <RefreshCw size={14} className="animate-spin mr-2" />
                                  加载额度中...
                                </div>
                              ) : agyQuotaCache[cred.id]?.error ? (
                                <div className="text-center py-2 text-cinnabar-500 dark:text-cinnabar-400 text-xs">
                                  {agyQuotaCache[cred.id].error}
                                </div>
                              ) : agyQuotaCache[cred.id] ? (
                                <>
                                  {agyQuotaCache[cred.id].claude?.count > 0 && (
                                    <div className="flex items-center gap-2">
                                      <span className="text-wisteria-500 dark:text-wisteria-400 w-14 text-xs">Claude</span>
                                      <div className="flex-1 bg-parchment-300 dark:bg-night-50 rounded-full h-1.5">
                                        <div
                                          className={`h-1.5 rounded-full ${getAgyQuotaColor(agyQuotaCache[cred.id].claude.remaining).bar}`}
                                          style={{ width: `${Math.min(agyQuotaCache[cred.id].claude.remaining, 100)}%` }}
                                        />
                                      </div>
                                      <span className={`text-xs font-medium w-12 text-right ${getAgyQuotaColor(agyQuotaCache[cred.id].claude.remaining).text}`}>
                                        {agyQuotaCache[cred.id].claude.remaining.toFixed(1)}%
                                      </span>
                                    </div>
                                  )}
                                  {agyQuotaCache[cred.id].gemini?.count > 0 && (
                                    <div className="flex items-center gap-2">
                                      <span className="text-indigo-500 dark:text-indigo-400 w-14 text-xs">Gemini</span>
                                      <div className="flex-1 bg-parchment-300 dark:bg-night-50 rounded-full h-1.5">
                                        <div
                                          className={`h-1.5 rounded-full ${getAgyQuotaColor(agyQuotaCache[cred.id].gemini.remaining).bar}`}
                                          style={{ width: `${Math.min(agyQuotaCache[cred.id].gemini.remaining, 100)}%` }}
                                        />
                                      </div>
                                      <span className={`text-xs font-medium w-12 text-right ${getAgyQuotaColor(agyQuotaCache[cred.id].gemini.remaining).text}`}>
                                        {agyQuotaCache[cred.id].gemini.remaining.toFixed(1)}%
                                      </span>
                                    </div>
                                  )}
                                  {agyQuotaCache[cred.id].banana?.count > 0 && (
                                    <div className="flex items-center gap-2">
                                      <span className="text-goldenrod-500 dark:text-goldenrod-400 w-14 text-xs">banana</span>
                                      <div className="flex-1 bg-parchment-300 dark:bg-night-50 rounded-full h-1.5">
                                        <div
                                          className={`h-1.5 rounded-full ${getAgyQuotaColor(agyQuotaCache[cred.id].banana.remaining).bar}`}
                                          style={{ width: `${Math.min(agyQuotaCache[cred.id].banana.remaining, 100)}%` }}
                                        />
                                      </div>
                                      <span className={`text-xs font-medium w-12 text-right ${getAgyQuotaColor(agyQuotaCache[cred.id].banana.remaining).text}`}>
                                        {agyQuotaCache[cred.id].banana.remaining.toFixed(1)}%
                                      </span>
                                    </div>
                                  )}
                                  {!agyQuotaCache[cred.id].claude?.count && !agyQuotaCache[cred.id].gemini?.count && !agyQuotaCache[cred.id].banana?.count && (
                                    <div className="text-center py-2 text-inkbrown-300 dark:text-sand-500 text-xs">
                                      暂无额度数据
                                    </div>
                                  )}
                                  {(agyQuotaCache[cred.id].claude?.resetTime || agyQuotaCache[cred.id].gemini?.resetTime) && (
                                    <div className="text-xs text-inkbrown-200 dark:text-sand-600 text-right">
                                      重置: {agyQuotaCache[cred.id].claude?.resetTime || agyQuotaCache[cred.id].gemini?.resetTime}
                                    </div>
                                  )}
                                </>
                              ) : (
                                <div className="text-center py-2 text-inkbrown-300 dark:text-sand-500 text-xs">
                                  点击加载额度信息
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ========== Codex 标签页 ========== */}
        {mainTab === "codex" && (
          <div className="space-y-5">
            {/* 使用提示卡片 */}
            <div className="rounded-lg border border-parchment-400 dark:border-night-50 p-4 bg-parchment-100 dark:bg-night-100">
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-lg bg-emerald-100 dark:bg-emerald-600/20">
                  <Code size={20} className="text-emerald-500 dark:text-emerald-400" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-medium text-inkbrown-500 dark:text-sand-200 mb-2">Codex 使用说明</h3>
                  <ul className="text-xs text-inkbrown-300 dark:text-sand-400 space-y-1.5">
                    <li className="flex items-start gap-2">
                      <span className="text-emerald-500 dark:text-emerald-400 mt-0.5">1.</span>
                      <span>Codex 凭证用于调用 OpenAI GPT 模型（GPT-5.2、5.1-mini 等）</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-emerald-500 dark:text-emerald-400 mt-0.5">2.</span>
                      <span>通过 ChatGPT OAuth 登录获取凭证，与 CLI/反重力凭证<strong className="text-emerald-600 dark:text-emerald-400">完全独立</strong></span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-emerald-500 dark:text-emerald-400 mt-0.5">3.</span>
                      <span>API 端点：<code className="px-1.5 py-0.5 rounded bg-parchment-300 dark:bg-night-50 text-emerald-600 dark:text-emerald-400">{window.location.origin}/codex/v1</code></span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-emerald-500 dark:text-emerald-400 mt-0.5">4.</span>
                      <span>模型前缀：<code className="px-1.5 py-0.5 rounded bg-parchment-300 dark:bg-night-50 text-emerald-600 dark:text-emerald-400">codex-</code>（如 codex-gpt-5.2-codex）</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            {/* 消息提示 */}
            {codexMessage.text && (
              <div className={`p-3 rounded-lg border text-sm ${
                codexMessage.type === "success"
                  ? "bg-jade-100 dark:bg-jade-600/20 border-jade-300 dark:border-jade-500/50 text-jade-600 dark:text-jade-400"
                  : "bg-cinnabar-100 dark:bg-cinnabar-600/20 border-cinnabar-300 dark:border-cinnabar-500/50 text-cinnabar-600 dark:text-cinnabar-400"
              }`}>
                <div className="flex items-center justify-between">
                  <span>{codexMessage.text}</span>
                  <button onClick={() => setCodexMessage({ type: "", text: "" })} className="text-inkbrown-300 hover:text-inkbrown-500">
                    <X size={14} />
                  </button>
                </div>
              </div>
            )}

            {/* 统计卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
                <div className="text-2xl font-bold text-emerald-500 dark:text-emerald-400">
                  {userInfo?.usage_by_provider?.codex || 0}
                  {userInfo?.quota_by_provider?.codex && (
                    <span className="text-sm font-normal text-inkbrown-200 dark:text-sand-500">/{userInfo.quota_by_provider.codex}</span>
                  )}
                </div>
                <div className="text-xs text-inkbrown-200 dark:text-sand-500 mt-1">Codex 调用</div>
              </div>
              <div className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
                <div className="text-2xl font-bold text-jade-500 dark:text-jade-400">{codexStats?.user_active || 0}</div>
                <div className="text-xs text-inkbrown-200 dark:text-sand-500 mt-1">有效凭证</div>
              </div>
              <div className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
                <div className="text-2xl font-bold text-wisteria-500 dark:text-wisteria-400">{codexCredentials.filter(c => c.is_public).length}</div>
                <div className="text-xs text-inkbrown-200 dark:text-sand-500 mt-1">公开凭证</div>
              </div>
              <div className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
                <div className="text-2xl font-bold text-indigo-500 dark:text-indigo-400">{codexStats?.pool_total || 0}</div>
                <div className="text-xs text-inkbrown-200 dark:text-sand-500 mt-1">池中凭证</div>
              </div>
            </div>

            {/* OAuth 授权区域 */}
            <div className="rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100 p-4">
              <h3 className="text-sm font-medium text-inkbrown-500 dark:text-sand-200 mb-4 flex items-center gap-2">
                <Shield size={16} className="text-emerald-500 dark:text-emerald-400" />
                OAuth 授权登录
              </h3>
              
              {!codexOauthState ? (
                <div className="space-y-3">
                  <p className="text-xs text-inkbrown-300 dark:text-sand-400">
                    点击下方按钮开始 ChatGPT OAuth 授权流程，登录成功后将回调 URL 粘贴到输入框完成凭证添加。
                  </p>
                  <div className="flex items-center gap-2">
                    <label className="flex items-center gap-2 text-xs text-inkbrown-400 dark:text-sand-400 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={codexIsPublic}
                        onChange={(e) => setCodexIsPublic(e.target.checked)}
                        className="w-4 h-4 rounded border-parchment-400 dark:border-night-50 text-emerald-500 focus:ring-emerald-500"
                      />
                      公开凭证（大锅饭模式）
                    </label>
                  </div>
                  <button
                    onClick={startCodexOAuth}
                    className="w-full px-4 py-2.5 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg font-medium text-sm transition-all flex items-center justify-center gap-2"
                  >
                    <ExternalLink size={16} />
                    开始 OAuth 授权
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-600/10 border border-emerald-200 dark:border-emerald-500/30">
                    <p className="text-xs text-emerald-700 dark:text-emerald-300 mb-2">
                      请在弹出的窗口中完成登录，然后将回调 URL 粘贴到下方：
                    </p>
                    <code className="block text-xs text-emerald-600 dark:text-emerald-400 bg-white dark:bg-night-200 p-2 rounded break-all">
                      {codexOauthState.auth_url?.substring(0, 80)}...
                    </code>
                  </div>
                  <input
                    type="text"
                    value={codexCallbackUrl}
                    onChange={(e) => setCodexCallbackUrl(e.target.value)}
                    placeholder="粘贴回调 URL（以 https://chatgpt.com 开头）"
                    className="w-full px-3 py-2 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-50 dark:bg-night-200 text-sm text-inkbrown-500 dark:text-sand-200 placeholder:text-inkbrown-200 dark:placeholder:text-sand-600 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={submitCodexCallback}
                      disabled={codexProcessing || !codexCallbackUrl.trim()}
                      className="flex-1 px-4 py-2.5 bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 text-white rounded-lg font-medium text-sm transition-all flex items-center justify-center gap-2"
                    >
                      {codexProcessing ? <RefreshCw size={16} className="animate-spin" /> : <CheckCircle size={16} />}
                      提交
                    </button>
                    <button
                      onClick={() => { setCodexOauthState(null); setCodexCallbackUrl(""); }}
                      className="px-4 py-2.5 bg-parchment-200 dark:bg-night-50 hover:bg-parchment-300 dark:hover:bg-night-100 text-inkbrown-400 dark:text-sand-400 rounded-lg font-medium text-sm transition-all"
                    >
                      取消
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* 文件上传 */}
            <div className="rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100 p-4">
              <h3 className="text-sm font-medium text-inkbrown-500 dark:text-sand-200 mb-3 flex items-center gap-2">
                <Upload size={16} className="text-emerald-500 dark:text-emerald-400" />
                上传 JSON 凭证
              </h3>
              <p className="text-xs text-inkbrown-300 dark:text-sand-400 mb-3">
                支持格式：{"{"} access_token, refresh_token, email, account_id {"}"}
              </p>
              <input
                type="file"
                ref={codexFileInputRef}
                accept=".json"
                multiple
                onChange={handleCodexFileUpload}
                className="hidden"
              />
              <button
                onClick={() => codexFileInputRef.current?.click()}
                disabled={codexUploading}
                className="w-full px-4 py-2.5 bg-parchment-200 dark:bg-night-50 hover:bg-parchment-300 dark:hover:bg-night-100 text-inkbrown-400 dark:text-sand-400 rounded-lg font-medium text-sm transition-all flex items-center justify-center gap-2 border border-parchment-400 dark:border-night-50"
              >
                {codexUploading ? <RefreshCw size={16} className="animate-spin" /> : <Upload size={16} />}
                {codexUploading ? "上传中..." : "选择 JSON 文件"}
              </button>
            </div>

            {/* 凭证列表 */}
            <div className="rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
              <div className="p-4 border-b border-parchment-400 dark:border-night-50 flex items-center justify-between flex-wrap gap-2">
                <h3 className="text-sm font-medium text-inkbrown-500 dark:text-sand-200 flex items-center gap-2">
                  <Code size={16} className="text-emerald-500 dark:text-emerald-400" />
                  我的 Codex 凭证
                </h3>
                <button
                  onClick={() => { fetchCodexCredentials(); fetchCodexStats(); }}
                  className="text-xs text-emerald-500 dark:text-emerald-400 hover:text-emerald-600 flex items-center gap-1"
                >
                  <RefreshCw size={12} />
                  刷新
                </button>
              </div>
              
              <div className="p-4">
                {codexCredLoading ? (
                  <div className="text-center py-8 text-inkbrown-300 dark:text-sand-500 text-sm">
                    <RefreshCw className="animate-spin mx-auto mb-2" size={20} />
                    加载中...
                  </div>
                ) : codexCredentials.length === 0 ? (
                  <div className="text-center py-8 text-inkbrown-300 dark:text-sand-400 text-sm">
                    暂无凭证，请通过 OAuth 授权或上传 JSON 文件添加
                  </div>
                ) : (
                  <div className="space-y-3">
                    {codexCredentials.map((cred) => (
                      <div
                        key={cred.id}
                        className="p-4 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-50 dark:bg-night-200"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium text-inkbrown-500 dark:text-sand-200 truncate">
                              {cred.email || cred.name || `凭证 #${cred.id}`}
                            </div>
                            <div className="flex flex-wrap items-center gap-2 mt-2">
                              <span className={`text-xs px-2 py-0.5 rounded-full ${
                                cred.is_active
                                  ? "bg-jade-100 dark:bg-jade-600/20 text-jade-600 dark:text-jade-400"
                                  : "bg-cinnabar-100 dark:bg-cinnabar-600/20 text-cinnabar-600 dark:text-cinnabar-400"
                              }`}>
                                {cred.is_active ? "有效" : "无效"}
                              </span>
                              {cred.is_public && (
                                <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-600/20 text-indigo-600 dark:text-indigo-400">
                                  公开
                                </span>
                              )}
                              {cred.plan_type && (
                                <span className="text-xs px-2 py-0.5 rounded-full bg-wisteria-100 dark:bg-wisteria-600/20 text-wisteria-600 dark:text-wisteria-400">
                                  {cred.plan_type}
                                </span>
                              )}
                            </div>
                            {cred.last_error && (
                              <div className="mt-2 text-xs text-cinnabar-500 dark:text-cinnabar-400 truncate">
                                {cred.last_error}
                              </div>
                            )}
                            <div className="mt-2 text-xs text-inkbrown-200 dark:text-sand-600">
                              调用: {cred.total_requests || 0} 次
                              {cred.last_used_at && ` · 最后使用: ${new Date(cred.last_used_at).toLocaleString()}`}
                            </div>
                          </div>
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => verifyCodexCred(cred.id)}
                              disabled={codexVerifying === cred.id}
                              className="p-2 text-indigo-500 dark:text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-600/20 rounded-md transition-all"
                              title="验证凭证"
                            >
                              {codexVerifying === cred.id ? <RefreshCw size={14} className="animate-spin" /> : <CheckCircle size={14} />}
                            </button>
                            <button
                              onClick={() => refreshCodexToken(cred.id)}
                              disabled={codexRefreshing === cred.id}
                              className="p-2 text-emerald-500 dark:text-emerald-400 hover:bg-emerald-100 dark:hover:bg-emerald-600/20 rounded-md transition-all"
                              title="刷新 Token"
                            >
                              {codexRefreshing === cred.id ? <RefreshCw size={14} className="animate-spin" /> : <Zap size={14} />}
                            </button>
                            <button
                              onClick={() => toggleCodexPublic(cred.id, cred.is_public)}
                              className={`p-2 rounded-md transition-all ${
                                cred.is_public
                                  ? "text-indigo-500 dark:text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-600/20"
                                  : "text-inkbrown-200 dark:text-sand-600 hover:bg-parchment-200 dark:hover:bg-night-50"
                              }`}
                              title={cred.is_public ? "取消公开" : "公开"}
                            >
                              {cred.is_public ? <Globe size={14} /> : <Lock size={14} />}
                            </button>
                            <button
                              onClick={() => toggleCodexActive(cred.id, cred.is_active)}
                              className={`p-2 rounded-md transition-all ${
                                cred.is_active
                                  ? "text-goldenrod-500 dark:text-goldenrod-400 hover:bg-goldenrod-100 dark:hover:bg-goldenrod-600/20"
                                  : "text-jade-500 dark:text-jade-400 hover:bg-jade-100 dark:hover:bg-jade-600/20"
                              }`}
                              title={cred.is_active ? "禁用" : "启用"}
                            >
                              {cred.is_active ? <X size={14} /> : <Check size={14} />}
                            </button>
                            <button
                              onClick={() => deleteCodexCred(cred.id)}
                              className="p-2 text-cinnabar-500 dark:text-cinnabar-400 hover:bg-cinnabar-100 dark:hover:bg-cinnabar-600/20 rounded-md transition-all"
                              title="删除"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </div>

                        {/* 配额预览按钮和展开区域 */}
                        <div className="mt-3 border-t border-parchment-300 dark:border-night-50 pt-3">
                          <button
                            onClick={() => cred.is_active && toggleCodexQuotaPreview(cred.id)}
                            disabled={!cred.is_active}
                            className={`w-full flex items-center justify-between px-2 py-1.5 rounded-lg text-sm transition-colors ${
                              cred.is_active
                                ? "bg-parchment-200 dark:bg-night-50 hover:bg-parchment-300 dark:hover:bg-night-100 cursor-pointer"
                                : "bg-parchment-300/50 dark:bg-night-200/50 text-inkbrown-200 dark:text-sand-600 cursor-not-allowed"
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <BarChart2 size={14} className="text-emerald-500 dark:text-emerald-400" />
                              <span className="text-inkbrown-300 dark:text-sand-500 text-xs">
                                {codexLoadingQuotaPreview === cred.id
                                  ? "加载中..."
                                  : codexQuotaCache[cred.id]
                                    ? "配额信息"
                                    : "查看配额"}
                              </span>
                            </div>
                            {cred.is_active && (
                              codexExpandedQuota === cred.id
                                ? <ChevronUp size={14} className="text-inkbrown-300 dark:text-sand-500" />
                                : <ChevronDown size={14} className="text-inkbrown-300 dark:text-sand-500" />
                            )}
                          </button>

                          {/* 展开的配额详情 */}
                          {codexExpandedQuota === cred.id && cred.is_active && (
                            <div className="mt-2 space-y-2 px-1">
                              {codexLoadingQuotaPreview === cred.id ? (
                                <div className="flex items-center justify-center py-3 text-inkbrown-300 dark:text-sand-500 text-xs">
                                  <RefreshCw size={14} className="animate-spin mr-2" />
                                  加载配额中...
                                </div>
                              ) : codexQuotaCache[cred.id]?.error ? (
                                <div className="text-center py-2 text-cinnabar-500 dark:text-cinnabar-400 text-xs">
                                  {codexQuotaCache[cred.id].error}
                                </div>
                              ) : codexQuotaCache[cred.id]?.rate_limits ? (
                                <>
                                  {/* 5小时限制 */}
                                  <div className="flex items-center gap-2">
                                    <span className="text-emerald-500 dark:text-emerald-400 w-14 text-xs">5小时</span>
                                    <div className="flex-1 bg-parchment-300 dark:bg-night-50 rounded-full h-1.5">
                                      <div
                                        className={`h-1.5 rounded-full ${getCodexQuotaColor(codexQuotaCache[cred.id].rate_limits.hourly_5h?.remaining || 0).bar}`}
                                        style={{ width: `${Math.min(codexQuotaCache[cred.id].rate_limits.hourly_5h?.remaining || 0, 100)}%` }}
                                      />
                                    </div>
                                    <span className={`text-xs font-medium w-12 text-right ${getCodexQuotaColor(codexQuotaCache[cred.id].rate_limits.hourly_5h?.remaining || 0).text}`}>
                                      {(codexQuotaCache[cred.id].rate_limits.hourly_5h?.remaining || 0).toFixed(0)}%
                                    </span>
                                  </div>
                                  {/* 每周限制 */}
                                  <div className="flex items-center gap-2">
                                    <span className="text-indigo-500 dark:text-indigo-400 w-14 text-xs">每周</span>
                                    <div className="flex-1 bg-parchment-300 dark:bg-night-50 rounded-full h-1.5">
                                      <div
                                        className={`h-1.5 rounded-full ${getCodexQuotaColor(codexQuotaCache[cred.id].rate_limits.weekly?.remaining || 0).bar}`}
                                        style={{ width: `${Math.min(codexQuotaCache[cred.id].rate_limits.weekly?.remaining || 0, 100)}%` }}
                                      />
                                    </div>
                                    <span className={`text-xs font-medium w-12 text-right ${getCodexQuotaColor(codexQuotaCache[cred.id].rate_limits.weekly?.remaining || 0).text}`}>
                                      {(codexQuotaCache[cred.id].rate_limits.weekly?.remaining || 0).toFixed(0)}%
                                    </span>
                                  </div>
                                  {/* 代码审查 */}
                                  <div className="flex items-center gap-2">
                                    <span className="text-wisteria-500 dark:text-wisteria-400 w-14 text-xs">审查</span>
                                    <div className="flex-1 bg-parchment-300 dark:bg-night-50 rounded-full h-1.5">
                                      <div
                                        className={`h-1.5 rounded-full ${getCodexQuotaColor(codexQuotaCache[cred.id].rate_limits.code_review?.remaining || 0).bar}`}
                                        style={{ width: `${Math.min(codexQuotaCache[cred.id].rate_limits.code_review?.remaining || 0, 100)}%` }}
                                      />
                                    </div>
                                    <span className={`text-xs font-medium w-12 text-right ${getCodexQuotaColor(codexQuotaCache[cred.id].rate_limits.code_review?.remaining || 0).text}`}>
                                      {(codexQuotaCache[cred.id].rate_limits.code_review?.remaining || 0).toFixed(0)}%
                                    </span>
                                  </div>
                                </>
                              ) : (
                                <div className="text-center py-2 text-inkbrown-300 dark:text-sand-500 text-xs">
                                  点击加载配额信息
                                </div>
                              )}
                            </div>
                          )}
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
            <div className="rounded-lg border border-parchment-400 dark:border-night-50 p-4 bg-parchment-100 dark:bg-night-100">
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-lg bg-cinnabar-100 dark:bg-cinnabar-600/20">
                  <Key size={20} className="text-cinnabar-500 dark:text-cinnabar-400" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-medium text-inkbrown-500 dark:text-sand-200 mb-2">API 密钥说明</h3>
                  <ul className="text-xs text-inkbrown-300 dark:text-sand-400 space-y-1.5">
                    <li className="flex items-start gap-2">
                      <span className="text-cinnabar-500 dark:text-cinnabar-400 mt-0.5">1.</span>
                      <span>此密钥用于调用 CLI 和反重力 API</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-cinnabar-500 dark:text-cinnabar-400 mt-0.5">2.</span>
                      <span>请妥善保管，不要泄露给他人</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-cinnabar-500 dark:text-cinnabar-400 mt-0.5">3.</span>
                      <span>如需更换可点击「更换」按钮重新生成</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            {/* API 密钥卡片 */}
            <div className="rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
              <div className="p-4 border-b border-parchment-400 dark:border-night-50">
                <h3 className="text-sm font-medium text-inkbrown-500 dark:text-sand-200 flex items-center gap-2">
                  <Key size={16} className="text-cinnabar-500 dark:text-cinnabar-400" />
                  API 密钥
                </h3>
              </div>
              
              <div className="p-4">
                {keyLoading ? (
                  <div className="text-center py-8 text-inkbrown-300 dark:text-sand-500 text-sm">
                    <RefreshCw className="animate-spin mx-auto mb-2" size={20} />
                    加载中...
                  </div>
                ) : myKey ? (
                  <div className="space-y-4">
                    <div className="p-3 rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-50 dark:bg-night-200">
                      <code className="block text-wisteria-600 dark:text-wisteria-400 text-sm font-mono break-all">{myKey.key}</code>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={copyKey}
                        className="flex-1 px-4 py-2.5 bg-wisteria-100 dark:bg-wisteria-600/20 text-wisteria-600 dark:text-wisteria-400 border border-wisteria-300 dark:border-wisteria-500/50 rounded-lg hover:bg-wisteria-200 dark:hover:bg-wisteria-600/30 flex items-center justify-center gap-2 text-sm transition-all"
                      >
                        {keyCopied ? <Check size={16} /> : <Copy size={16} />}
                        {keyCopied ? "已复制" : "复制"}
                      </button>
                      <button
                        onClick={regenerateKey}
                        disabled={regenerating}
                        className="flex-1 px-4 py-2.5 bg-goldenrod-100 dark:bg-goldenrod-600/20 text-goldenrod-600 dark:text-goldenrod-400 border border-goldenrod-300 dark:border-goldenrod-500/50 rounded-lg hover:bg-goldenrod-200 dark:hover:bg-goldenrod-600/30 disabled:opacity-50 flex items-center justify-center gap-2 text-sm transition-all"
                      >
                        <RefreshCcw size={16} className={regenerating ? "animate-spin" : ""} />
                        更换
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8 text-cinnabar-500 dark:text-cinnabar-400 text-sm">
                    获取失败，请刷新重试
                  </div>
                )}
              </div>
            </div>

            {/* 端点信息 */}
            <div className="rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
              <div className="p-4 border-b border-parchment-400 dark:border-night-50">
                <h3 className="text-sm font-medium text-inkbrown-500 dark:text-sand-200">API 端点</h3>
              </div>
              <div className="p-4 space-y-3">
                <div>
                  <div className="text-xs text-inkbrown-200 dark:text-sand-600 mb-1.5">CLI 端点</div>
                  <code className="block p-2.5 rounded-lg text-sm text-wisteria-600 dark:text-wisteria-400 font-mono bg-parchment-50 dark:bg-night-200 border border-parchment-300 dark:border-night-50">
                    {apiEndpoint}
                  </code>
                </div>
                <div>
                  <div className="text-xs text-inkbrown-200 dark:text-sand-600 mb-1.5">反重力端点</div>
                  <code className="block p-2.5 rounded-lg text-sm text-goldenrod-600 dark:text-goldenrod-400 font-mono bg-parchment-50 dark:bg-night-200 border border-parchment-300 dark:border-night-50">
                    {window.location.origin}/agy/v1
                  </code>
                </div>
              </div>
            </div>

            {/* 使用说明 */}
            <div className="rounded-lg border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
              <div className="p-4 border-b border-parchment-400 dark:border-night-50">
                <h3 className="text-sm font-medium text-inkbrown-500 dark:text-sand-200">在 SillyTavern 中使用</h3>
              </div>
              <div className="p-4 text-sm text-inkbrown-300 dark:text-sand-400">
                <ol className="space-y-2 list-decimal list-inside">
                  <li>打开 SillyTavern 连接设置</li>
                  <li>选择 <span className="text-wisteria-600 dark:text-wisteria-400">兼容OpenAI</span> 或 <span className="text-wisteria-600 dark:text-wisteria-400">Gemini反代</span></li>
                  <li>填入上方 API 端点和密钥</li>
                  <li>选择模型：gemini-3.0-flash / gemini-3.0-pro</li>
                </ol>
              </div>
            </div>

            {/* 提示 */}
            {!userInfo?.has_public_credentials && (
              <div className="p-4 rounded-lg border border-goldenrod-300 dark:border-goldenrod-500/50 flex items-start gap-3 bg-goldenrod-100 dark:bg-goldenrod-600/20">
                <AlertCircle size={18} className="text-goldenrod-600 dark:text-goldenrod-400 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-sm text-goldenrod-600 dark:text-goldenrod-400">
                    未上传凭证，调用频率限制为 {rpmConfig.base} 次/分钟
                  </div>
                  <div className="text-xs text-goldenrod-500 dark:text-goldenrod-500 mt-1">
                    上传凭证可提升至 {rpmConfig.contributor} 次/分钟
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 底部 */}
      <footer className="py-4 mt-8">
        <div className="max-w-5xl mx-auto px-4 text-center">
          <a
            href="https://github.com/mzrodyu/CatieCli"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-inkbrown-200 dark:text-sand-600 hover:text-wisteria-500 dark:hover:text-wisteria-400 flex items-center justify-center gap-2 transition-colors"
          >
            <Github size={14} />
            改自：https://github.com/mzrodyu/CatieCli
          </a>
        </div>
      </footer>

      {/* ========== 弹窗 ========== */}

      {/* 导出格式选择 */}
      {exportModal && (
        <div className="fixed inset-0 bg-inkbrown-700/60 dark:bg-night-500/80 flex items-center justify-center z-50 backdrop-blur-sm">
          <div className="rounded-lg p-5 max-w-sm w-full mx-4 border border-parchment-400 dark:border-night-50 bg-parchment-100 dark:bg-night-100">
            <h3 className="text-base font-medium mb-3 text-inkbrown-500 dark:text-sand-200">导出格式</h3>
            <p className="text-xs text-inkbrown-300 dark:text-sand-500 mb-4">{exportModal.email}</p>
            <div className="space-y-2">
              <button
                onClick={() => exportAgyCred("full")}
                className="w-full p-3 rounded-lg text-left bg-wisteria-100 dark:bg-wisteria-600/20 text-wisteria-600 dark:text-wisteria-400 border border-wisteria-300 dark:border-wisteria-500/50 hover:bg-wisteria-200 dark:hover:bg-wisteria-600/30 transition-all"
              >
                <div className="text-sm font-medium">完整格式</div>
                <div className="text-xs text-wisteria-500 dark:text-wisteria-500 mt-1">包含全部字段</div>
              </button>
              <button
                onClick={() => exportAgyCred("simple")}
                className="w-full p-3 rounded-lg text-left bg-goldenrod-100 dark:bg-goldenrod-600/20 text-goldenrod-600 dark:text-goldenrod-400 border border-goldenrod-300 dark:border-goldenrod-500/50 hover:bg-goldenrod-200 dark:hover:bg-goldenrod-600/30 transition-all"
              >
                <div className="text-sm font-medium">简化格式</div>
                <div className="text-xs text-goldenrod-500 dark:text-goldenrod-500 mt-1">仅 email + refresh_token</div>
              </button>
            </div>
            <button
              onClick={() => setExportModal(null)}
              className="w-full mt-3 p-2.5 rounded-lg text-sm text-inkbrown-400 dark:text-sand-400 hover:text-inkbrown-600 dark:hover:text-sand-200 bg-parchment-200 dark:bg-night-50 border border-parchment-400 dark:border-night-50 hover:border-parchment-500 dark:hover:border-sand-700 transition-all"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* CLI 检测结果 */}
      {verifyResult && (
        <div className="fixed inset-0 bg-inkbrown-700/60 dark:bg-night-500/80 flex items-center justify-center z-50 backdrop-blur-sm">
          <div className="rounded-lg w-full max-w-md mx-4 border border-parchment-400 dark:border-night-50 overflow-hidden bg-parchment-100 dark:bg-night-100">
            <div className="p-4 border-b border-parchment-400 dark:border-night-50 flex items-center justify-between">
              <h3 className="text-base font-medium flex items-center gap-2 text-inkbrown-500 dark:text-sand-200">
                <CheckCircle className={verifyResult.is_valid ? "text-jade-500 dark:text-jade-400" : "text-cinnabar-500 dark:text-cinnabar-400"} size={18} />
                检测结果
              </h3>
              <button onClick={() => setVerifyResult(null)} className="text-inkbrown-300 dark:text-sand-500 hover:text-inkbrown-500 dark:hover:text-sand-300">
                <X size={16} />
              </button>
            </div>
            <div className="p-4 space-y-3">
              <div className="text-sm text-inkbrown-400 dark:text-sand-400">{verifyResult.email}</div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-inkbrown-300 dark:text-sand-500">状态</span>
                <span className={`text-xs px-2 py-0.5 rounded ${verifyResult.is_valid ? 'bg-jade-100 dark:bg-jade-600/20 text-jade-600 dark:text-jade-400' : 'bg-cinnabar-100 dark:bg-cinnabar-600/20 text-cinnabar-600 dark:text-cinnabar-400'}`}>
                  {verifyResult.is_valid ? "有效" : "无效"}
                </span>
              </div>
              {verifyResult.error && (
                <div className="p-3 rounded-lg border text-xs text-cinnabar-600 dark:text-cinnabar-400 bg-cinnabar-100 dark:bg-cinnabar-600/20 border-cinnabar-300 dark:border-cinnabar-500/50">
                  {verifyResult.error}
                </div>
              )}
            </div>
            <div className="p-4 border-t border-parchment-400 dark:border-night-50 flex justify-end">
              <button onClick={() => setVerifyResult(null)} className="px-4 py-2 text-sm text-inkbrown-500 dark:text-sand-400 hover:text-inkbrown-600 dark:hover:text-sand-200 bg-parchment-200 dark:bg-night-50 border border-parchment-400 dark:border-night-50 rounded-lg transition-all">
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AGY 检测结果 */}
      {agyVerifyResult && (
        <div className="fixed inset-0 bg-inkbrown-700/60 dark:bg-night-500/80 flex items-center justify-center z-50 backdrop-blur-sm">
          <div className="rounded-lg w-full max-w-md mx-4 border border-parchment-400 dark:border-night-50 overflow-hidden bg-parchment-100 dark:bg-night-100">
            <div className="p-4 border-b border-parchment-400 dark:border-night-50 flex items-center justify-between">
              <h3 className="text-base font-medium flex items-center gap-2 text-inkbrown-500 dark:text-sand-200">
                {agyVerifyResult.is_project_id_refresh ? (
                  <RefreshCw className={agyVerifyResult.is_valid ? "text-jade-500 dark:text-jade-400" : "text-cinnabar-500 dark:text-cinnabar-400"} size={18} />
                ) : (
                  <CheckCircle className={agyVerifyResult.is_valid ? "text-jade-500 dark:text-jade-400" : "text-cinnabar-500 dark:text-cinnabar-400"} size={18} />
                )}
                {agyVerifyResult.is_project_id_refresh ? "刷新 Project ID 结果" : "检测结果"}
              </h3>
              <button onClick={() => setAgyVerifyResult(null)} className="text-inkbrown-300 dark:text-sand-500 hover:text-inkbrown-500 dark:hover:text-sand-300">
                <X size={16} />
              </button>
            </div>
            <div className="p-4 space-y-3">
              <div className="text-sm text-inkbrown-400 dark:text-sand-400">{agyVerifyResult.email}</div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-inkbrown-300 dark:text-sand-500">状态</span>
                <span className={`text-xs px-2 py-0.5 rounded ${agyVerifyResult.is_valid ? 'bg-jade-100 dark:bg-jade-600/20 text-jade-600 dark:text-jade-400' : 'bg-cinnabar-100 dark:bg-cinnabar-600/20 text-cinnabar-600 dark:text-cinnabar-400'}`}>
                  {agyVerifyResult.is_project_id_refresh
                    ? agyVerifyResult.is_valid
                      ? "刷新成功"
                      : "刷新失败"
                    : agyVerifyResult.is_valid
                      ? "有效"
                      : "无效"}
                </span>
              </div>
              {agyVerifyResult.project_id && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-inkbrown-300 dark:text-sand-500">Project ID</span>
                  <span className="text-xs px-2 py-0.5 rounded bg-goldenrod-100 dark:bg-goldenrod-600/20 text-goldenrod-600 dark:text-goldenrod-400 truncate max-w-[180px]">
                    {agyVerifyResult.project_id}
                  </span>
                </div>
              )}
              {agyVerifyResult.is_project_id_refresh && agyVerifyResult.old_project_id && agyVerifyResult.is_valid && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-inkbrown-300 dark:text-sand-500">旧 ID</span>
                  <span className="text-xs px-2 py-0.5 rounded bg-parchment-300 dark:bg-night-50 text-inkbrown-300 dark:text-sand-600 line-through truncate max-w-[180px]">
                    {agyVerifyResult.old_project_id}
                  </span>
                </div>
              )}
              {agyVerifyResult.error && (
                <div className="p-3 rounded-lg border text-xs text-cinnabar-600 dark:text-cinnabar-400 bg-cinnabar-100 dark:bg-cinnabar-600/20 border-cinnabar-300 dark:border-cinnabar-500/50">
                  {agyVerifyResult.error}
                </div>
              )}
            </div>
            <div className="p-4 border-t border-parchment-400 dark:border-night-50 flex justify-end">
              <button onClick={() => setAgyVerifyResult(null)} className="px-4 py-2 text-sm text-inkbrown-500 dark:text-sand-400 hover:text-inkbrown-600 dark:hover:text-sand-200 bg-parchment-200 dark:bg-night-50 border border-parchment-400 dark:border-night-50 rounded-lg transition-all">
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AGY 额度弹窗 - 分类显示 */}
      {agyQuotaResult && (
        <div className="fixed inset-0 bg-inkbrown-700/60 dark:bg-night-500/80 flex items-center justify-center z-50 backdrop-blur-sm">
          <div className="rounded-lg w-full max-w-2xl mx-4 border border-parchment-400 dark:border-night-50 overflow-hidden max-h-[80vh] bg-parchment-100 dark:bg-night-100">
            <div className="p-4 border-b border-parchment-400 dark:border-night-50 flex items-center justify-between">
              <h3 className="text-base font-medium flex items-center gap-2 text-goldenrod-600 dark:text-goldenrod-400">
                <BarChart2 size={18} />
                额度信息详情
              </h3>
              <button onClick={() => setAgyQuotaResult(null)} className="text-inkbrown-300 dark:text-sand-500 hover:text-inkbrown-500 dark:hover:text-sand-300">
                <X size={16} />
              </button>
            </div>
            <div className="p-4 overflow-y-auto max-h-[60vh]">
              {/* 凭证名称 */}
              <div className="text-sm text-inkbrown-400 dark:text-sand-400 mb-4 bg-indigo-100 dark:bg-indigo-600/20 border border-indigo-300 dark:border-indigo-500/50 rounded-lg p-2">
                文件: {agyQuotaResult.filename || agyQuotaResult.email}
              </div>
              
              {agyQuotaResult.success ? (
                <>
                  {Object.keys(agyQuotaResult.models || {}).length > 0 ? (
                    (() => {
                      const categorizeModel = (modelId) => {
                        const lower = modelId.toLowerCase();
                        if (lower.includes("claude")) return "Claude";
                        if (
                          lower.includes("gemini-3") ||
                          lower.includes("3-pro") ||
                          lower.includes("3-flash")
                        )
                          return "Gemini 3.0";
                        if (
                          lower.includes("gemini-2.5") ||
                          lower.includes("2.5-")
                        )
                          return null;
                        if (
                          lower.includes("gpt-oss") ||
                          lower.includes("gpt_oss")
                        )
                          return "GPT-OSS";
                        if (
                          lower.includes("chat_") ||
                          lower.includes("rev") ||
                          lower.includes("tab_") ||
                          lower.includes("uic")
                        )
                          return null;
                        return "其他";
                      };

                      const categories = {
                        Claude: { color: "wisteria", icon: "🟣", models: [] },
                        "Gemini 3.0": { color: "indigo", icon: "🔵", models: [] },
                        "GPT-OSS": { color: "goldenrod", icon: "🟠", models: [] },
                        其他: { color: "parchment", icon: "⚪", models: [] },
                      };

                      Object.entries(agyQuotaResult.models).forEach(
                        ([modelId, data]) => {
                          const category = categorizeModel(modelId);
                          if (category && categories[category]) {
                            categories[category].models.push({ modelId, data });
                          }
                        },
                      );

                      const categoryColors = {
                        Claude: "border-wisteria-300 dark:border-wisteria-500/50 bg-wisteria-100 dark:bg-wisteria-600/20",
                        "Gemini 3.0": "border-indigo-300 dark:border-indigo-500/50 bg-indigo-100 dark:bg-indigo-600/20",
                        "GPT-OSS": "border-goldenrod-300 dark:border-goldenrod-500/50 bg-goldenrod-100 dark:bg-goldenrod-600/20",
                        其他: "border-parchment-400 dark:border-night-50 bg-parchment-200 dark:bg-night-50",
                      };

                      return (
                        <div className="space-y-4">
                          {Object.entries(categories).map(
                            ([catName, catData]) => {
                              if (catData.models.length === 0) return null;
                              return (
                                <div
                                  key={catName}
                                  className={`rounded-lg border p-3 ${categoryColors[catName]}`}
                                >
                                  <div className="text-sm font-medium mb-3 flex items-center gap-2 text-inkbrown-500 dark:text-sand-200">
                                    <span>{catData.icon}</span>
                                    <span>{catName}</span>
                                    <span className="text-xs text-inkbrown-300 dark:text-sand-500">
                                      ({catData.models.length})
                                    </span>
                                  </div>
                                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                                    {catData.models.map(({ modelId, data }) => {
                                      const remaining = data.remaining || 0;
                                      const colorClass =
                                        remaining >= 80
                                          ? "bg-jade-500"
                                          : remaining >= 40
                                            ? "bg-goldenrod-400"
                                            : remaining >= 20
                                              ? "bg-goldenrod-500"
                                              : "bg-cinnabar-500";
                                      const textColor =
                                        remaining >= 80
                                          ? "text-jade-600 dark:text-jade-400"
                                          : remaining >= 40
                                            ? "text-goldenrod-500 dark:text-goldenrod-400"
                                            : remaining >= 20
                                              ? "text-goldenrod-600 dark:text-goldenrod-400"
                                              : "text-cinnabar-600 dark:text-cinnabar-400";
                                      const shortName = modelId
                                        .replace("gemini-", "")
                                        .replace("claude-", "")
                                        .replace("-thinking", "");
                                      return (
                                        <div
                                          key={modelId}
                                          className="rounded p-2 bg-parchment-50 dark:bg-night-200 border border-parchment-300 dark:border-night-50"
                                        >
                                          <div
                                            className="text-xs text-inkbrown-300 dark:text-sand-500 truncate mb-1"
                                            title={modelId}
                                          >
                                            {shortName}
                                          </div>
                                          <div className="flex items-center gap-2">
                                            <div className="flex-1 bg-parchment-300 dark:bg-night-50 rounded-full h-1.5">
                                              <div
                                                className={`h-1.5 rounded-full ${colorClass}`}
                                                style={{ width: `${Math.min(remaining, 100)}%` }}
                                              />
                                            </div>
                                            <span className={`text-xs font-medium ${textColor}`}>
                                              {remaining.toFixed(0)}%
                                            </span>
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                </div>
                              );
                            },
                          )}
                        </div>
                      );
                    })()
                  ) : (
                    <div className="text-center py-8 text-inkbrown-300 dark:text-sand-500 text-sm">
                      暂无额度数据
                    </div>
                  )}
                </>
              ) : (
                <div className="p-4 rounded-lg border border-cinnabar-300 dark:border-cinnabar-500/50 bg-cinnabar-100 dark:bg-cinnabar-600/20 text-cinnabar-600 dark:text-cinnabar-400 text-sm">
                  {agyQuotaResult.error || "获取额度失败"}
                </div>
              )}
            </div>
            <div className="p-4 border-t border-parchment-400 dark:border-night-50 flex justify-end">
              <button onClick={() => setAgyQuotaResult(null)} className="px-4 py-2 text-sm text-inkbrown-500 dark:text-sand-400 hover:text-inkbrown-600 dark:hover:text-sand-200 bg-parchment-200 dark:bg-night-50 border border-parchment-400 dark:border-night-50 rounded-lg transition-all">
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
