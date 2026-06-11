import { createRouter, createWebHistory } from "vue-router";
import { getAuthToken } from "./api/client";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: () => import("./views/DashboardView.vue") },
    { path: "/login", component: () => import("./views/LoginView.vue") },
    { path: "/courses", component: () => import("./views/CoursesView.vue") },
    { path: "/courses/:id", component: () => import("./views/CourseDetailView.vue"), props: true },
    { path: "/reports", component: () => import("./views/ReportHighlightView.vue") },
    {
      path: "/courses/:id/diagnosis",
      component: () => import("./views/LearningDiagnosisView.vue"),
      props: true
    }
  ]
});

router.beforeEach((to) => {
  const isLoggedIn = Boolean(getAuthToken());
  if (to.path !== "/login" && !isLoggedIn) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }
  if (to.path === "/login" && isLoggedIn) {
    return "/";
  }
  return true;
});

export default router;
