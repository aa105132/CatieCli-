import { ArrowLeft, Save, Settings as SettingsIcon, Users, Coins, Database, Bell, Globe, Code, Rocket, Terminal } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api";

export default function Settings() {
  const navigate = useNavigate();
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [activeTab, setActiveTab] = useState("basic");

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    try {
      const res = await api.get("/api/manage/config");
      setConfig(res.data);
    } catch (err) {
      if (err.response?.status === 401 || err.response?.status === 403) {
        navigate("/login");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const formData = new FormData();
      formData.append("allow_registration", config.allow_registration);
      formData.append(
        "discord_only_registration",
        config.discord_only_registration,
      );
      formData.append("discord_oauth_only", config.discord_oauth_only);
      formData.append("no_cred_quota_flash", config.no_cred_quota_flash ?? 100);
      formData.append("no_cred_quota_25pro", config.no_cred_quota_25pro ?? 50);
      formData.append("no_cred_quota_30pro", config.no_cred_quota_30pro ?? 0);
      formData.append("cred25_quota_30pro", config.cred25_quota_30pro ?? 0);
      formData.append(
        "credential_reward_quota",
        config.credential_reward_quota,
      );
      formData.append("quota_flash", config.quota_flash ?? 1000);
      formData.append("quota_25pro", config.quota_25pro ?? 500);
      formData.append("quota_30pro", config.quota_30pro ?? 300);
      formData.append("base_rpm", config.base_rpm);
      formData.append("contributor_rpm", config.contributor_rpm);
      formData.append("error_retry_count", config.error_retry_count);
      formData.append("cd_flash", config.cd_flash ?? 0);
      formData.append("cd_pro", config.cd_pro ?? 4);
      formData.append("cd_30", config.cd_30 ?? 4);
      formData.append("credential_pool_mode", config.credential_pool_mode);
      formData.append("force_donate", config.force_donate);
      formData.append("lock_donate", config.lock_donate);
      formData.append("announcement_enabled", config.announcement_enabled);
      formData.append("announcement_title", config.announcement_title || "");
      formData.append(
        "announcement_content",
        config.announcement_content || "",
      );
      formData.append(
        "announcement_read_seconds",
        config.announcement_read_seconds || 5,
      );
      formData.append("stats_quota_flash", config.stats_quota_flash ?? 0);
      formData.append("stats_quota_25pro", config.stats_quota_25pro ?? 0);
      formData.append("stats_quota_30pro", config.stats_quota_30pro ?? 0);
      formData.append("antigravity_enabled", config.antigravity_enabled);
      formData.append(
        "antigravity_system_prompt",
        config.antigravity_system_prompt || "",
      );
      formData.append(
        "antigravity_quota_enabled",
        config.antigravity_quota_enabled ?? true,
      );
      formData.append(
        "antigravity_quota_default",
        config.antigravity_quota_default ?? 100,
      );
      formData.append(
        "antigravity_quota_contributor",
        config.antigravity_quota_contributor ?? 500,
      );
      formData.append(
        "antigravity_quota_per_cred",
        config.antigravity_quota_per_cred ?? 100,
      );
      formData.append("antigravity_base_rpm", config.antigravity_base_rpm ?? 5);
      formData.append(
        "antigravity_contributor_rpm",
        config.antigravity_contributor_rpm ?? 10,
      );
      formData.append(
        "antigravity_pool_mode",
        config.antigravity_pool_mode ?? "full_shared",
      );
      formData.append(
        "banana_quota_enabled",
        config.banana_quota_enabled ?? true,
      );
      formData.append(
        "banana_quota_default",
        config.banana_quota_default ?? 50,
      );
      formData.append(
        "banana_quota_per_cred",
        config.banana_quota_per_cred ?? 50,
      );
      formData.append(
        "oauth_guide_enabled",
        config.oauth_guide_enabled ?? true,
      );
      formData.append("oauth_guide_seconds", config.oauth_guide_seconds ?? 8);
      formData.append("help_link_enabled", config.help_link_enabled ?? false);
      formData.append("help_link_url", config.help_link_url || "");
      formData.append("help_link_text", config.help_link_text || "使用教程");
      formData.append("tutorial_enabled", config.tutorial_enabled ?? false);
      formData.append("tutorial_content", config.tutorial_content || "");
      formData.append(
        "tutorial_force_first_visit",
        config.tutorial_force_first_visit ?? false,
      );
      formData.append("anthropic_enabled", config.anthropic_enabled ?? false);
      formData.append(
        "anthropic_quota_enabled",
        config.anthropic_quota_enabled ?? false,
      );
      formData.append(
        "anthropic_quota_default",
        config.anthropic_quota_default ?? 100,
      );
      formData.append("anthropic_base_rpm", config.anthropic_base_rpm ?? 10);
      formData.append("stats_timezone", config.stats_timezone ?? "server");
      formData.append("allow_export_credentials", config.allow_export_credentials ?? true);
      // Codex 配置
      formData.append("codex_enabled", config.codex_enabled ?? true);
      formData.append("codex_quota_enabled", config.codex_quota_enabled ?? true);
      formData.append("codex_quota_default", config.codex_quota_default ?? 0);
      formData.append("codex_quota_per_cred", config.codex_quota_per_cred ?? 200);
      formData.append("codex_quota_plus", config.codex_quota_plus ?? 150);
      formData.append("codex_quota_pro", config.codex_quota_pro ?? 300);
      formData.append("codex_quota_team", config.codex_quota_team ?? 250);
      formData.append("codex_base_rpm", config.codex_base_rpm ?? 5);
      formData.append("codex_contributor_rpm", config.codex_contributor_rpm ?? 10);
      formData.append("codex_pool_mode", config.codex_pool_mode ?? "full_shared");

      await api.post("/api/manage/config", formData);
      setMessage({ type: "success", text: "配置已保存！" });
      // 保存成功后滚动到顶部
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setMessage({
        type: "error",
        text: err.response?.data?.detail || "保存失败",
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  const tabs = [
    { id: "basic", label: "基础设置", icon: Users },
    { id: "notice", label: "公告教程", icon: Bell },
    { id: "proxy", label: "反代服务", icon: Globe },
    { id: "cli", label: "CLI 设置", icon: Terminal },
    { id: "antigravity", label: "Antigravity", icon: Rocket },
    { id: "codex", label: "Codex 设置", icon: Code },
  ];

  return (
    <div className="min-h-screen bg-dark-900 text-white p-6">
      <div className="max-w-4xl mx-auto">
        {/* 标题栏 */}
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={() => navigate("/dashboard")}
            className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
          >
            <ArrowLeft size={24} />
          </button>
          <div className="flex items-center gap-3">
            <SettingsIcon className="text-purple-400" size={28} />
            <h1 className="text-2xl font-bold">系统配置</h1>
          </div>
        </div>

        {/* 消息提示 */}
        {message && (
          <div
            className={`p-4 rounded-lg mb-6 ${
              message.type === "success"
                ? "bg-green-600/20 text-green-400 border border-green-600/50"
                : "bg-red-600/20 text-red-400 border border-red-600/50"
            }`}
          >
            {message.text}
          </div>
        )}

        {/* 标签页导航 */}
        <div className="flex flex-wrap gap-2 mb-6 bg-gray-800/50 p-2 rounded-xl">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
                  activeTab === tab.id
                    ? "bg-purple-600 text-white shadow-lg"
                    : "text-gray-400 hover:text-white hover:bg-gray-700"
                }`}
              >
                <Icon size={18} />
                <span className="font-medium">{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* 配置区域 */}
        <div className="bg-gray-800/50 rounded-xl p-6 border border-gray-700 space-y-6">
          
          {/* 基础设置 */}
          {activeTab === "basic" && (
            <div className="space-y-6">
              <h2 className="text-xl font-bold flex items-center gap-2 text-purple-400">
                <Users size={24} />
                基础设置
              </h2>

              {/* 开放注册 */}
              <div className="flex justify-between items-center">
                <div>
                  <h3 className="font-semibold">开放注册</h3>
                  <p className="text-gray-400 text-sm">
                    允许新用户通过网页注册账号
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config?.allow_registration || false}
                    onChange={(e) =>
                      setConfig({ ...config, allow_registration: e.target.checked })
                    }
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
                </label>
              </div>

              {/* 仅 Discord Bot 注册 */}
              <div className="flex justify-between items-center">
                <div>
                  <h3 className="font-semibold">仅允许 Discord Bot 注册</h3>
                  <p className="text-gray-400 text-sm">
                    开启后只能通过 Discord Bot 注册，网页注册将被禁用
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config?.discord_only_registration || false}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        discord_only_registration: e.target.checked,
                      })
                    }
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                </label>
              </div>

              {/* 仅 Discord OAuth 注册 */}
              <div className="flex justify-between items-center">
                <div>
                  <h3 className="font-semibold">仅允许 Discord 登录注册</h3>
                  <p className="text-gray-400 text-sm">
                    开启后只能通过网页 Discord 登录注册，普通注册将被禁用
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config?.discord_oauth_only || false}
                    onChange={(e) =>
                      setConfig({ ...config, discord_oauth_only: e.target.checked })
                    }
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
                </label>
              </div>

              {/* 允许导出凭证 */}
              <div className="flex items-center justify-between bg-gray-700/50 rounded-lg px-4 py-3">
                <div>
                  <h3 className="font-semibold">允许导出凭证</h3>
                  <p className="text-gray-400 text-sm">
                    允许用户下载自己上传的凭证文件（管理员不受限）
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config?.allow_export_credentials ?? true}
                    onChange={(e) =>
                      setConfig({ ...config, allow_export_credentials: e.target.checked })
                    }
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-500"></div>
                </label>
              </div>

              {/* 统计时区设置 */}
              <div className="bg-gray-800/50 rounded-xl p-5 border border-gray-700">
                <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
                  🕐 统计时区
                </h3>
                <div>
                  <label className="text-sm text-gray-400 mb-1 block">
                    今日使用统计重置时区
                  </label>
                  <select
                    value={config?.stats_timezone ?? "server"}
                    onChange={(e) =>
                      setConfig({ ...config, stats_timezone: e.target.value })
                    }
                    className="w-full bg-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  >
                    <option value="server">服务器时区（跟随服务器系统时间）</option>
                    <option value="utc">UTC 时区（北京时间下午 4 点重置）</option>
                    <option value="utc8">
                      北京时间 UTC+8（北京时间 0 点重置）
                    </option>
                  </select>
                  <p className="text-xs text-gray-500 mt-2">
                    影响"今日使用"统计的重置时间
                  </p>
                </div>
              </div>

              {/* 错误重试（全局） */}
              <div>
                <h3 className="font-semibold mb-2">报错切换凭证重试次数 🔄</h3>
                <p className="text-gray-400 text-sm mb-3">
                  遇到 API 错误（如 404、500 等）时自动切换凭证重试的次数（全局设置，适用于所有反代服务）
                </p>
                <input
                  type="number"
                  min="0"
                  max="10"
                  value={config?.error_retry_count ?? ""}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      error_retry_count:
                        e.target.value === "" ? "" : parseInt(e.target.value),
                    })
                  }
                  className="w-32 bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <p className="text-gray-500 text-sm mt-1">
                  设为 0 则不重试，直接返回错误
                </p>
                <p className="text-blue-400 text-sm mt-2">
                  💡 当凭证请求失败时，系统会自动尝试切换到其他可用凭证重试
                </p>
              </div>
            </div>
          )}

          {/* CLI 设置 */}
          {activeTab === "cli" && (
            <div className="space-y-6">
              <h2 className="text-xl font-bold flex items-center gap-2 text-cyan-400">
                <Terminal size={24} />
                Gemini CLI 设置
              </h2>
              <p className="text-gray-500 text-sm -mt-4">
                以下配置仅适用于 Gemini CLI 凭证反代服务（/v1 路径）
              </p>

              {/* 无凭证用户按模型配额 */}
              <div>
                <h3 className="font-semibold mb-2">无凭证用户按模型配额 🔒</h3>
                <p className="text-gray-400 text-sm mb-3">
                  无凭证用户各类模型的每日配额（0 = 禁止使用该类模型）
                </p>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="text-sm text-gray-400 mb-1 block">
                      Flash 配额
                    </label>
                    <input
                      type="number"
                      value={config?.no_cred_quota_flash ?? ""}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          no_cred_quota_flash:
                            e.target.value === "" ? "" : parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-400 mb-1 block">
                      2.5 Pro 配额
                    </label>
                    <input
                      type="number"
                      value={config?.no_cred_quota_25pro ?? ""}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          no_cred_quota_25pro:
                            e.target.value === "" ? "" : parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-400 mb-1 block">
                      3.0 配额
                    </label>
                    <input
                      type="number"
                      value={config?.no_cred_quota_30pro ?? ""}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          no_cred_quota_30pro:
                            e.target.value === "" ? "" : parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-pink-500"
                    />
                  </div>
                </div>
                <p className="text-gray-500 text-sm mt-2">
                  💡 设为 0 表示禁止无凭证用户使用该类模型
                </p>
              </div>

              {/* 2.5凭证用户的3.0配额 */}
              <div>
                <h3 className="font-semibold mb-2">2.5凭证用户 3.0 配额 🎯</h3>
                <p className="text-gray-400 text-sm mb-3">
                  只有2.5凭证（无3.0凭证）的用户可使用的3.0模型配额（0 = 禁止）
                </p>
                <input
                  type="number"
                  value={config?.cred25_quota_30pro ?? ""}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      cred25_quota_30pro:
                        e.target.value === "" ? "" : parseInt(e.target.value),
                    })
                  }
                  className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <p className="text-gray-500 text-sm mt-2">
                  💡 允许2.5凭证用户体验3.0模型，设为0则只有3.0凭证用户可用
                </p>
              </div>

              {/* 凭证奖励 - 按模型分类 */}
              <div>
                <h3 className="font-semibold mb-2">凭证上传奖励额度 🎁</h3>
                <p className="text-gray-400 text-sm mb-3">
                  按模型分类的额度配置，2.5凭证=Flash+2.5Pro，3.0凭证=Flash+2.5Pro+3.0
                </p>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="text-sm text-gray-400 mb-1 block">
                      Flash 额度
                    </label>
                    <input
                      type="number"
                      value={config?.quota_flash ?? ""}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          quota_flash:
                            e.target.value === "" ? "" : parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-400 mb-1 block">
                      2.5 Pro 额度
                    </label>
                    <input
                      type="number"
                      value={config?.quota_25pro ?? ""}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          quota_25pro:
                            e.target.value === "" ? "" : parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-400 mb-1 block">
                      3.0 额度
                    </label>
                    <input
                      type="number"
                      value={config?.quota_30pro ?? ""}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          quota_30pro:
                            e.target.value === "" ? "" : parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-pink-500"
                    />
                  </div>
                </div>
                <p className="text-green-400 text-sm mt-2">
                  💡 2.5凭证 +
                  {(config?.quota_flash ?? 1000) + (config?.quota_25pro ?? 500)} |
                  3.0凭证 +
                  {(config?.quota_flash ?? 1000) +
                    (config?.quota_25pro ?? 500) +
                    (config?.quota_30pro ?? 300)}
                </p>
              </div>

              {/* 全站统计额度配置 */}
              <div>
                <h3 className="font-semibold mb-2">全站统计额度 📊</h3>
                <p className="text-gray-400 text-sm mb-3">
                  统计页面显示的每个凭证贡献的额度基数
                </p>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="text-sm text-gray-400 mb-1 block">
                      Flash 额度/凭证
                    </label>
                    <input
                      type="number"
                      value={config?.stats_quota_flash ?? ""}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          stats_quota_flash:
                            e.target.value === "" ? "" : parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-400 mb-1 block">
                      2.5 Pro 额度/凭证
                    </label>
                    <input
                      type="number"
                      value={config?.stats_quota_25pro ?? ""}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          stats_quota_25pro:
                            e.target.value === "" ? "" : parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-400 mb-1 block">
                      3.0 额度/凭证
                    </label>
                    <input
                      type="number"
                      value={config?.stats_quota_30pro ?? ""}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          stats_quota_30pro:
                            e.target.value === "" ? "" : parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-pink-500"
                    />
                  </div>
                </div>
                <p className="text-gray-500 text-sm mt-2">
                  💡 统计页显示: Flash={config?.stats_quota_flash || 1000}
                  ×活跃凭证数, 2.5Pro={config?.stats_quota_25pro || 250}×活跃凭证数,
                  3.0={config?.stats_quota_30pro || 200}×3.0凭证数
                </p>
              </div>

              {/* 分隔线 - 凭证池设置 */}
              <div className="border-t border-gray-700 pt-6 mt-6">
                <h2 className="text-xl font-bold flex items-center gap-2 text-purple-400 mb-4">
                  <Database size={24} />
                  CLI 凭证池设置
                </h2>
              </div>

              {/* 凭证池模式 */}
              <div>
                <h3 className="font-semibold mb-2">凭证池模式 🏊</h3>
                <p className="text-gray-400 text-sm mb-3">控制用户如何共享凭证</p>
                <select
                  value={config?.credential_pool_mode || "full_shared"}
                  onChange={(e) =>
                    setConfig({ ...config, credential_pool_mode: e.target.value })
                  }
                  className="w-full bg-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  <option value="private">🔒 私有模式 - 只能用自己的凭证</option>
                  <option value="tier3_shared">
                    ⚡ 3.0小锅饭 - 适合凭证较少时
                  </option>
                  <option value="full_shared">🍲 大锅饭 - 适合凭证较多时</option>
                </select>
                <div className="mt-2 text-sm space-y-1">
                  {config?.credential_pool_mode === "private" && (
                    <p className="text-yellow-400">⚠️ 用户只能使用自己上传的凭证</p>
                  )}
                  {config?.credential_pool_mode === "tier3_shared" && (
                    <>
                      <p className="text-blue-400">
                        💎 有3.0凭证 → 可用公共3.0池 + 自己的
                      </p>
                      <p className="text-cyan-400">
                        📘 无3.0凭证 → 可用公共2.5凭证
                      </p>
                    </>
                  )}
                  {config?.credential_pool_mode === "full_shared" && (
                    <>
                      <p className="text-green-400">
                        🎉 上传凭证后可使用所有公共凭证（2.5+3.0）
                      </p>
                      <p className="text-gray-400">🚫 未上传只能用自己的凭证</p>
                    </>
                  )}
                </div>
              </div>

              {/* 强制公开 */}
              <div className="flex items-center justify-between bg-gray-700/50 rounded-lg px-4 py-3">
                <div>
                  <h3 className="font-semibold">强制公开 🤝</h3>
                  <p className="text-gray-400 text-sm">
                    上传凭证时强制设为公开，不给选择
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config?.force_donate ?? false}
                    onChange={(e) =>
                      setConfig({ ...config, force_donate: e.target.checked })
                    }
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-red-500"></div>
                </label>
              </div>

              {/* 锁定公开 */}
              <div className="flex items-center justify-between bg-gray-700/50 rounded-lg px-4 py-3">
                <div>
                  <h3 className="font-semibold">锁定公开 🔒</h3>
                  <p className="text-gray-400 text-sm">
                    有效凭证不允许取消公开（失效的可以取消）
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config?.lock_donate ?? false}
                    onChange={(e) =>
                      setConfig({ ...config, lock_donate: e.target.checked })
                    }
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-red-500"></div>
                </label>
              </div>

              {/* GeminiCLI 速率限制 */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <h3 className="font-semibold mb-2">CLI 基础速率限制 ⏱️</h3>
                  <p className="text-gray-400 text-sm mb-3">
                    GeminiCLI 未上传凭证用户的每分钟请求数
                  </p>
                  <input
                    type="number"
                    value={config?.base_rpm ?? ""}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        base_rpm:
                          e.target.value === "" ? "" : parseInt(e.target.value),
                      })
                    }
                    className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                  <p className="text-gray-500 text-sm mt-1">次/分钟</p>
                </div>
                <div>
                  <h3 className="font-semibold mb-2">CLI 上传者速率限制 🚀</h3>
                  <p className="text-gray-400 text-sm mb-3">
                    GeminiCLI 上传凭证用户的每分钟请求数
                  </p>
                  <input
                    type="number"
                    value={config?.contributor_rpm ?? ""}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        contributor_rpm:
                          e.target.value === "" ? "" : parseInt(e.target.value),
                      })
                    }
                    className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                  <p className="text-gray-500 text-sm mt-1">次/分钟</p>
                </div>
              </div>

              {/* CD 机制 */}
              <div>
                <h3 className="font-semibold mb-2">凭证冷却时间 (CD) ⏱️</h3>
                <p className="text-gray-400 text-sm mb-3">
                  按模型组设置凭证冷却时间，避免同一凭证被频繁调用（0=无CD）
                </p>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="text-sm text-gray-400 mb-1 block">
                      Flash CD (秒)
                    </label>
                    <input
                      type="number"
                      min="0"
                      value={config?.cd_flash ?? 0}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          cd_flash:
                            e.target.value === "" ? 0 : parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-400 mb-1 block">
                      Pro CD (秒)
                    </label>
                    <input
                      type="number"
                      min="0"
                      value={config?.cd_pro ?? 4}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          cd_pro:
                            e.target.value === "" ? 0 : parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-400 mb-1 block">
                      3.0 CD (秒)
                    </label>
                    <input
                      type="number"
                      min="0"
                      value={config?.cd_30 ?? 4}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          cd_30:
                            e.target.value === "" ? 0 : parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-pink-500"
                    />
                  </div>
                </div>
                <p className="text-gray-500 text-sm mt-2">
                  💡 同一凭证在 CD
                  期间内不会被同模型组再次选中，优先选择已冷却的凭证
                </p>
              </div>
            </div>
          )}

          {/* 公告教程 */}
          {activeTab === "notice" && (
            <div className="space-y-6">
              <h2 className="text-xl font-bold flex items-center gap-2 text-amber-400">
                <Bell size={24} />
                公告与教程
              </h2>

              {/* 公告配置 */}
              <div className="pt-4 border-t border-gray-700">
                <div className="flex justify-between items-center mb-4">
                  <div>
                    <h3 className="font-semibold">📢 公告功能</h3>
                    <p className="text-gray-400 text-sm">向所有用户显示重要通知</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={config?.announcement_enabled || false}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          announcement_enabled: e.target.checked,
                        })
                      }
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-amber-600"></div>
                  </label>
                </div>

                {config?.announcement_enabled && (
                  <div className="space-y-4 bg-gray-700/30 rounded-lg p-4">
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        公告标题
                      </label>
                      <input
                        type="text"
                        value={config?.announcement_title || ""}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            announcement_title: e.target.value,
                          })
                        }
                        placeholder="例如：【重要通知】系统维护公告"
                        className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-amber-500"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        公告内容
                      </label>
                      <textarea
                        value={config?.announcement_content || ""}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            announcement_content: e.target.value,
                          })
                        }
                        placeholder="在这里输入公告内容，支持多行文本..."
                        rows={6}
                        className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-amber-500 resize-none"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        阅读等待时间（秒）
                      </label>
                      <input
                        type="number"
                        min="0"
                        max="60"
                        value={config?.announcement_read_seconds || 5}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            announcement_read_seconds:
                              parseInt(e.target.value) || 5,
                          })
                        }
                        className="w-32 bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-amber-500"
                      />
                      <p className="text-gray-500 text-sm mt-1">
                        用户首次阅读需等待此时间才能关闭公告
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* OAuth 操作指引弹窗 */}
              <div className="pt-4 border-t border-gray-700">
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="font-semibold">📖 OAuth 操作指引弹窗</h3>
                    <p className="text-gray-400 text-sm">
                      用户获取凭证时显示的操作指引弹窗
                    </p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={config?.oauth_guide_enabled ?? true}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          oauth_guide_enabled: e.target.checked,
                        })
                      }
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-cyan-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-500"></div>
                  </label>
                </div>
                {config?.oauth_guide_enabled && (
                  <div className="mt-4 space-y-4 pl-4 border-l-2 border-cyan-500/30">
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        倒计时等待（秒）
                      </label>
                      <input
                        type="number"
                        min="0"
                        max="30"
                        value={config?.oauth_guide_seconds ?? 8}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            oauth_guide_seconds: parseInt(e.target.value) || 0,
                          })
                        }
                        className="w-32 bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                      />
                      <p className="text-gray-500 text-sm mt-1">
                        用户需等待此时间才能关闭指引弹窗（0=可立即关闭）
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* 帮助链接 */}
              <div className="pt-4 border-t border-gray-700">
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="font-semibold">📚 帮助链接</h3>
                    <p className="text-gray-400 text-sm">
                      在侧边栏显示使用教程链接
                    </p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={config?.help_link_enabled || false}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          help_link_enabled: e.target.checked,
                        })
                      }
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
                  </label>
                </div>
                {config?.help_link_enabled && (
                  <div className="mt-4 space-y-4 pl-4 border-l-2 border-cyan-500/30">
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        链接文字
                      </label>
                      <input
                        type="text"
                        value={config?.help_link_text || "使用教程"}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            help_link_text: e.target.value,
                          })
                        }
                        placeholder="使用教程"
                        className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        链接地址
                      </label>
                      <input
                        type="url"
                        value={config?.help_link_url || ""}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            help_link_url: e.target.value,
                          })
                        }
                        placeholder="https://..."
                        className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                      />
                      <p className="text-gray-500 text-sm mt-1">
                        可设置为视频教程、文档等链接
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* 内置教程 */}
              <div className="pt-4 border-t border-gray-700">
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="font-semibold">📖 内置教程页面</h3>
                    <p className="text-gray-400 text-sm">
                      启用后用户点击教程链接将打开站内页面（优先于外链）
                    </p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={config?.tutorial_enabled || false}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          tutorial_enabled: e.target.checked,
                        })
                      }
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
                  </label>
                </div>
                {config?.tutorial_enabled && (
                  <div className="mt-4 space-y-4 pl-4 border-l-2 border-cyan-500/30">
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        教程内容（支持简单Markdown格式）
                      </label>
                      <textarea
                        value={config?.tutorial_content || ""}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            tutorial_content: e.target.value,
                          })
                        }
                        placeholder={`# 使用教程\n\n## 什么是本站？\n本站是一个 Gemini API 反向代理服务...\n\n## 如何使用？\n1. 首先，您需要...\n2. 然后，...\n\n### 注意事项\n- 不要分享您的 API Key\n- ...`}
                        rows={15}
                        className="w-full bg-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-cyan-500 font-mono text-sm"
                      />
                      <div className="flex gap-2 mt-2">
                        <button
                          type="button"
                          onClick={() =>
                            setConfig({ ...config, tutorial_content: "" })
                          }
                          className="px-3 py-1.5 bg-red-600/20 hover:bg-red-600/40 text-red-300 rounded-lg text-sm transition-colors"
                        >
                          🗑️ 清空教程
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            setConfig({
                              ...config,
                              tutorial_content: "",
                            })
                          }
                          className="px-3 py-1.5 bg-cyan-600/20 hover:bg-cyan-600/40 text-cyan-300 rounded-lg text-sm transition-colors"
                        >
                          📥 使用内置默认教程
                        </button>
                      </div>
                      <p className="text-gray-500 text-sm mt-1">
                        支持 #标题、##二级标题、###三级标题、- 列表、1.
                        数字列表。留空则使用内置默认教程。
                      </p>
                    </div>
                    <div className="flex items-center justify-between mt-4 p-3 bg-gray-800 rounded-lg">
                      <div>
                        <span className="font-medium">首次访问强制查看</span>
                        <p className="text-gray-500 text-sm">
                          新用户首次登录必须先看完教程才能使用其他功能
                        </p>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={config?.tutorial_force_first_visit || false}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              tutorial_force_first_visit: e.target.checked,
                            })
                          }
                          className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
                      </label>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 反代服务 */}
          {activeTab === "proxy" && (
            <div className="space-y-6">
              <h2 className="text-xl font-bold flex items-center gap-2 text-green-400">
                <Globe size={24} />
                反代服务配置
              </h2>

              {/* Antigravity 反代开关（简要） */}
              <div className="p-4 bg-gray-700/30 rounded-lg">
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="font-semibold">🚀 Antigravity 反代</h3>
                    <p className="text-gray-400 text-sm">
                      启用 Antigravity API 反代功能（/antigravity 路径）
                    </p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={config?.antigravity_enabled || false}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          antigravity_enabled: e.target.checked,
                        })
                      }
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
                  </label>
                </div>
                {config?.antigravity_enabled && (
                  <p className="text-green-400 text-sm mt-2">
                    ✅ 已启用 - 详细配置请切换到「Antigravity」标签页
                  </p>
                )}
              </div>

              {/* Anthropic 反代 */}
              <div className="p-4 bg-gray-700/30 rounded-lg">
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="font-semibold">🧠 Anthropic 反代</h3>
                    <p className="text-gray-400 text-sm">
                      启用 Anthropic API 反代功能（/anthropic 路径）
                    </p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={config?.anthropic_enabled || false}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          anthropic_enabled: e.target.checked,
                        })
                      }
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-pink-600"></div>
                  </label>
                </div>
                {config?.anthropic_enabled && (
                  <div className="mt-3 bg-gray-700/30 rounded-lg p-3">
                    <p className="text-gray-400 text-sm mb-2">
                      用户可添加 Anthropic API Key，通过
                      <code className="bg-dark-700 px-1 rounded mx-1">/anthropic/v1</code>
                      端点使用 Claude 模型。
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-gray-400 mb-1 block">默认配额</label>
                        <input
                          type="number"
                          min="0"
                          value={config?.anthropic_quota_default ?? 100}
                          onChange={(e) => setConfig({ ...config, anthropic_quota_default: parseInt(e.target.value) || 0 })}
                          className="w-full bg-gray-700 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-pink-500"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-400 mb-1 block">默认 RPM</label>
                        <input
                          type="number"
                          min="1"
                          value={config?.anthropic_base_rpm ?? 10}
                          onChange={(e) => setConfig({ ...config, anthropic_base_rpm: parseInt(e.target.value) || 1 })}
                          className="w-full bg-gray-700 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-pink-500"
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Codex 反代开关（简要） */}
              <div className="p-4 bg-gray-700/30 rounded-lg">
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="font-semibold">💚 Codex 反代 (OpenAI GPT)</h3>
                    <p className="text-gray-400 text-sm">
                      启用 OpenAI Codex API 反代功能（/codex 路径）
                    </p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={config?.codex_enabled === true}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          codex_enabled: e.target.checked,
                        })
                      }
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
                  </label>
                </div>
                {config?.codex_enabled && (
                  <p className="text-emerald-400 text-sm mt-2">
                    ✅ 已启用 - 详细配置请切换到「Codex 设置」标签页
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Antigravity 设置 */}
          {activeTab === "antigravity" && (
            <div className="space-y-6">
              <h2 className="text-xl font-bold flex items-center gap-2 text-green-400">
                <Rocket size={24} />
                Antigravity 设置
              </h2>

              {/* Antigravity 开关 */}
              <div className="flex justify-between items-center">
                <div>
                  <h3 className="font-semibold">启用 Antigravity 反代</h3>
                  <p className="text-gray-400 text-sm">
                    启用 Antigravity API 反代功能（/antigravity 路径）
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config?.antigravity_enabled || false}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        antigravity_enabled: e.target.checked,
                      })
                    }
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
                </label>
              </div>
              <p className="text-gray-500 text-sm">
                💡 Antigravity 使用沙盒 API 端点，支持动态模型列表获取
              </p>

              {config?.antigravity_enabled && (
                <>
                  {/* 系统提示词 */}
                  <div className="bg-gray-700/30 rounded-lg p-4">
                    <div className="flex justify-between items-center mb-2">
                      <label className="block text-sm font-medium">
                        🔧 系统提示词（用于绕过 Claude 429 限制）
                      </label>
                      <button
                        type="button"
                        onClick={() =>
                          setConfig({
                            ...config,
                            antigravity_system_prompt: `**Example of deprecated persona description (for reference only):**

You are Antigravity, a powerful agentic AI coding assistant designed by the Google Deepmind team working on Advanced Agentic Coding.

 You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question. **Proactiveness**`,
                          })
                        }
                        className="text-xs px-3 py-1 bg-gray-600 hover:bg-gray-500 rounded text-gray-300 hover:text-white transition-colors"
                      >
                        ↻ 恢复默认
                      </button>
                    </div>
                    <textarea
                      value={config?.antigravity_system_prompt || ""}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          antigravity_system_prompt: e.target.value,
                        })
                      }
                      placeholder="系统提示词，用于绕过 Claude 模型的 429 限制。建议使用默认值..."
                      rows={6}
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-green-500 resize-none text-sm"
                    />
                    <p className="text-gray-500 text-xs mt-2">
                      💡 这个提示词会自动添加到每个 Antigravity 请求的
                      systemInstruction 开头。留空可能导致 Claude 模型 429 错误。
                    </p>
                  </div>

                  {/* 凭证池模式 */}
                  <div className="bg-gray-700/30 rounded-lg p-4">
                    <label className="block text-sm font-medium mb-3">
                      🍲 Antigravity 凭证池模式
                    </label>
                    <select
                      value={config?.antigravity_pool_mode ?? "full_shared"}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          antigravity_pool_mode: e.target.value,
                        })
                      }
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-green-500"
                    >
                      <option value="private">🔒 私有模式 - 只能用自己的凭证</option>
                      <option value="full_shared">🍲 大锅饭模式 - 捐赠凭证即可用所有公共池</option>
                    </select>
                    <div className="mt-3 text-sm space-y-1">
                      {config?.antigravity_pool_mode === "private" && (
                        <p className="text-gray-400">
                          🔒 每个用户只能使用自己上传的 Antigravity 凭证
                        </p>
                      )}
                      {config?.antigravity_pool_mode === "full_shared" && (
                        <>
                          <p className="text-green-400">
                            🎉 上传凭证后可使用所有公共 Antigravity 凭证
                          </p>
                          <p className="text-gray-400">🚫 未上传只能用自己的凭证</p>
                        </>
                      )}
                    </div>
                  </div>

                  {/* 配额限制 */}
                  <div className="bg-gray-700/30 rounded-lg p-4">
                    <div className="flex justify-between items-center mb-3">
                      <div>
                        <label className="block text-sm font-medium">
                          📊 Antigravity 配额限制
                        </label>
                        <p className="text-gray-400 text-xs">
                          限制用户每日 Antigravity API 调用次数
                        </p>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={config?.antigravity_quota_enabled ?? true}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              antigravity_quota_enabled: e.target.checked,
                            })
                          }
                          className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange-600"></div>
                      </label>
                    </div>

                    {config?.antigravity_quota_enabled && (
                      <>
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="text-sm text-gray-400 mb-1 block">
                              默认配额
                            </label>
                            <input
                              type="number"
                              min="0"
                              value={config?.antigravity_quota_default ?? 100}
                              onChange={(e) =>
                                setConfig({
                                  ...config,
                                  antigravity_quota_default:
                                    parseInt(e.target.value) || 0,
                                })
                              }
                              className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500"
                            />
                            <p className="text-gray-500 text-xs mt-1">
                              普通用户每日可调用次数
                            </p>
                          </div>
                          <div>
                            <label className="text-sm text-gray-400 mb-1 block">
                              贡献者配额
                            </label>
                            <input
                              type="number"
                              min="0"
                              value={config?.antigravity_quota_contributor ?? 500}
                              onChange={(e) =>
                                setConfig({
                                  ...config,
                                  antigravity_quota_contributor:
                                    parseInt(e.target.value) || 0,
                                })
                              }
                              className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500"
                            />
                            <p className="text-gray-500 text-xs mt-1">
                              贡献凭证用户每日可调用次数（旧模式）
                            </p>
                          </div>
                        </div>
                        
                        {/* 大锅饭模式凭证奖励 */}
                        {config?.antigravity_pool_mode === "full_shared" && (
                          <div className="mt-4 p-3 border border-orange-500/30 rounded-lg bg-orange-500/5">
                            <label className="text-sm text-orange-400 mb-2 block font-medium">
                              大锅饭模式凭证奖励
                            </label>
                            <div className="grid grid-cols-2 gap-4">
                              <div>
                                <label className="text-xs text-gray-400 mb-1 block">
                                  每凭证奖励配额
                                </label>
                                <input
                                  type="number"
                                  min="0"
                                  value={config?.antigravity_quota_per_cred ?? 100}
                                  onChange={(e) =>
                                    setConfig({
                                      ...config,
                                      antigravity_quota_per_cred:
                                        parseInt(e.target.value) || 0,
                                    })
                                  }
                                  className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500"
                                />
                              </div>
                              <div className="flex items-end pb-2">
                                <p className="text-gray-400 text-xs">
                                  公式：基础配额 + (公开凭证数 × 此值)
                                </p>
                              </div>
                            </div>
                            <p className="text-green-400 text-xs mt-2">
                              示例：基础 {config?.antigravity_quota_default || 100} + 3凭证 × {config?.antigravity_quota_per_cred || 100} = {(config?.antigravity_quota_default || 100) + 3 * (config?.antigravity_quota_per_cred || 100)} 次/日
                            </p>
                          </div>
                        )}
                      </>
                    )}
                  </div>

                  {/* Banana 额度配置 */}
                  <div className="bg-gray-700/30 rounded-lg p-4">
                    <div className="flex justify-between items-center mb-3">
                      <div>
                        <label className="text-sm font-medium block">
                          🍌 Banana 额度限制
                        </label>
                        <p className="text-gray-400 text-xs mt-1">
                          限制 image 模型每日调用次数（agy-gemini-3-pro-image 系列）
                        </p>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={config?.banana_quota_enabled ?? true}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              banana_quota_enabled: e.target.checked,
                            })
                          }
                          className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-yellow-600"></div>
                      </label>
                    </div>
                    
                    {config?.banana_quota_enabled && (
                      <>
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="text-xs text-gray-400 mb-1 block">
                              默认配额
                            </label>
                            <input
                              type="number"
                              min="0"
                              value={config?.banana_quota_default ?? 50}
                              onChange={(e) =>
                                setConfig({
                                  ...config,
                                  banana_quota_default:
                                    parseInt(e.target.value) || 0,
                                })
                              }
                              className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-yellow-500"
                            />
                            <p className="text-gray-500 text-xs mt-1">
                              普通用户每日可调用次数
                            </p>
                          </div>
                          <div>
                            <label className="text-xs text-gray-400 mb-1 block">
                              每凭证奖励配额
                            </label>
                            <input
                              type="number"
                              min="0"
                              value={config?.banana_quota_per_cred ?? 50}
                              onChange={(e) =>
                                setConfig({
                                  ...config,
                                  banana_quota_per_cred:
                                    parseInt(e.target.value) || 0,
                                })
                              }
                              className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-yellow-500"
                            />
                            <p className="text-gray-500 text-xs mt-1">
                              每个公开凭证奖励额度
                            </p>
                          </div>
                        </div>
                        <p className="text-yellow-400 text-xs mt-3">
                          示例：基础 {config?.banana_quota_default || 50} + 3凭证 × {config?.banana_quota_per_cred || 50} = {(config?.banana_quota_default || 50) + 3 * (config?.banana_quota_per_cred || 50)} 次/日
                        </p>
                      </>
                    )}
                  </div>

                  {/* 速率限制 */}
                  <div className="bg-gray-700/30 rounded-lg p-4">
                    <label className="block text-sm font-medium mb-3">
                      ⏱️ Antigravity 速率限制 (RPM)
                    </label>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="text-sm text-gray-400 mb-1 block">
                          基础 RPM
                        </label>
                        <input
                          type="number"
                          min="1"
                          value={config?.antigravity_base_rpm ?? 5}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              antigravity_base_rpm: parseInt(e.target.value) || 1,
                            })
                          }
                          className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-green-500"
                        />
                        <p className="text-gray-500 text-xs mt-1">
                          未贡献凭证用户每分钟请求数
                        </p>
                      </div>
                      <div>
                        <label className="text-sm text-gray-400 mb-1 block">
                          贡献者 RPM
                        </label>
                        <input
                          type="number"
                          min="1"
                          value={config?.antigravity_contributor_rpm ?? 10}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              antigravity_contributor_rpm:
                                parseInt(e.target.value) || 1,
                            })
                          }
                          className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-green-500"
                        />
                        <p className="text-gray-500 text-xs mt-1">
                          贡献凭证用户每分钟请求数
                        </p>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Codex 设置 */}
          {activeTab === "codex" && (
            <div className="space-y-6">
              <h2 className="text-xl font-bold flex items-center gap-2 text-emerald-400">
                <Code size={24} />
                Codex 设置 (OpenAI GPT)
              </h2>

              {/* Codex 开关 */}
              <div className="flex justify-between items-center">
                <div>
                  <h3 className="font-semibold">启用 Codex 反代</h3>
                  <p className="text-gray-400 text-sm">
                    启用 OpenAI Codex API 反代功能（/codex 路径）
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config?.codex_enabled === true}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        codex_enabled: e.target.checked,
                      })
                    }
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
                </label>
              </div>

              {config?.codex_enabled && (
                <>
                  {/* 凭证池模式 */}
                  <div className="bg-gray-700/30 rounded-lg p-4">
                    <label className="block text-sm font-medium mb-3">
                      🍲 Codex 凭证池模式
                    </label>
                    <select
                      value={config?.codex_pool_mode ?? "full_shared"}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          codex_pool_mode: e.target.value,
                        })
                      }
                      className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    >
                      <option value="private">🔒 私有模式 - 只能用自己的凭证</option>
                      <option value="full_shared">🍲 大锅饭模式 - 捐赠凭证即可用所有公共池</option>
                    </select>
                    <div className="mt-3 text-sm space-y-1">
                      {config?.codex_pool_mode === "private" && (
                        <p className="text-gray-400">
                          🔒 每个用户只能使用自己的 ChatGPT 凭证
                        </p>
                      )}
                      {config?.codex_pool_mode === "full_shared" && (
                        <>
                          <p className="text-emerald-400">
                            🎉 上传凭证后可使用所有公共 Codex 凭证
                          </p>
                          <p className="text-gray-400">🚫 未上传只能用自己的凭证</p>
                        </>
                      )}
                    </div>
                  </div>

                  {/* 配额限制 */}
                  <div className="bg-gray-700/30 rounded-lg p-4">
                    <div className="flex justify-between items-center mb-3">
                      <div>
                        <label className="block text-sm font-medium">
                          📊 Codex 配额限制
                        </label>
                        <p className="text-gray-400 text-xs">
                          限制用户每日 Codex API 调用次数
                        </p>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={config?.codex_quota_enabled === true}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              codex_quota_enabled: e.target.checked,
                            })
                          }
                          className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
                      </label>
                    </div>

                    {config?.codex_quota_enabled && (
                      <>
                        {/* 无凭证用户配额 */}
                        <div className="mb-4">
                          <label className="text-sm text-gray-400 mb-1 block">
                            无凭证用户默认配额
                          </label>
                          <input
                            type="number"
                            min="0"
                            value={config?.codex_quota_default ?? 0}
                            onChange={(e) =>
                              setConfig({
                                ...config,
                                codex_quota_default:
                                  parseInt(e.target.value) || 0,
                              })
                            }
                            className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                          />
                          <p className="text-gray-500 text-xs mt-1">
                            未上传凭证用户每日可调用次数（0=禁止）
                          </p>
                        </div>

                        {/* 按订阅类型配置奖励 */}
                        <div className="mt-4 p-3 border border-emerald-500/30 rounded-lg bg-emerald-500/5">
                          <label className="text-sm text-emerald-400 mb-3 block font-medium">
                            按 ChatGPT 订阅类型配置凭证奖励
                          </label>
                          <div className="grid grid-cols-3 gap-4">
                            <div>
                              <label className="text-xs text-gray-400 mb-1 block">
                                Plus 凭证奖励
                              </label>
                              <input
                                type="number"
                                min="0"
                                value={config?.codex_quota_plus ?? 150}
                                onChange={(e) =>
                                  setConfig({
                                    ...config,
                                    codex_quota_plus:
                                      parseInt(e.target.value) || 0,
                                  })
                                }
                                className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                              />
                              <p className="text-blue-400 text-xs mt-1">$20/月</p>
                            </div>
                            <div>
                              <label className="text-xs text-gray-400 mb-1 block">
                                Pro 凭证奖励
                              </label>
                              <input
                                type="number"
                                min="0"
                                value={config?.codex_quota_pro ?? 300}
                                onChange={(e) =>
                                  setConfig({
                                    ...config,
                                    codex_quota_pro:
                                      parseInt(e.target.value) || 0,
                                  })
                                }
                                className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                              />
                              <p className="text-purple-400 text-xs mt-1">$200/月</p>
                            </div>
                            <div>
                              <label className="text-xs text-gray-400 mb-1 block">
                                Team 凭证奖励
                              </label>
                              <input
                                type="number"
                                min="0"
                                value={config?.codex_quota_team ?? 250}
                                onChange={(e) =>
                                  setConfig({
                                    ...config,
                                    codex_quota_team:
                                      parseInt(e.target.value) || 0,
                                  })
                                }
                                className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                              />
                              <p className="text-orange-400 text-xs mt-1">企业版</p>
                            </div>
                          </div>
                          <p className="text-emerald-400 text-xs mt-3">
                            💡 示例：用户上传 1个Plus + 1个Pro 凭证 = {(config?.codex_quota_default || 0)} + {config?.codex_quota_plus || 150} + {config?.codex_quota_pro || 300} = {(config?.codex_quota_default || 0) + (config?.codex_quota_plus || 150) + (config?.codex_quota_pro || 300)} 次/日
                          </p>
                        </div>

                        {/* 通用奖励（用于未识别类型） */}
                        <div className="mt-4">
                          <label className="text-sm text-gray-400 mb-1 block">
                            通用凭证奖励（未知类型）
                          </label>
                          <input
                            type="number"
                            min="0"
                            value={config?.codex_quota_per_cred ?? 200}
                            onChange={(e) =>
                              setConfig({
                                ...config,
                                codex_quota_per_cred:
                                  parseInt(e.target.value) || 0,
                              })
                            }
                            className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                          />
                          <p className="text-gray-500 text-xs mt-1">
                            无法识别订阅类型时使用此值
                          </p>
                        </div>
                      </>
                    )}
                  </div>

                  {/* 速率限制 */}
                  <div className="bg-gray-700/30 rounded-lg p-4">
                    <label className="block text-sm font-medium mb-3">
                      ⏱️ Codex 速率限制 (RPM)
                    </label>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="text-sm text-gray-400 mb-1 block">
                          基础 RPM
                        </label>
                        <input
                          type="number"
                          min="1"
                          value={config?.codex_base_rpm ?? 5}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              codex_base_rpm: parseInt(e.target.value) || 1,
                            })
                          }
                          className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                        <p className="text-gray-500 text-xs mt-1">
                          未贡献凭证用户每分钟请求数
                        </p>
                      </div>
                      <div>
                        <label className="text-sm text-gray-400 mb-1 block">
                          贡献者 RPM
                        </label>
                        <input
                          type="number"
                          min="1"
                          value={config?.codex_contributor_rpm ?? 10}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              codex_contributor_rpm:
                                parseInt(e.target.value) || 1,
                            })
                          }
                          className="w-full bg-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                        <p className="text-gray-500 text-xs mt-1">
                          贡献凭证用户每分钟请求数
                        </p>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* 保存按钮 */}
          <div className="pt-4 border-t border-gray-700">
            <button
              onClick={handleSave}
              disabled={saving}
              className="w-full py-3 bg-purple-600 hover:bg-purple-700 rounded-lg font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <Save size={18} />
              {saving ? "保存中..." : "保存配置"}
            </button>
          </div>
        </div>

        {/* 提示信息 */}
        <div className="mt-6 bg-green-900/20 border border-green-600/30 rounded-lg p-4">
          <h4 className="text-green-400 font-semibold mb-2">💾 自动保存</h4>
          <p className="text-green-200/80 text-sm">
            配置会自动保存到数据库，重启服务后依然生效。
          </p>
        </div>
      </div>
    </div>
  );
}
