/** 后端 REST API 客户端 */

const BASE = "/custom-news/api";

export function getToken(): string {
  return localStorage.getItem("cn_token") ?? "";
}

export function setToken(token: string) {
  localStorage.setItem("cn_token", token);
}

export function clearToken() {
  localStorage.removeItem("cn_token");
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  const token = getToken();
  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const resp = await fetch(`${BASE}${path}`, { ...options, headers });
  if (resp.status === 401) {
    clearToken();
    window.location.hash = "#/login";
  }
  if (!resp.ok) {
    let detail = `${resp.status}`;
    try {
      const data = await resp.json();
      detail = data.detail ?? JSON.stringify(data);
    } catch {
      /* ignore */
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ token: string; username: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  me: () => request<{ username: string }>("/auth/me"),

  changePassword: (old_password: string, new_password: string) =>
    request<{ ok: boolean }>("/auth/password", {
      method: "PUT",
      body: JSON.stringify({ old_password, new_password }),
    }),

  getConfig: () =>
    request<import("./types").ConfigResponse>("/config"),

  updateConfig: (payload: Record<string, unknown>) =>
    request<{ ok: boolean }>("/config", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  listThemes: () =>
    request<{ themes: import("./types").ThemeBrief[]; active_theme_id: string }>(
      "/themes",
    ),

  getTheme: (id: string) => request<import("./types").Theme>(`/themes/${id}`),

  saveTheme: (theme: import("./types").Theme) =>
    request<{ ok: boolean }>(`/themes/${theme.id}`, {
      method: "PUT",
      body: JSON.stringify(theme),
    }),

  llmTest: () => request<{ ok: boolean; url?: string; model?: string; reply?: string; error?: string }>("/llm/test", { method: "POST" }),

  deleteTheme: (id: string) =>
    request<{ ok: boolean }>(`/themes/${id}`, { method: "DELETE" }),

  activateTheme: (id: string) =>
    request<{ ok: boolean }>(`/themes/${id}/activate`, { method: "POST" }),

  duplicateTheme: (id: string) =>
    request<{ ok: boolean; id: string }>(`/themes/${id}/duplicate`, {
      method: "POST",
    }),

  listBackgrounds: () =>
    request<{
      preset: import("./types").BackgroundItem[];
      uploaded: import("./types").BackgroundItem[];
    }>("/backgrounds"),

  uploadBackground: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ ok: boolean; filename: string; url: string }>(
      "/upload/background",
      { method: "POST", body: form },
    );
  },

  extractPalette: (background: import("./types").BackgroundConfig) =>
    request<{ colors: import("./types").PaletteColors }>("/palette/extract", {
      method: "POST",
      body: JSON.stringify({ background }),
    }),

  renderPreview: (payload: {
    theme?: import("./types").Theme;
    theme_id?: string;
    force_refresh?: boolean;
  }) =>
    request<import("./types").RenderPreviewResponse>("/render/preview", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  pushNow: (theme_id?: string) =>
    request<{ ok: boolean; message: string }>("/push/now", {
      method: "POST",
      body: JSON.stringify({ theme_id }),
    }),

  getLatest: () => request<{ image: string }>("/data/latest"),

  llmAnalyze: (payload: { count?: number; theme_id?: string } = {}) =>
    request<{ image: string; items: { title: string; source: string; ok: boolean; error?: string }[] }>(
      "/llm/analyze",
      { method: "POST", body: JSON.stringify(payload) },
    ),

  getLatestAnalysis: () => request<{ image: string }>("/data/latest_analysis"),

  musicLoginState: () =>
    request<{
      accounts: Record<
        string,
        {
          logged: boolean;
          nickname: string;
          cookie_preview: string;
          valid?: boolean;
          logged_at?: string;
        }
      >;
    }>("/music/login/state"),

  musicQrCreate: (platform: string) =>
    request<{ qr_img: string }>("/music/login/qr/create", {
      method: "POST",
      body: JSON.stringify({ platform }),
    }),

  musicQrStatus: (platform: string) =>
    request<{ code: string; message: string }>(
      `/music/login/qr/status?platform=${platform}`,
    ),

  musicSmsSend: (phone: string) =>
    request<{ ok: boolean; message: string }>("/music/login/sms/send", {
      method: "POST",
      body: JSON.stringify({ phone }),
    }),

  musicSmsVerify: (phone: string, code: string) =>
    request<{ ok: boolean; nickname: string }>("/music/login/sms/verify", {
      method: "POST",
      body: JSON.stringify({ phone, code }),
    }),

  musicImport: (platform: string, cookie: string) =>
    request<{ ok: boolean; valid?: boolean }>("/music/login/import", {
      method: "POST",
      body: JSON.stringify({ platform, cookie }),
    }),

  musicLogout: (platform: string) =>
    request<{ ok: boolean }>("/music/login/logout", {
      method: "POST",
      body: JSON.stringify({ platform }),
    }),

  musicPreview: () =>
    request<{
      platforms: {
        platform: string;
        label: string;
        chart_text?: string;
        songs?: {
          song: string;
          artists: string;
          album: string;
          cover: string;
          audio: string;
          jump: string;
          comments_text: string;
        }[];
        error?: string;
      }[];
    }>("/music/preview", { method: "POST" }),

  getDigestCards: () =>
    request<{ cards: import("./types").DigestCardData[]; failed: string[] }>(
      "/digest/cards",
    ),

  sourcesStatus: () =>
    request<{
      status: Record<
        string,
        { last_ok: string | null; items: number; last_error: string | null }
      >;
      dailyhot_api_url: string;
    }>("/sources/status"),

  refreshSources: () =>
    request<{
      ok: boolean;
      cards: { name: string; count: number; stale: boolean }[];
      failed: string[];
    }>("/sources/refresh", { method: "POST" }),
};
