export interface ListItem {
  avatar?: string;
  title?: string;
  description?: string;
  datetime?: string;
  extra?: string;
  status?: "primary" | "success" | "warning" | "danger" | "info";
}

export const noticesData: { key: string; name: string; list: ListItem[]; emptyText: string }[] = [
  { key: "1", name: "通知", list: [], emptyText: "暂无通知" },
  { key: "2", name: "消息", list: [], emptyText: "暂无消息" }
];
