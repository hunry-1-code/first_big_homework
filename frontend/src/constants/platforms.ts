/** 7 大舆情监测平台配置 */
export interface PlatformInfo {
  name: string;
  short: string;
  color: string;
  bg: string;
  api: string;
}

export const PLATFORMS: PlatformInfo[] = [
  { name: "微博热搜", short: "微", color: "#e84118", bg: "#ffeef0", api: "公开接口", icon: "ant-design:weibo-circle-filled" },
  { name: "微博搜索", short: "微", color: "#c23616", bg: "#ffeef0", api: "TikHub API", icon: "ant-design:weibo-circle-filled" },
  { name: "知乎",     short: "知", color: "#0066ff", bg: "#e8f0fe", api: "开放平台", icon: "ant-design:zhihu-circle-filled" },
  { name: "B站",      short: "B",  color: "#fb7299", bg: "#fff0f5", api: "bilibili-api", icon: "ant-design:bilibili-filled" },
  { name: "小红书",   short: "红", color: "#ff4757", bg: "#ffeef0", api: "TikHub API", icon: "simple-icons:xiaohongshu" },
  { name: "百度热搜", short: "百", color: "#3385ff", bg: "#e8f0fe", api: "千帆 API", icon: "ant-design:baidu-outlined" },
  { name: "百度搜索", short: "百", color: "#2e77e5", bg: "#e8f0fe", api: "千帆 API", icon: "ant-design:baidu-outlined" },
];

export function getPlatform(name: string): PlatformInfo | undefined {
  return PLATFORMS.find(p => p.name === name);
}

/** 后端英文代码 → 前端中文名 */
const EN_TO_CN: Record<string, string> = {
  weibo: "微博热搜",
  weibo_search: "微博搜索",
  weibo_hot: "微博热搜",
  zhihu: "知乎",
  zhihu_hot: "知乎",
  bilibili: "B站",
  xiaohongshu: "小红书",
  baidu: "百度搜索",
  baidu_news: "百度搜索",
  baidu_hot: "百度热搜",
  rss: "百度搜索",
  douyin: "微博热搜"
};

/** 将后端英文平台代码转为前端中文名 */
export function resolvePlatformName(raw: string): string {
  return EN_TO_CN[raw] || raw;
}

/** 按 name 查 brand color */
export function platformColor(name: string): string {
  return getPlatform(resolvePlatformName(name))?.color || "#94a3b8";
}

/** 按 name 查背景色 */
export function platformBg(name: string): string {
  return getPlatform(resolvePlatformName(name))?.bg || "#f1f5f9";
}
