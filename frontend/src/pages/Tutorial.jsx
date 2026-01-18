import { ArrowLeft, BookOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api";

export default function Tutorial() {
  const navigate = useNavigate();
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    api
      .get("/api/manage/tutorial")
      .then((res) => {
        if (res.data.enabled) {
          setEnabled(true);
          setContent(res.data.content || "");
        } else {
          // 教程未启用，跳转回首页
          navigate("/");
        }
      })
      .catch(() => {
        navigate("/");
      })
      .finally(() => setLoading(false));
  }, [navigate]);

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-900 text-white flex items-center justify-center">
        <div className="text-gray-400">加载中...</div>
      </div>
    );
  }

  if (!enabled) {
    return null;
  }

  return (
    <div className="min-h-screen bg-dark-900 text-white">
      {/* 导航栏 */}
      <nav className="bg-dark-800 border-b border-dark-600 p-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <Link
            to="/"
            className="flex items-center gap-2 text-gray-400 hover:text-white"
          >
            <ArrowLeft size={20} />
            返回
          </Link>
          <div className="flex items-center gap-2 text-cyan-400">
            <BookOpen size={20} />
            <span className="font-semibold">使用教程</span>
          </div>
        </div>
      </nav>

      {/* 教程内容 */}
      <main className="max-w-4xl mx-auto p-6">
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-6 md:p-8">
          {/* 渲染 Markdown 内容（简单处理） */}
          <div className="prose prose-invert prose-cyan max-w-none">
            {content.split("\n").map((line, i) => {
              // 标题处理
              if (line.startsWith("### ")) {
                return (
                  <h3
                    key={i}
                    className="text-lg font-bold text-cyan-400 mt-6 mb-3"
                  >
                    {line.slice(4)}
                  </h3>
                );
              }
              if (line.startsWith("## ")) {
                return (
                  <h2
                    key={i}
                    className="text-xl font-bold text-cyan-300 mt-8 mb-4"
                  >
                    {line.slice(3)}
                  </h2>
                );
              }
              if (line.startsWith("# ")) {
                return (
                  <h1 key={i} className="text-2xl font-bold text-white mb-6">
                    {line.slice(2)}
                  </h1>
                );
              }
              // 列表处理
              if (line.startsWith("- ") || line.startsWith("* ")) {
                return (
                  <li key={i} className="text-gray-300 ml-4">
                    {line.slice(2)}
                  </li>
                );
              }
              if (/^\d+\.\s/.test(line)) {
                return (
                  <li key={i} className="text-gray-300 ml-4 list-decimal">
                    {line.replace(/^\d+\.\s/, "")}
                  </li>
                );
              }
              // 空行
              if (line.trim() === "") {
                return <br key={i} />;
              }
              // 普通段落
              return (
                <p key={i} className="text-gray-300 leading-relaxed mb-2">
                  {line}
                </p>
              );
            })}
          </div>
        </div>

        {/* 底部按钮 */}
        <div className="mt-6 text-center">
          <button
            onClick={() => {
              // 标记已阅读教程
              localStorage.setItem("hasReadTutorial", "true");
              navigate("/");
            }}
            className="inline-flex items-center gap-2 px-6 py-3 bg-cyan-600 hover:bg-cyan-700 text-white rounded-lg font-medium"
          >
            我已阅读，开始使用
          </button>
        </div>
      </main>
    </div>
  );
}
