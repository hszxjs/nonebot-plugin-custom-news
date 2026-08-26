import { useCallback, useEffect, useRef, useState } from "react";
import {
  Button,
  Card,
  CardBody,
  Chip,
  Input,
  PageHeader,
  Select,
  Switch,
} from "../ui";
import { api } from "../api";

type AccountState = {
  logged: boolean;
  nickname: string;
  cookie_preview: string;
  valid?: boolean;
  logged_at?: string;
};

const PLATFORM_META: Record<string, { label: string; icon: string; hint: string }> = {
  netease: {
    label: "网易云音乐",
    icon: "🎵",
    hint: "扫码或手机验证码登录，登录后部分歌曲可获得更好的播放链接",
  },
  qq: {
    label: "QQ音乐",
    icon: "🎧",
    hint: "通过手动导入浏览器 Cookie 登录（导入后音乐卡片可内嵌试听直链）",
  },
};

export default function MusicAccountsPage() {
  const [accounts, setAccounts] = useState<Record<string, AccountState>>({});
  const [qrPlatform, setQrPlatform] = useState("netease");
  const [qrImg, setQrImg] = useState<string | null>(null);
  const [qrState, setQrState] = useState<{ code: string; message: string } | null>(null);
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [smsMsg, setSmsMsg] = useState("");
  const [busy, setBusy] = useState("");
  const [importOpen, setImportOpen] = useState<Record<string, boolean>>({});
  const [cookieText, setCookieText] = useState<Record<string, string>>({});
  const pollRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    const r = await api.musicLoginState();
    setAccounts(r.accounts);
  }, []);

  useEffect(() => {
    load();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [load]);

  const stopPoll = () => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const startQr = async (platform: string) => {
    setBusy("qr");
    setQrState(null);
    setQrImg(null); // 先清旧图：请求失败时不残留上一个平台的二维码
    stopPoll();
    try {
      const r = await api.musicQrCreate(platform);
      setQrImg(r.qr_img);
      stopPoll();
      pollRef.current = window.setInterval(async () => {
        try {
          const s = await api.musicQrStatus(platform);
          setQrState(s);
          if (["success", "expired", "risk", "error"].includes(s.code)) {
            stopPoll();
            if (s.code === "success") await load();
          }
        } catch {
          /* 轮询失败忽略，下轮重试 */
        }
      }, 2000);
    } catch (e) {
      setQrState({ code: "error", message: e instanceof Error ? e.message : "生成失败" });
    } finally {
      setBusy("");
    }
  };

  const sendSms = async () => {
    setBusy("sms");
    setSmsMsg("");
    try {
      const r = await api.musicSmsSend(phone);
      setSmsMsg(`✅ ${r.message}`);
    } catch (e) {
      setSmsMsg(`❌ ${e instanceof Error ? e.message : "发送失败"}`);
    } finally {
      setBusy("");
    }
  };

  const verifySms = async () => {
    setBusy("verify");
    setSmsMsg("");
    try {
      const r = await api.musicSmsVerify(phone, code);
      setSmsMsg(`✅ 登录成功（${r.nickname || "未知昵称"}）`);
      setPhone("");
      setCode("");
      await load();
    } catch (e) {
      setSmsMsg(`❌ ${e instanceof Error ? e.message : "登录失败"}`);
    } finally {
      setBusy("");
    }
  };

  const doImport = async (platform: string) => {
    setBusy(`import-${platform}`);
    try {
      await api.musicImport(platform, cookieText[platform] || "");
      setImportOpen((p) => ({ ...p, [platform]: false }));
      setCookieText((p) => ({ ...p, [platform]: "" }));
      await load();
    } catch (e) {
      alert(`导入失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setBusy("");
    }
  };

  const doLogout = async (platform: string) => {
    await api.musicLogout(platform);
    await load();
  };

  const qrStateChip = () => {
    if (!qrState) return null;
    const color =
      qrState.code === "success"
        ? "success"
        : qrState.code === "scanned"
          ? "accent"
          : qrState.code === "waiting"
            ? "default"
            : "danger";
    return <Chip color={color as never}>{qrState.message}</Chip>;
  };

  return (
    <div className="flex max-w-5xl flex-col gap-4">
      <PageHeader
        title="音乐账号"
        desc="登录后音乐卡片可获得真实播放直链（未登录也能正常出卡片，评论区数据本就免登录）"
      />

      {(["netease", "qq"] as const).map((platform) => {
        const meta = PLATFORM_META[platform];
        const acc = accounts[platform];
        return (
          <Card key={platform} className="glass">
            <CardBody className="gap-3 p-5">
              <div className="flex flex-wrap items-center gap-3">
                <span className="brand-gradient flex h-10 w-10 items-center justify-center rounded-2xl text-lg shadow">
                  {meta.icon}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{meta.label}</div>
                  <div className="text-tiny text-muted">{meta.hint}</div>
                </div>
                {acc?.logged ? (
                  <div className="flex items-center gap-2">
                    <Chip color={acc.valid === false ? "warning" : "success"}>
                      {acc.valid === false ? "cookie 可能失效" : "已登录"}
                    </Chip>
                    <span className="text-small">{acc.nickname}</span>
                    <span className="font-mono text-tiny text-muted">{acc.cookie_preview}</span>
                    <Button size="sm" variant="flat" color="danger" onPress={() => void doLogout(platform)}>
                      退出
                    </Button>
                  </div>
                ) : (
                  <Chip>未登录</Chip>
                )}
              </div>

              {platform === "netease" && !acc?.logged && (
                <div className="rounded-2xl border border-white/8 bg-white/3 p-3">
                  <div className="mb-2 text-small font-semibold">📱 手机验证码登录</div>
                  <div className="flex flex-wrap items-end gap-2">
                    <Input className="w-40" label="手机号" value={phone} onValueChange={setPhone} />
                    <Button size="md" variant="flat" isLoading={busy === "sms"} isDisabled={phone.length !== 11} onPress={() => void sendSms()}>
                      发送验证码
                    </Button>
                    <Input className="w-28" label="验证码" value={code} onValueChange={setCode} />
                    <Button size="md" isLoading={busy === "verify"} isDisabled={!code.trim()} onPress={() => void verifySms()}>
                      登录
                    </Button>
                    {smsMsg && <span className="pb-2 text-small text-muted">{smsMsg}</span>}
                  </div>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2">
                {platform === "netease" && (
                  <Button
                    size="sm"
                    variant="flat"
                    isLoading={busy === "qr"}
                    onPress={() => {
                      setQrPlatform(platform);
                      void startQr(platform);
                    }}
                  >
                    📷 {acc?.logged ? "重新扫码" : "扫码登录"}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="flat"
                  onPress={() =>
                    setImportOpen((p) => ({ ...p, [platform]: !p[platform] }))
                  }
                >
                  🍪 手动导入 Cookie
                </Button>
              </div>

              {importOpen[platform] && (
                <div className="rounded-2xl border border-white/8 bg-white/3 p-3">
                  <div className="mb-2 text-tiny text-muted">
                    从浏览器登录 {meta.label} 网页版 → F12 → Network 任意请求 → 复制请求头里的整串 Cookie 粘贴到此处
                    {platform === "qq" ? "（需包含 uin 与 qm_keyst）" : "（需包含 MUSIC_U）"}
                  </div>
                  <textarea
                    className="field-input h-24 font-mono text-tiny"
                    placeholder="uin=...; qm_keyst=...; ..."
                    value={cookieText[platform] || ""}
                    onChange={(e) =>
                      setCookieText((p) => ({ ...p, [platform]: e.target.value }))
                    }
                  />
                  <Button
                    className="mt-2"
                    size="sm"
                    isLoading={busy === `import-${platform}`}
                    isDisabled={!(cookieText[platform] || "").trim()}
                    onPress={() => void doImport(platform)}
                  >
                    校验并保存
                  </Button>
                </div>
              )}

              {qrPlatform === platform && qrImg && (
                <div className="flex items-start gap-4 rounded-2xl border border-white/8 bg-white/3 p-4">
                  <img
                    src={qrImg}
                    alt="登录二维码"
                    className="h-44 w-44 rounded-xl bg-white p-2"
                  />
                  <div className="flex flex-col items-start gap-2">
                    <div className="text-small font-semibold">用 {meta.label} App 扫码</div>
                    <div className="text-tiny text-muted">
                      二维码 4 分钟内有效，登录成功后此面板自动更新
                    </div>
                    {qrStateChip()}
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        );
      })}
    </div>
  );
}
