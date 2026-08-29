import { useCallback, useEffect, useState } from "react";
import { FloppyDisk, Lightning } from "@phosphor-icons/react";
import { Button, Card, CardBody, Divider, Input, PageHeader, Switch } from "../ui";
import { api } from "../api";
import type { GeneralSettings } from "../types";

export default function SettingsPage() {
  const [general, setGeneral] = useState<GeneralSettings | null>(null);
  const [musicChat, setMusicChat] = useState({ count: 10, forward: true, comments: true });
  const [pwd, setPwd] = useState({ old: "", neo: "", repeat: "" });
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");
  const [llmBusy, setLlmBusy] = useState(false);
  const [llmResult, setLlmResult] = useState<string | null>(null);

  const load = useCallback(async () => {
    const cfg = await api.getConfig();
    setGeneral(cfg.config.general);
    if (cfg.config.music_chat) setMusicChat(cfg.config.music_chat);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!general) return <div className="p-8 text-center text-muted">加载中…</div>;

  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <PageHeader title="设置" desc="渲染参数 / 抓取缓存 / 每日壁纸 / WebUI 密码" />
      <Card className="glass glass-hover">
        <CardBody className="gap-3 p-4">
          <div className="font-semibold">渲染与抓取</div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              size="sm"
              label="日报图宽度（像素）"
              type="number"
              value={String(general.render_width)}
              onValueChange={(v) => setGeneral({ ...general, render_width: Number(v) || 1080 })}
              description="默认 1080，图片实际输出为 2 倍（高清）"
            />
            <Input
              size="sm"
              label="数据缓存时长（秒）"
              type="number"
              value={String(general.cache_ttl)}
              onValueChange={(v) => setGeneral({ ...general, cache_ttl: Number(v) || 1800 })}
              description="同一段时间内重复生成直接使用缓存"
            />
            <Input
              size="sm"
              label="时区"
              value={general.timezone}
              onValueChange={(v) => setGeneral({ ...general, timezone: v })}
              description="定时任务使用的时区，如 Asia/Shanghai"
            />
            <Input
              size="sm"
              label="自定义每日壁纸直链"
              placeholder="留空使用必应每日壁纸"
              value={general.wallpaper_url}
              onValueChange={(v) => setGeneral({ ...general, wallpaper_url: v })}
              description="主题背景选择「每日在线壁纸」时生效"
            />
          </div>
          <Button
            className="self-start"
            size="sm"
            color="primary"
            isLoading={busy === "save"}
            onPress={async () => {
              setBusy("save");
              try {
                await api.updateConfig({ general });
                await api.updateConfig({ music_chat: musicChat } as never);
                setMsg("✅ 设置已保存");
              } catch (e) {
                setMsg(`❌ ${e instanceof Error ? e.message : "保存失败"}`);
              } finally {
                setBusy("");
              }
            }}
          >
            <FloppyDisk className="h-4 w-4" /> 保存设置
          </Button>
          {msg && <span className="text-small text-muted">{msg}</span>}
        </CardBody>
      </Card>

      <Card className="glass glass-hover">
        <CardBody className="gap-3 p-4">
          <div className="font-semibold">新闻深读（LLM 解析）</div>
          <Divider />
          <p className="text-small text-muted">
            配置 OpenAI 兼容接口后，可用「热点解析」命令或在日报后自动跟随一条聊天记录风格的深度解读图（基于新闻原文解析）。
            API Key 填 <code className="rounded bg-white/10 px-1">mock</code> 可预览样式效果。
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label="API Base URL"
              value={general.llm_base_url}
              onValueChange={(v) => setGeneral({ ...general, llm_base_url: v })}
              description="如 https://api.deepseek.com/v1 或本地 Ollama"
            />
            <Input
              label="API Key"
              type="password"
              value={general.llm_api_key}
              onValueChange={(v) => setGeneral({ ...general, llm_api_key: v })}
              description="仅保存在本机 config.json"
            />
            <Input
              label="模型"
              value={general.llm_model}
              onValueChange={(v) => setGeneral({ ...general, llm_model: v })}
              description="如 deepseek-chat / gpt-4o-mini"
            />
            <Input
              label="生成上限 tokens"
              type="number"
              value={String(general.llm_max_tokens ?? 8000)}
              onValueChange={(v) => setGeneral({ ...general, llm_max_tokens: Number(v) || 8000 })}
              description="推理模型（GLM/DeepSeek-R1 等）思考计入，建议 8000 起"
            />
            <Input
              label="每次解析条数"
              type="number"
              value={String(general.analysis_count)}
              onValueChange={(v) => setGeneral({ ...general, analysis_count: Number(v) || 3 })}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="flat"
              isLoading={llmBusy}
              onPress={async () => {
                setLlmBusy(true);
                setLlmResult(null);
                try {
                  const r = await api.llmTest();
                  setLlmResult(r.ok ? `✅ 连接成功（${r.model}）：${r.reply ?? ""}` : `❌ 连接失败：${r.error ?? "未知错误"}`);
                } catch (e) {
                  setLlmResult(`❌ ${e instanceof Error ? e.message : "请求失败"}`);
                } finally {
                  setLlmBusy(false);
                }
              }}
            >
              <Lightning className="h-4 w-4" /> 测试连接
            </Button>
            {llmResult && <span className="text-small text-muted">{llmResult}</span>}
          </div>
          <Switch
            isSelected={general.llm_follow_digest}
            onValueChange={(v) => setGeneral({ ...general, llm_follow_digest: v })}
          >
            定时推送前 5 分钟预生成深读，随日报同步发送
          </Switch>
        </CardBody>
      </Card>

      <Card className="glass glass-hover">
        <CardBody className="gap-3 p-4">
          <div className="font-semibold">新歌榜聊天记录</div>
          <Divider />
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label="每平台歌曲数（卡片+热评）"
              type="number"
              value={String(musicChat.count)}
              onValueChange={(v) => setMusicChat({ ...musicChat, count: Number(v) || 10 })}
            />
            <div className="flex items-end gap-6 pb-1">
              <Switch
                isSelected={musicChat.forward}
                onValueChange={(v) => setMusicChat({ ...musicChat, forward: v })}
              >
                合并转发
              </Switch>
              <Switch
                isSelected={musicChat.comments}
                onValueChange={(v) => setMusicChat({ ...musicChat, comments: v })}
              >
                附热评
              </Switch>
            </div>
          </div>
          <p className="text-tiny text-muted">
            关闭合并转发则逐条发送（消息较多）；账号登录见「音乐账号」页。
          </p>
        </CardBody>
      </Card>

      <Card className="glass glass-hover">
        <CardBody className="gap-3 p-4">
          <div className="font-semibold">修改 WebUI 密码</div>
          <Divider />
          <div className="grid gap-3 sm:grid-cols-3">
            <Input size="sm" type="password" label="当前密码" value={pwd.old} onValueChange={(v) => setPwd({ ...pwd, old: v })} />
            <Input size="sm" type="password" label="新密码（≥6位）" value={pwd.neo} onValueChange={(v) => setPwd({ ...pwd, neo: v })} />
            <Input size="sm" type="password" label="确认新密码" value={pwd.repeat} onValueChange={(v) => setPwd({ ...pwd, repeat: v })} />
          </div>
          <Button
            className="self-start"
            size="sm"
            variant="flat"
            isLoading={busy === "pwd"}
            onPress={async () => {
              if (pwd.neo !== pwd.repeat) {
                setMsg("❌ 两次输入的新密码不一致");
                return;
              }
              setBusy("pwd");
              try {
                await api.changePassword(pwd.old, pwd.neo);
                setMsg("✅ 密码已修改");
                setPwd({ old: "", neo: "", repeat: "" });
              } catch (e) {
                setMsg(`❌ ${e instanceof Error ? e.message : "修改失败"}`);
              } finally {
                setBusy("");
              }
            }}
          >
            🔑 修改密码
          </Button>
        </CardBody>
      </Card>

      <Card className="glass glass-hover">
        <CardBody className="p-4 text-small text-muted">
          <div className="mb-1 font-semibold text-foreground">机器人命令</div>
          <div>今日热点 —— 立即生成日报图</div>
          <div>订阅热点 / 退订热点 —— 管理本会话定时推送</div>
          <div>热点帮助 —— 查看帮助</div>
        </CardBody>
      </Card>
    </div>
  );
}
