import { createRouter, createWebHistory } from "vue-router";

import { useAuthStore } from "../stores/auth";
import AdminView from "../views/AdminView.vue";
import BoardView from "../views/BoardView.vue";
import DetailView from "../views/DetailView.vue";
import LoginView from "../views/LoginView.vue";
import QaView from "../views/QaView.vue";
import UserView from "../views/UserView.vue";

const routes = [
  { path: "/login", name: "login", component: LoginView, meta: { public: true } },
  { path: "/", name: "board", component: BoardView },
  { path: "/events/:id", name: "event-detail", component: DetailView, props: true },
  { path: "/qa", name: "qa", component: QaView },
  { path: "/user", name: "user", component: UserView },
  { path: "/admin", name: "admin", component: AdminView, meta: { admin: true } }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: "login" };
  }
  if (to.meta.admin && !auth.isAdmin) {
    return { name: "board" };
  }
  if (to.name === "login" && auth.isAuthenticated) {
    return { name: "board" };
  }
  return true;
});

export default router;
