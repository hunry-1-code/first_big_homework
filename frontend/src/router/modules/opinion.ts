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
          title: "系统管理",
          rank: 99,
          roles: ["admin"]
        }
      },
      {
        path: "/admin/users",
        name: "AdminUsers",
        component: () => import("@/views/admin/users.vue"),
        meta: {
          icon: "ep:user-filled",
          title: "用户管理",
          rank: 100,
          roles: ["admin"]
        }
      }
    ]
  }
] satisfies Array<RouteConfigsTable>;
