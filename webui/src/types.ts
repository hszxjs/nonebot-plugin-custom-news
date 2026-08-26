/** 与后端 pydantic 模型一一对应的类型定义 */

export interface PaletteColors {
  primary: string;
  accent: string;
  text: string;
  subtext: string;
  card_bg: string;
  card_border: string;
  rank1: string;
  rank2: string;
  rank3: string;
  rank_n: string;
  hot: string;
}

export interface BackgroundConfig {
  type: "preset" | "upload" | "wallpaper";
  value: string;
  overlay: number;
  overlay_mode: "light" | "dark";
  blur: number;
}

export interface PaletteConfig {
  mode: "auto" | "manual";
  colors: PaletteColors;
}

export interface CardStyleConfig {
  columns: number;
  items_per_card: number;
  border_radius: number;
  glass_blur: number;
  glass_saturation: number;
  shadow: number;
  show_hot: boolean;
}

export interface TypographyConfig {
  scale: number;
  title_weight: number;
}

export interface HeaderConfig {
  title: string;
  subtitle: string;
  show_date: boolean;
}

export interface FooterConfig {
  custom_text: string;
  show_credit: boolean;
}

export interface Theme {
  id: string;
  name: string;
  background: BackgroundConfig;
  palette: PaletteConfig;
  cards: CardStyleConfig;
  typography: TypographyConfig;
  header: HeaderConfig;
  footer: FooterConfig;
  per_card: Record<string, string>;
}

export interface GeneralSettings {
  dailyhot_api_url: string;
  render_width: number;
  cache_ttl: number;
  timezone: string;
  wallpaper_url: string;
  llm_api_key: string;
  llm_base_url: string;
  llm_model: string;
  llm_follow_digest: boolean;
  analysis_count: number;
}

export interface SourceSetting {
  enabled: boolean;
  limit: number;
}

export interface CustomSourceDef {
  id: string;
  name: string;
  route: string;
  category: string;
  emoji: string;
  limit: number;
  enabled: boolean;
}

export interface ScheduleItem {
  id: string;
  label: string;
  hour: number;
  minute: number;
  weekdays: number[];
  theme_id: string | null;
  enabled: boolean;
}

export interface PushTargetItem {
  id: string;
  label: string;
  enabled: boolean;
  target: Record<string, unknown>;
  added_at: string;
}

export interface RuntimeConfig {
  general: GeneralSettings;
  sources: Record<string, SourceSetting>;
  custom_sources: CustomSourceDef[];
  schedules: ScheduleItem[];
  push_targets: PushTargetItem[];
  themes: Record<string, Theme>;
  active_theme_id: string;
  webui: { username: string; password_sha: string; secret: string };
  music_accounts?: Record<string, { cookie: string; nickname: string; logged_at: string }>;
  music_chat?: { count: number; forward: boolean; comments: boolean };
}

export interface BuiltinSource {
  id: string;
  name: string;
  route: string;
  category: string;
  category_label: string;
  emoji: string;
}

export interface ConfigResponse {
  config: RuntimeConfig;
  builtin_sources: BuiltinSource[];
  category_labels: Record<string, string>;
  preset_theme_ids: string[];
}

export interface ThemeBrief {
  id: string;
  name: string;
  preset: boolean;
  active: boolean;
}

export interface BackgroundItem {
  id?: string;
  name: string;
  url: string;
}

export interface DigestCardData {
  source_id: string;
  name: string;
  emoji: string;
  category: string;
  stale: boolean;
  items: { rank: number; title: string; hot: number | null }[];
}

export interface RenderPreviewResponse {
  image: string;
  cards: { name: string; emoji: string; count: number; stale: boolean }[];
  failed: string[];
}
