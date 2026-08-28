import { useState } from "react";
import { Newspaper } from "@phosphor-icons/react";
import { Button, Card, Input } from "../ui";
import { api, setToken } from "../api";

export default function LoginPage({ onOk }: { onOk: () => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setLoading(true);
    setError("");
    try {
      const r = await api.login(username, password);
      setToken(r.token);
      onOk();
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center p-4">
      {/* 顶部品牌光晕 */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-[420px]"
        style={{
          background:
            "radial-gradient(900px 380px at 50% -80px, rgba(124,140,248,.28), transparent 70%)",
        }}
      />
      <div className="glass relative w-full max-w-md rounded-3xl p-8 shadow-2xl">
        <div className="mb-6 text-center">
          <div className="brand-gradient brand-glow mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-2xl">
            <Newspaper className="h-8 w-8 text-white drop-shadow" weight="fill" />
          </div>
          <h1 className="text-gradient text-2xl font-bold tracking-wide">全网热点日报</h1>
          <p className="mt-1 text-small text-muted">
            聚合 · 主题化 · 定时推送 · WebUI 控制台
          </p>
        </div>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <Input label="用户名" value={username} onValueChange={setUsername} autoComplete="username" />
          <Input
            label="密码"
            type="password"
            value={password}
            onValueChange={setPassword}
            autoComplete="current-password"
            isInvalid={!!error}
            errorMessage={error}
          />
          <Button type="submit" className="mt-1 !h-11" isLoading={loading}>
            进入控制台
          </Button>
        </form>
        <p className="mt-5 text-center text-tiny text-muted/70">
          初始密码见机器人启动日志（可在 .env 配置 custom_news_webui_password）
        </p>
      </div>
    </div>
  );
}
