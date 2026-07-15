/** 7 大舆情监测平台配置 */
export interface PlatformInfo {
  name: string;
  short: string;
  color: string;
  bg: string;
  api: string;
  icon: string;
}

export const PLATFORMS: PlatformInfo[] = [
  { name: "微博热搜", short: "微", color: "#e84118", bg: "#ffeef0", api: "公开接口", icon: "ant-design:weibo-circle-filled" },
  { name: "微博搜索", short: "微", color: "#c23616", bg: "#ffeef0", api: "TikHub API", icon: "ant-design:weibo-circle-filled" },
  { name: "知乎",     short: "知", color: "#0066ff", bg: "#e8f0fe", api: "开放平台", icon: "ant-design:zhihu-circle-filled" },
  { name: "B站",      short: "B",  color: "#fb7299", bg: "#fff0f5", api: "bilibili-api", icon: "ant-design:bilibili-filled" },
  { name: "小红书",   short: "红", color: "#ff4757", bg: "#ffeef0", api: "TikHub API", icon: "simple-icons:xiaohongshu" },
  { name: "抖音",     short: "抖", color: "#111111", bg: "#f1f5f9", api: "TikHub API", icon: "simple-icons:tiktok" },
  { name: "36氪",     short: "氪", color: "#3182ce", bg: "#ebf8ff", api: "RSS 订阅",  icon: "ri/rss-fill" },
  { name: "人民网",   short: "人", color: "#c41e3a", bg: "#fef0f0", api: "新闻爬虫", icon: "ri/rss-fill" },
  { name: "澎湃新闻", short: "澎", color: "#1e40af", bg: "#e8f0fe", api: "新闻爬虫", icon: "ri/rss-fill" },
  { name: "InfoQ",    short: "Q",  color: "#38a169", bg: "#f0fff4", api: "新闻爬虫", icon: "ri/rss-fill" },
  { name: "少数派",   short: "派", color: "#d53f8c", bg: "#fff5f7", api: "新闻爬虫", icon: "ri/rss-fill" },
  { name: "主流新闻", short: "聚", color: "#1e3a5f", bg: "#e8f0fe", api: "聚合人民网·36氪·澎湃·InfoQ·少数派", icon: "ri/rss-fill" },
  { name: "百度热搜", short: "百", color: "#3385ff", bg: "#e8f0fe", api: "千帆 API", icon: "ant-design:baidu-outlined" },
  { name: "百度搜索", short: "百", color: "#2e77e5", bg: "#e8f0fe", api: "千帆 API", icon: "ant-design:baidu-outlined" },
];

export function getPlatform(name: string): PlatformInfo | undefined {
  return PLATFORMS.find(p => p.name === name);
}

/** 后端英文代码 → 前端中文名 */
const EN_TO_CN: Record<string, string> = {
  weibo: "微博搜索",
  weibo_search: "微博搜索",
  weibo_hot: "微博热搜",
  zhihu: "知乎",
  zhihu_hot: "知乎",
  bilibili: "B站",
  xiaohongshu: "小红书",
  baidu: "百度搜索",
  baidu_news: "百度搜索",
  baidu_hot: "百度热搜",
  rss: "RSS订阅",
  rss_36kr: "36氪",
  rss_sspai: "少数派",
  rss_infoq: "InfoQ",
  douyin: "抖音",
  news_people: "人民网",
  news_36kr: "36氪",
  news_thepaper: "澎湃新闻",
  news_infoq: "InfoQ",
  news_sspai: "少数派",
  mainstream_news: "主流新闻(聚合)"
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

// ==================== 搜索平台配置 ====================

/** 支持关键词搜索的爬虫平台映射（前端显示名 → 后端 platform ID） */
export interface SearchPlatform {
  name: string;
  id: string;
  always: boolean;
  needKey?: string;
  icon: string;
  color: string;
  bg: string;
}

export const SEARCH_PLATFORMS: SearchPlatform[] = [
  {
    name: "B站",
    id: "bilibili",
    always: true,
    icon: "ant-design:bilibili-filled",
    color: "#fb7299",
    bg: "#fff0f5"
  },
  {
    name: "百度搜索",
    id: "baidu",
    always: false,
    needKey: "千帆 API Key",
    icon: "ant-design:baidu-outlined",
    color: "#3385ff",
    bg: "#e8f0fe"
  },
  {
    name: "知乎",
    id: "zhihu",
    always: false,
    needKey: "知乎开放平台",
    icon: "ant-design:zhihu-circle-filled",
    color: "#0066ff",
    bg: "#e8f0fe"
  },
  {
    name: "微博搜索",
    id: "weibo",
    always: false,
    needKey: "TikHub API Key",
    icon: "ant-design:weibo-circle-filled",
    color: "#e84118",
    bg: "#ffeef0"
  },
  {
    name: "小红书",
    id: "xiaohongshu",
    always: false,
    needKey: "TikHub API Key",
    icon: "simple-icons:xiaohongshu",
    color: "#ff4757",
    bg: "#ffeef0"
  },
  {
    name: "抖音",
    id: "douyin",
    always: false,
    needKey: "TikHub API Key",
    icon: "simple-icons:tiktok",
    color: "#111111",
    bg: "#f1f5f9"
  },
  // ===== 主流新闻媒体 =====
  {
    name: "人民网",
    id: "news_people",
    always: true,
    icon: "ri/rss-fill",
    color: "#c41e3a",
    bg: "#fef0f0"
  },
  {
    name: "36氪",
    id: "news_36kr",
    always: true,
    icon: "ri/rss-fill",
    color: "#3182ce",
    bg: "#ebf8ff"
  },
  {
    name: "澎湃新闻",
    id: "news_thepaper",
    always: true,
    icon: "ri/rss-fill",
    color: "#1e40af",
    bg: "#e8f0fe"
  },
  {
    name: "InfoQ",
    id: "news_infoq",
    always: true,
    icon: "ri/rss-fill",
    color: "#38a169",
    bg: "#f0fff4"
  },
  {
    name: "少数派",
    id: "news_sspai",
    always: true,
    icon: "ri/rss-fill",
    color: "#d53f8c",
    bg: "#fff5f7"
  },
  {
    name: "百度新闻",
    id: "baidu_news",
    always: true,
    icon: "ant-design:baidu-outlined",
    color: "#3385ff",
    bg: "#e8f0fe"
  },
];
