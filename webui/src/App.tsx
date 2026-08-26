import { useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { api, getToken } from "./api";
import LoginPage from "./pages/Login";
import DashboardPage from "./pages/Dashboard";
import ThemeEditorPage from "./pages/ThemeEditor";
import SourcesPage from "./pages/Sources";
import PushPage from "./pages/Push";
import MusicAccountsPage from "./pages/MusicAccounts";
import SettingsPage from "./pages/Settings";

const NAV = [
  { to: "/", label: "总览", icon: "📊", end: true },
  { to: "/theme", label: "主题工坊", icon: "🎨", end: false },
  { to: "/sources", label: "数据源", icon: "📡", end: false },
  { to: "/push", label: "推送管理", icon: "🚀", end: false },
  { to: "/music", label: "音乐账号", icon: "🎧", end: false },
  { to: "/settings", label: "设置", icon: "⚙️", end: false },
];

function Layout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen text-foreground">
      {/* 顶部装饰光带 */}
      <div
        className="pointer-events-none fixed inset-x-0 top-0 h-64"
        style={{
          background:
            "radial-gradient(700px 220px at 50% -60px, rgba(124,140,248,.20), transparent 70%)",
        }}
      />
      <div className="relative mx-auto flex max-w-[1500px] gap-4 p-4 lg:p-6">
        {/* ---------------- 侧边栏 ---------------- */}
        <aside className="glass sticky top-6 hidden h-[calc(100vh-3rem)] w-60 shrink-0 flex-col rounded-2xl p-3.5 md:flex">
          {/* 品牌区 */}
          <div className="brand-gradient brand-glow mb-5 rounded-xl p-3.5">
            <div className="flex items-center gap-2.5">
              <span className="text-2xl drop-shadow">🗞️</span>
              <div>
                <div className="text-small font-bold tracking-wide text-white">
                  全网热点日报
                </div>
                <div className="text-tiny text-white/70">
                  Custom News Studio
                </div>
              </div>
            </div>
          </div>

          <nav className="flex flex-col gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-xl px-3.5 py-2.5 text-medium transition-all duration-200 ${
                    isActive
                      ? "brand-gradient font-semibold text-white shadow-lg"
                      : "text-muted hover:bg-white/6 hover:text-foreground"
                  }`
                }
              >
                <span className="text-base">{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="mt-auto flex flex-col gap-1 px-1">
            <button
              className="w-full rounded-xl px-3 py-2 text-left text-small text-muted transition-colors hover:bg-danger-soft hover:text-danger"
              onClick={() => {
                localStorage.removeItem("cn_token");
                navigate("/login");
              }}
            >
              🚪 退出登录
            </button>
            <div className="px-1 pt-1 text-tiny text-muted/60">
              nonebot-plugin-custom-news · v0.1.0
            </div>
          </div>
        </aside>

        {/* ---------------- 主内容 ---------------- */}
        <main className="min-w-0 flex-1">
          {/* 移动端导航 */}
          <nav className="glass mb-3 flex gap-1.5 overflow-x-auto rounded-2xl p-1.5 md:hidden">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `shrink-0 rounded-xl px-3.5 py-2 text-small ${
                    isActive
                      ? "brand-gradient font-semibold text-white"
                      : "text-muted"
                  }`
                }
              >
                {item.icon} {item.label}
              </NavLink>
            ))}
          </nav>
          {children}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  const [ready, setReady] = useState(false);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      setReady(true);
      setAuthed(false);
      return;
    }
    api
      .me()
      .then(() => setAuthed(true))
      .catch(() => setAuthed(false))
      .finally(() => setReady(true));
  }, []);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted">
        加载中…
      </div>
    );
  }

  if (!authed) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage onOk={() => setAuthed(true)} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/theme" element={<ThemeEditorPage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/push" element={<PushPage />} />
        <Route path="/music" element={<MusicAccountsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
