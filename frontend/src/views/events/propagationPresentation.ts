export function buildPropagationNotice(data: any): string {
  if (!data || data.coverage_status !== "insufficient") return "";

  const limitations = Array.isArray(data.limitations)
    ? data.limitations.map((item: unknown) => String(item).trim()).filter(Boolean)
    : [];
  const detail = limitations.length > 0 ? `原因：${limitations.join("；")}。` : "";
  return `传播证据不足：图中节点仅表示当前数据中的来源候选，不代表已验证传播路径。${detail}`;
}
