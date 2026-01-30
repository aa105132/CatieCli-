import {
  ArrowLeft,
  CheckCircle,
  Download,
  ExternalLink,
  Key,
  RefreshCw,
  Shield,
  Trash2,
  Upload,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useState, useRef } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import { useAuth } from "../App";

export default function CodexCredentials() {
  const { user } = useAuth();
  const [credentials, setCredentials] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState({ type: "", text: "" });
  const [verifyResult, setVerifyResult] = useState(null);
  const [stats, setStats] = useState(null);
  const [verifying, setVerifying] = useState(null);
  const [refreshing, setRefreshing] = useState(null);
  
  // OAuth 状态
  const [oauthState, setOauthState] = useState(null);
  const [callbackUrl, setCallbackUrl] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [processing, setProcessing] = useState(false);
  
  // 文件上传
  const fileInputRef = useRef(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    fetchCredentials();
    fetchStats();
  }, []);

  const fetchCredentials = async () => {
    setLoading(true);
    try {
      const res = await api.get("/api/codex/credentials");
      setCredentials(res.data);
    } catch (err) {
      setMessage({ type: "error", text: "获取凭证失败" });
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const res = await api.get("/api/codex/stats");
      setStats(res.data);
    } catch (err) {
      console.error("获取统计失败", err);
    }
  };

  // OAuth 授权流程
  const startOAuth = async () => {
    try {
      const res = await api.get("/api/codex-oauth/auth-url");
      setOauthState(res.data);
      // 在新窗口打开授权链接
      window.open(res.data.auth_url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setMessage({
        type: "error",
        text: err.response?.data?.detail || "获取授权链接失败",
      });
    }
  };

  const submitCallback = async () => {
    if (!callbackUrl.trim()) {
      setMessage({ type: "error", text: "请输入回调 URL" });
      return;
    }
    
    setProcessing(true);
    try {
      const res = await api.post("/api/codex-oauth/from-callback-url", {
        callback_url: callbackUrl,
        is_public: isPublic,
      });
      
      setMessage({ type: "success", text: res.data.message });
      setOauthState(null);
      setCallbackUrl("");
      fetchCredentials();
      fetchStats();
    } catch (err) {
      setMessage({
        type: "error",
        text: err.response?.data?.detail || "处理失败",
      });
    } finally {
      setProcessing(false);
    }
  };

  // 文件上传
  const handleFileUpload = async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    
    setUploading(true);
    const formData = new FormData();
    for (const file of files) {
      formData.append("files", file);
    }
    formData.append("is_public", isPublic);
    
    try {
      const res = await api.post("/api/codex/credentials/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      
      setMessage({
        type: "success",
        text: `上传完成：${res.data.success_count}/${res.data.total_count} 成功`,
      });
      fetchCredentials();
      fetchStats();
    } catch (err) {
      setMessage({
        type: "error",
        text: err.response?.data?.detail || "上传失败",
      });
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const togglePublic = async (id, currentPublic) => {
    try {
      await api.patch(`/api/codex/credentials/${id}`, null, {
        params: { is_public: !currentPublic },
      });
      fetchCredentials();
    } catch (err) {
      setMessage({
        type: "error",
        text: err.response?.data?.detail || "操作失败",
      });
    }
  };

  const toggleActive = async (id, currentActive) => {
    try {
      await api.patch(`/api/codex/credentials/${id}`, null, {
        params: { is_active: !currentActive },
      });
      fetchCredentials();
    } catch (err) {
      setMessage({ type: "error", text: "操作失败" });
    }
  };

  const deleteCred = async (id) => {
    if (!confirm("确定删除此凭证？此操作不可恢复！")) return;
    try {
      await api.delete(`/api/codex/credentials/${id}`);
      setMessage({ type: "success", text: "删除成功" });
      fetchCredentials();
      fetchStats();
    } catch (err) {
      setMessage({ type: "error", text: "删除失败" });
    }
  };

  const verifyCred = async (id, email) => {
    setVerifying(id);
    try {
      const res = await api.post(`/api/codex/credentials/${id}/verify`);
      setVerifyResult({ ...res.data, email });
      fetchCredentials();
    } catch (err) {
      setVerifyResult({
        error: err.response?.data?.detail || err.message,
        is_valid: false,
        email,
      });
    } finally {
      setVerifying(null);
    }
  };

  const refreshToken = async (id, email) => {
    setRefreshing(id);
    try {
      const res = await api.post(`/api/codex/credentials/${id}/refresh`);
      setMessage({ type: "success", text: `Token 刷新成功: ${email}` });
      fetchCredentials();
    } catch (err) {
      setMessage({
        type: "error",
        text: err.response?.data?.detail || "Token 刷新失败",
      });
    } finally {
      setRefreshing(null);
    }
  };

  const exportCred = async (id, email) => {
    try {
      const res = await api.get(`/api/codex/credentials/${id}/export`);
      const blob = new Blob([JSON.stringify(res.data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `codex_${email || id}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setMessage({ type: "success", text: "凭证已导出！" });
    } catch (err) {
      setMessage({
        type: "error",
        text: "导出失败: " + (err.response?.data?.detail || err.message),
      });
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-4 md:p-8">
      <div className="max-w-5xl mx-auto">
        {/* 头部 */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Link
              to="/dashboard"
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-2xl font-bold flex items-center gap-2">
                <Zap className="w-6 h-6 text-green-400" />
                OpenAI Codex 凭证管理
              </h1>
              <p className="text-sm text-gray-400 mt-1">
                管理您的 OpenAI Codex OAuth 凭证
              </p>
            </div>
          </div>
        </div>

        {/* 消息提示 */}
        {message.text && (
          <div
            className={`mb-4 p-3 rounded-lg flex items-center justify-between ${
              message.type === "error"
                ? "bg-red-900/50 text-red-200"
                : "bg-green-900/50 text-green-200"
            }`}
          >
            <span>{message.text}</span>
            <button onClick={() => setMessage({ type: "", text: "" })}>
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* 统计卡片 */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-gray-800 rounded-xl p-4">
              <div className="text-2xl font-bold text-green-400">
                {stats.user_credentials}
              </div>
              <div className="text-sm text-gray-400">我的凭证</div>
            </div>
            <div className="bg-gray-800 rounded-xl p-4">
              <div className="text-2xl font-bold text-blue-400">
                {stats.public_pool_count}
              </div>
              <div className="text-sm text-gray-400">公共池凭证</div>
            </div>
            <div className="bg-gray-800 rounded-xl p-4">
              <div className="text-2xl font-bold text-yellow-400">
                {stats.today_usage}
              </div>
              <div className="text-sm text-gray-400">今日使用</div>
            </div>
            <div className="bg-gray-800 rounded-xl p-4">
              <div className="text-2xl font-bold text-purple-400">
                {stats.quota_remaining}/{stats.quota}
              </div>
              <div className="text-sm text-gray-400">剩余配额</div>
            </div>
          </div>
        )}

        {/* OAuth 授权区域 */}
        <div className="bg-gray-800 rounded-xl p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Key className="w-5 h-5 text-green-400" />
            获取 OpenAI Codex 凭证
          </h2>
          
          {!oauthState ? (
            <div className="space-y-4">
              <p className="text-gray-400 text-sm">
                通过 OpenAI OAuth 登录获取 Codex 凭证。点击下方按钮后，在新窗口完成 OpenAI 登录，
                然后将回调 URL 粘贴到下方输入框。
              </p>
              
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={isPublic}
                    onChange={(e) => setIsPublic(e.target.checked)}
                    className="rounded border-gray-600 bg-gray-700"
                  />
                  <span>捐赠到公共池（获得额外配额）</span>
                </label>
              </div>
              
              <div className="flex gap-4">
                <button
                  onClick={startOAuth}
                  className="px-6 py-2 bg-green-600 hover:bg-green-500 rounded-lg font-medium flex items-center gap-2 transition-colors"
                >
                  <ExternalLink className="w-4 h-4" />
                  开始 OAuth 授权
                </button>
                
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  className="px-6 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg font-medium flex items-center gap-2 transition-colors"
                >
                  <Upload className="w-4 h-4" />
                  {uploading ? "上传中..." : "上传凭证文件"}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".json"
                  multiple
                  onChange={handleFileUpload}
                  className="hidden"
                />
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="p-4 bg-gray-700/50 rounded-lg">
                <p className="text-sm text-gray-300 mb-2">
                  1. 在新窗口完成 OpenAI 登录
                </p>
                <p className="text-sm text-gray-300 mb-2">
                  2. 登录后浏览器会跳转到 localhost:1455/...
                </p>
                <p className="text-sm text-gray-300 mb-4">
                  3. 将完整的回调 URL 粘贴到下方输入框
                </p>
                
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={callbackUrl}
                    onChange={(e) => setCallbackUrl(e.target.value)}
                    placeholder="http://localhost:1455/auth/callback?code=..."
                    className="flex-1 px-4 py-2 bg-gray-800 border border-gray-600 rounded-lg text-sm focus:outline-none focus:border-green-500"
                  />
                  <button
                    onClick={submitCallback}
                    disabled={processing || !callbackUrl.trim()}
                    className="px-6 py-2 bg-green-600 hover:bg-green-500 disabled:bg-gray-600 rounded-lg font-medium transition-colors"
                  >
                    {processing ? "处理中..." : "提交"}
                  </button>
                </div>
              </div>
              
              <button
                onClick={() => setOauthState(null)}
                className="text-sm text-gray-400 hover:text-gray-200"
              >
                取消授权
              </button>
            </div>
          )}
        </div>

        {/* 凭证列表 */}
        <div className="bg-gray-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Shield className="w-5 h-5 text-blue-400" />
            我的 Codex 凭证
          </h2>
          
          {loading ? (
            <div className="text-center py-8 text-gray-400">加载中...</div>
          ) : credentials.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              暂无凭证，请通过上方 OAuth 授权或上传凭证文件添加
            </div>
          ) : (
            <div className="space-y-3">
              {credentials.map((cred) => (
                <div
                  key={cred.id}
                  className={`p-4 rounded-lg border transition-colors ${
                    cred.is_active
                      ? "bg-gray-700/50 border-gray-600"
                      : "bg-red-900/20 border-red-800/50"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-medium">{cred.email || cred.name}</span>
                        {cred.plan_type && cred.plan_type !== "free" && (
                          <span className="px-2 py-0.5 bg-green-600/30 text-green-300 rounded text-xs">
                            {cred.plan_type}
                          </span>
                        )}
                        {cred.is_public && (
                          <span className="px-2 py-0.5 bg-blue-600/30 text-blue-300 rounded text-xs">
                            公共池
                          </span>
                        )}
                        {!cred.is_active && (
                          <span className="px-2 py-0.5 bg-red-600/30 text-red-300 rounded text-xs">
                            已禁用
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-gray-400">
                        使用次数: {cred.total_requests} | 
                        最后使用: {cred.last_used_at ? new Date(cred.last_used_at).toLocaleString() : "从未"}
                      </div>
                      {cred.last_error && (
                        <div className="text-sm text-red-400 mt-1">
                          错误: {cred.last_error}
                        </div>
                      )}
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => verifyCred(cred.id, cred.email)}
                        disabled={verifying === cred.id}
                        className="p-2 rounded-lg bg-gray-600 hover:bg-gray-500 transition-colors"
                        title="验证凭证"
                      >
                        {verifying === cred.id ? (
                          <RefreshCw className="w-4 h-4 animate-spin" />
                        ) : (
                          <CheckCircle className="w-4 h-4" />
                        )}
                      </button>
                      
                      <button
                        onClick={() => refreshToken(cred.id, cred.email)}
                        disabled={refreshing === cred.id}
                        className="p-2 rounded-lg bg-gray-600 hover:bg-gray-500 transition-colors"
                        title="刷新 Token"
                      >
                        <RefreshCw className={`w-4 h-4 ${refreshing === cred.id ? "animate-spin" : ""}`} />
                      </button>
                      
                      <button
                        onClick={() => exportCred(cred.id, cred.email)}
                        className="p-2 rounded-lg bg-gray-600 hover:bg-gray-500 transition-colors"
                        title="导出凭证"
                      >
                        <Download className="w-4 h-4" />
                      </button>
                      
                      <button
                        onClick={() => togglePublic(cred.id, cred.is_public)}
                        className={`p-2 rounded-lg transition-colors ${
                          cred.is_public
                            ? "bg-blue-600 hover:bg-blue-500"
                            : "bg-gray-600 hover:bg-gray-500"
                        }`}
                        title={cred.is_public ? "取消公开" : "公开到池"}
                      >
                        <Shield className="w-4 h-4" />
                      </button>
                      
                      <button
                        onClick={() => deleteCred(cred.id)}
                        className="p-2 rounded-lg bg-red-600/50 hover:bg-red-600 transition-colors"
                        title="删除凭证"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 验证结果弹窗 */}
        {verifyResult && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-gray-800 rounded-xl p-6 max-w-md w-full mx-4">
              <h3 className="text-lg font-semibold mb-4">验证结果</h3>
              <div className="space-y-2 text-sm">
                <div>
                  <span className="text-gray-400">邮箱:</span>{" "}
                  {verifyResult.email}
                </div>
                <div>
                  <span className="text-gray-400">状态:</span>{" "}
                  <span
                    className={
                      verifyResult.is_valid ? "text-green-400" : "text-red-400"
                    }
                  >
                    {verifyResult.is_valid ? "✅ 有效" : "❌ 无效"}
                  </span>
                </div>
                {verifyResult.message && (
                  <div>
                    <span className="text-gray-400">消息:</span>{" "}
                    {verifyResult.message}
                  </div>
                )}
                {verifyResult.error && (
                  <div className="text-red-400">
                    错误: {verifyResult.error}
                  </div>
                )}
              </div>
              <button
                onClick={() => setVerifyResult(null)}
                className="mt-4 w-full py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
              >
                关闭
              </button>
            </div>
          </div>
        )}

        {/* API 使用说明 */}
        <div className="mt-6 bg-gray-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4">API 使用说明</h2>
          <div className="space-y-3 text-sm text-gray-300">
            <p>
              <strong>API 端点:</strong>{" "}
              <code className="px-2 py-1 bg-gray-700 rounded">
                {window.location.origin}/codex/v1/chat/completions
              </code>
            </p>
            <p>
              <strong>支持模型:</strong> gpt-5.2-codex, gpt-5.1-codex-mini, gpt-5.1-codex-max, gpt-5.2, gpt-5.1, gpt-5.1-codex, gpt-5-codex, gpt-5-codex-mini, gpt-5
            </p>
            <p>
              <strong>认证方式:</strong> 使用您的 API Key 作为 Bearer Token
            </p>
            <div className="p-3 bg-gray-700/50 rounded-lg">
              <pre className="text-xs overflow-x-auto">
{`curl ${window.location.origin}/codex/v1/chat/completions \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-5.2-codex",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}