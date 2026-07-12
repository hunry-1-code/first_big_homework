const Layout = () => import("@/layout/index.vue");

export default [
  {
    path: "/",
    name: "Home",
    component: Layout,
    redirect: "/dashboard",
    meta: {
      icon: "ep:monitor",
      title: "舆情分析系统",
      rank: 1
    },
    children: [
      {
        path: "/dashboard",
        name: "Dashboard",
        component: () => import("@/views/welcome/index.vue"),
        meta: {
          icon: "ep:trend-charts",
          title: "舆情看板"
        }
      },
      {
        path: "/events/:id",
        name: "EventDetail",
        component: () => import("@/views/events/detail.vue"),
        meta: {
          title: "事件详情",
          showLink: false
        }
      },
      {
        path: "/analysis",
        name: "Analysis",
        component: () => import("@/views/analysis/index.vue"),
        meta: {
          icon: "ep:search",
          title: "事件分析"
        }
      },
      {
        path: "/qa",
        name: "Qa",
        component: () => import("@/views/qa/index.vue"),
        meta: {
          icon: "ep:chat-dot-round",
          title: "智能问答"
        }
      },
      {
        path: "/user",
        name: "UserCenter",
        component: () => import("@/views/user/index.vue"),
        meta: {
          icon: "ep:user",
          title: "个人中心"
        }
      },
      {
        path: "/admin",
        name: "Admin",
        component: () => import("@/views/admin/index.vue"),
        meta: {
          icon: "ep:setting",
          title: "运维管理",
          rank: 99,
          roles: ["admin"]
        }
      }
    ]
  },
  {
    path: "/system",
    name: "System",
    component: Layout,
    redirect: "/system/users",
    meta: {
      icon: "ri:settings-3-line",
      title: "系统管理",
      rank: 99,
      roles: ["admin"]
    },
    children: [
      {
        path: "/system/users",
        name: "SystemUsers",
        component: () => import("@/views/admin/users.vue"),
        meta: {
          icon: "ri:admin-line",
          title: "用户管理"
        }
      },
      {
        path: "/system/events",
        name: "SystemEvents",
        component: () => import("@/views/admin/events.vue"),
        meta: {
          icon: "ri:file-list-3-line",
          title: "事件管理"
        }
      }
    ]
  }
] satisfies Array<RouteConfigsTable>;
