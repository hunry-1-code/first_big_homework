/** 7 大舆情监测平台配置 */
export interface PlatformInfo {
  name: string;
  short: string;
  color: string;
  bg: string;
  api: string;
}

export const PLATFORMS: PlatformInfo[] = [
  { name: "微博热搜", short: "微", color: "#e84118", bg: "#ffeef0", api: "公开接口" },
  { name: "微博搜索", short: "微", color: "#c23616", bg: "#ffeef0", api: "TikHub API" },
  { name: "知乎",     short: "知", color: "#0066ff", bg: "#e8f0fe", api: "开放平台" },
  { name: "B站",      short: "B",  color: "#fb7299", bg: "#fff0f5", api: "bilibili-api" },
  { name: "小红书",   short: "红", color: "#ff4757", bg: "#ffeef0", api: "TikHub API" },
  { name: "百度热搜", short: "百", color: "#3385ff", bg: "#e8f0fe", api: "千帆 API" },
  { name: "百度搜索", short: "百", color: "#2e77e5", bg: "#e8f0fe", api: "千帆 API" },
];

export function getPlatform(name: string): PlatformInfo | undefined {
  return PLATFORMS.find(p => p.name === name);
}

/** 按 name 查 brand color */
export function platformColor(name: string): string {
  return getPlatform(name)?.color || "#94a3b8";
}

/** 按 name 查背景色 */
export function platformBg(name: string): string {
  return getPlatform(name)?.bg || "#f1f5f9";
}
