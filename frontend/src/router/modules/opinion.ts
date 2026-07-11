const Layout = () => import("@/layout/index.vue");

export default {
  path: "/",
  name: "Home",
  component: Layout,
  redirect: "/opinion/welcome",
  meta: {
    icon: "ep:menu",
    title: "舆情分析系统",
    rank: 1
  },
  children: [
    {
      path: "/opinion/welcome",
      name: "OpinionBoard",
      component: () => import("@/views/welcome/index.vue"),
      meta: {
        icon: "ep:trend-charts",
        title: "舆情看板"
      }
    },
    {
      path: "/opinion/detail/:id",
      name: "OpinionDetail",
      component: () => import("@/views/events/detail.vue"),
      meta: {
        title: "事件详情",
        showLink: false
      }
    },
    {
      path: "/opinion/qa",
      name: "OpinionQa",
      component: () => import("@/views/qa/index.vue"),
      meta: {
        icon: "ep:chat-dot-round",
        title: "智能问答"
      }
    },
    {
      path: "/opinion/user",
      name: "OpinionUser",
      component: () => import("@/views/user/index.vue"),
      meta: {
        icon: "ep:user",
        title: "个人中心"
      }
    },
    {
      path: "/opinion/admin",
      name: "OpinionAdmin",
      component: () => import("@/views/admin/index.vue"),
      meta: {
        icon: "ep:setting",
        title: "系统管理",
        roles: ["admin"]
      }
    }
  ]
} satisfies RouteConfigsTable;
