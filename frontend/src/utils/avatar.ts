/** 根据用户名生成默认头像 */
const AVATAR_COLORS = [
  "#3b82f6", "#ef4444", "#22c55e", "#f97316", "#8b5cf6",
  "#ec4899", "#06b6d4", "#84cc16", "#f43f5e", "#6366f1",
  "#14b8a6", "#eab308", "#64748b", "#0ea5e9", "#a855f7"
];

export function avatarColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

export function avatarInitials(name: string, nickname?: string): string {
  const src = (nickname || name || "?").trim();
  if (!src) return "?";
  // 中文取最后一个字，英文取首字母大写
  if (/[一-龥]/.test(src)) {
    return src.slice(-1);
  }
  return src.charAt(0).toUpperCase();
}

/** 生成 SVG data URI 格式的默认头像 */
export function avatarDataUri(name: string, nickname?: string): string {
  const color = avatarColor(name);
  const initials = avatarInitials(name, nickname);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
    <rect width="100" height="100" fill="${color}"/>
    <text x="50" y="50" dy=".1em" text-anchor="middle" dominant-baseline="central"
      fill="white" font-size="42" font-family="PingFang SC,Microsoft YaHei,sans-serif" font-weight="600">
      ${initials}
    </text>
  </svg>`;
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}
