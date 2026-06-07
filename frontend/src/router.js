import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: () => import("./views/DashboardView.vue") },
    { path: "/login", component: () => import("./views/LoginView.vue") },
    { path: "/courses", component: () => import("./views/CoursesView.vue") },
    { path: "/courses/:id", component: () => import("./views/CourseDetailView.vue"), props: true },
    {
      path: "/courses/:id/diagnosis",
      component: () => import("./views/LearningDiagnosisView.vue"),
      props: true
    }
  ]
});

export default router;
