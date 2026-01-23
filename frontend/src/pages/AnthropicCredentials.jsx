import {
    ArrowLeft,
    Check,
    ExternalLink,
    Key,
    Plus,
    RefreshCw,
    Trash2
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";

// 太极图标组件
const TaijiIcon = ({ className = "w-8 h-8" }) => (
  <svg viewBox="0 0 1024 1024" className={className} fill="currentColor">
    <path d="M803.4816 515.84c-1.9968 159.2576-131.712 287.744-291.456 287.744S222.5664 675.0976 220.5696 515.84c-0.0256-1.2544-0.0512-2.5088-0.0512-3.7632 0-80.4864 65.2544-145.7664 145.7408-145.7664s145.7664 65.28 145.7664 145.7664 65.2544 145.7664 145.7664 145.7664 143.6928-63.2576 145.6896-142.0032z" />
    <path d="M366.2592 512.1024m-43.8016 0a43.8016 43.8016 0 1 0 87.6032 0 43.8016 43.8016 0 1 0-87.6032 0Z" fill="#1e1e2e" />
    <path d="M220.5184 508.16c1.9968-159.2576 131.712-287.744 291.456-287.744s289.4592 128.4864 291.456 287.744c0.0256 1.2544 0.0512 2.5088 0.0512 3.7632 0 80.4864-65.2544 145.7664-145.7408 145.7664s-145.7664-65.28-145.7664-145.7664-65.2544-145.7664-145.7664-145.7664-143.6928 63.2576-145.6896 142.0032z" fill="#1e1e2e" />
    <path d="M657.7408 511.8976m-43.8016 0a43.8016 43.8016 0 1 0 87.6032 0 43.8016 43.8016 0 1 0-87.6032 0Z" />
  </svg>
);

export default function AnthropicCredentials() {
  const [credentials, setCredentials] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState({ type: "", text: "" });

  // 添加凭证
  const [showAddForm, setShowAddForm] = useState(false);
  const [newApiKey, setNewApiKey] = useState("");
  const [newRemark, setNewRemark] = useState("");
  const [adding, setAdding] = useState(false);

  // 操作状态
  const [verifying, setVerifying] = useState(null);
  const [deleting, setDeleting] = useState(null);

  useEffect(() => {
    loadCredentials();
  }, []);

  const loadCredentials = async () => {
    try {
      const res = await api.get("/api/anthropic/credentials");
      setCredentials(res.data.credentials || []);
    } catch (err) {
      setMessage({
        type: "error",
        text: "加载凭证失败: " + (err.response?.data?.detail || err.message),
      });
    } finally {
      setLoading(false);
    }
  };

  const addCredential = async () => {
    if (!newApiKey.trim()) {
      setMessage({ type: "error", text: "请输入 API Key" });
      return;
    }

    setAdding(true);
    setMessage({ type: "", text: "" });

    try {
      const formData = new FormData();
      formData.append("api_key", newApiKey.trim());
      formData.append("remark", newRemark.trim());

      await api.post("/api/anthropic/credentials", formData);
      setMessage({ type: "success", text: "API Key 添加成功！" });
      setNewApiKey("");
      setNewRemark("");
      setShowAddForm(false);
      loadCredentials();
    } catch (err) {
      setMessage({
        type: "error",
        text: "添加失败: " + (err.response?.data?.detail || err.message),
      });
    } finally {
      setAdding(false);
    }
  };

  const verifyCredential = async (id) => {
    setVerifying(id);
    try {
      const res = await api.post(`/api/anthropic/credentials/${id}/verify`);
      setMessage({
        type: res.data.success ? "success" : "error",
        text: res.data.message,
      });
      loadCredentials();
    } catch (err) {
      setMessage({
        type: "error",
        text: "验证失败: " + (err.response?.data?.detail || err.message),
      });
    } finally {
      setVerifying(null);
    }
  };

  const deleteCredential = async (id) => {
    if (!confirm("确定要删除这个 API Key 吗？")) return;

    setDeleting(id);
    try {
      await api.delete(`/api/anthropic/credentials/${id}`);
      setMessage({ type: "success", text: "已删除" });
      loadCredentials();
    } catch (err) {
      setMessage({
        type: "error",
        text: "删除失败: " + (err.response?.data?.detail || err.message),
      });
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="min-h-screen bg-dark-900 text-white">
      {/* 导航栏 */}
      <nav className="bg-dark-800 border-b border-dark-600 p-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <TaijiIcon className="w-8 h-8 text-purple-400" />
            <span className="text-xl font-bold">同尘</span>
            <span className="text-sm text-gray-500 bg-dark-700 px-2 py-0.5 rounded">
              Anthropic 凭证
            </span>
          </div>
          <Link
            to="/dashboard"
            className="text-gray-400 hover:text-white flex items-center gap-2"
          >
            <ArrowLeft size={20} />
            返回
          </Link>
        </div>
      </nav>

      <main className="max-w-4xl mx-auto p-6">
        {/* 消息提示 */}
        {message.text && (
          <div
            className={`mb-6 p-4 rounded-xl border ${
              message.type === "success"
                ? "bg-green-500/10 border-green-500/30 text-green-400"
                : "bg-red-500/10 border-red-500/30 text-red-400"
            }`}
          >
            {message.text}
          </div>
        )}

        {/* 说明卡片 */}
        <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 border border-purple-500/30 rounded-xl p-6 mb-6">
          <h2 className="text-lg font-bold text-purple-300 mb-2 flex items-center gap-2">
            <Key size={20} />
            Anthropic API 反代
          </h2>
          <p className="text-gray-300 text-sm mb-4">
            添加您的 Anthropic API Key，即可通过本站的统一端点使用 Claude 模型。
          </p>
          <div className="text-sm text-gray-400 space-y-1">
            <p>
              API Base:{" "}
              <code className="bg-dark-700 px-2 py-0.5 rounded">
                {window.location.origin}/anthropic/v1
              </code>
            </p>
            <p>
              支持模型: Claude Sonnet 4.5, Claude Haiku 4.5, Claude Opus 4.5
            </p>
          </div>
        </div>

        {/* 添加按钮 */}
        <div className="mb-6">
          {!showAddForm ? (
            <button
              onClick={() => setShowAddForm(true)}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg"
            >
              <Plus size={18} />
              添加 API Key
            </button>
          ) : (
            <div className="bg-dark-800 border border-dark-600 rounded-xl p-6">
              <h3 className="font-bold mb-4">添加 Anthropic API Key</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    API Key
                  </label>
                  <input
                    type="password"
                    value={newApiKey}
                    onChange={(e) => setNewApiKey(e.target.value)}
                    placeholder="sk-ant-..."
                    className="w-full bg-dark-700 border border-dark-500 rounded-lg px-4 py-2 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    备注（选填）
                  </label>
                  <input
                    type="text"
                    value={newRemark}
                    onChange={(e) => setNewRemark(e.target.value)}
                    placeholder="例如：个人账户"
                    className="w-full bg-dark-700 border border-dark-500 rounded-lg px-4 py-2 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={addCredential}
                    disabled={adding}
                    className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg disabled:opacity-50"
                  >
                    {adding ? (
                      <RefreshCw size={18} className="animate-spin" />
                    ) : (
                      <Check size={18} />
                    )}
                    {adding ? "添加中..." : "确认添加"}
                  </button>
                  <button
                    onClick={() => {
                      setShowAddForm(false);
                      setNewApiKey("");
                      setNewRemark("");
                    }}
                    className="px-4 py-2 bg-dark-600 hover:bg-dark-500 rounded-lg"
                  >
                    取消
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 凭证列表 */}
        <div className="bg-dark-800 border border-dark-600 rounded-xl overflow-hidden">
          <div className="p-4 border-b border-dark-600 flex justify-between items-center">
            <h3 className="font-bold">我的 API Keys</h3>
            <button
              onClick={loadCredentials}
              className="text-gray-400 hover:text-white"
            >
              <RefreshCw size={18} />
            </button>
          </div>

          {loading ? (
            <div className="p-8 text-center text-gray-500">加载中...</div>
          ) : credentials.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              暂无 API Key，点击上方按钮添加
            </div>
          ) : (
            <div className="divide-y divide-dark-600">
              {credentials.map((cred) => (
                <div
                  key={cred.id}
                  className="p-4 flex items-center justify-between"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`w-2 h-2 rounded-full ${cred.is_active ? "bg-green-500" : "bg-red-500"}`}
                      ></span>
                      <span className="font-mono text-sm text-gray-300">
                        {cred.api_key_masked}
                      </span>
                    </div>
                    <div className="text-sm text-gray-500 mt-1">
                      {cred.remark && (
                        <span className="mr-3">{cred.remark}</span>
                      )}
                      <span>使用 {cred.use_count} 次</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => verifyCredential(cred.id)}
                      disabled={verifying === cred.id}
                      className="p-2 text-gray-400 hover:text-green-400 disabled:opacity-50"
                      title="验证"
                    >
                      {verifying === cred.id ? (
                        <RefreshCw size={18} className="animate-spin" />
                      ) : (
                        <Check size={18} />
                      )}
                    </button>
                    <button
                      onClick={() => deleteCredential(cred.id)}
                      disabled={deleting === cred.id}
                      className="p-2 text-gray-400 hover:text-red-400 disabled:opacity-50"
                      title="删除"
                    >
                      {deleting === cred.id ? (
                        <RefreshCw size={18} className="animate-spin" />
                      ) : (
                        <Trash2 size={18} />
                      )}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 使用说明 */}
        <div className="mt-6 bg-dark-800 border border-dark-600 rounded-xl p-6">
          <h3 className="font-bold mb-4">使用说明</h3>
          <ol className="list-decimal list-inside text-sm text-gray-400 space-y-2">
            <li>
              前往{" "}
              <a
                href="https://console.anthropic.com/settings/keys"
                target="_blank"
                rel="noopener noreferrer"
                className="text-purple-400 hover:underline"
              >
                Anthropic Console
                <ExternalLink size={12} className="inline ml-1" />
              </a>{" "}
              创建 API Key
            </li>
            <li>复制 API Key 并添加到本页面</li>
            <li>
              在您的应用中使用 API Base:{" "}
              <code className="bg-dark-700 px-1 rounded">
                {window.location.origin}/anthropic/v1
              </code>
            </li>
            <li>使用本站的 API Key 进行认证</li>
          </ol>
        </div>
      </main>
    </div>
  );
}
