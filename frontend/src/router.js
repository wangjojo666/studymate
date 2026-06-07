import { createRouter, createWebHistory } from "vue-router";

import CourseDetailView from "./views/CourseDetailView.vue";
import CoursesView from "./views/CoursesView.vue";
import LearningDiagnosisView from "./views/LearningDiagnosisView.vue";
import LoginView from "./views/LoginView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/courses" },
    { path: "/login", component: LoginView },
    { path: "/courses", component: CoursesView },
    { path: "/courses/:id", component: CourseDetailView, props: true },
    { path: "/courses/:id/diagnosis", component: LearningDiagnosisView, props: true }
  ]
});

export default router;
