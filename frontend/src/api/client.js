import axios from "axios";

import { normalizeApiError } from "./errors";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 600000
});

const TOKEN_KEY = "studymate_access_token";
const USER_KEY = "studymate_user";

http.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (shouldRedirectToLogin(error)) {
      clearAuthSession();
      window.location.assign(`/login?redirect=${encodeURIComponent(window.location.pathname + window.location.search)}`);
    }
    error.userMessage = normalizeApiError(error);
    return Promise.reject(error);
  }
);

export function getAuthToken() {
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser() {
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    window.localStorage.removeItem(USER_KEY);
    return null;
  }
}

export function setAuthSession(payload) {
  window.localStorage.setItem(TOKEN_KEY, payload.access_token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(payload.user));
}

export function clearAuthSession() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

export async function login(payload) {
  const { data } = await http.post("/auth/login", payload);
  setAuthSession(data);
  return data;
}

export async function register(payload) {
  const { data } = await http.post("/auth/register", payload);
  setAuthSession(data);
  return data;
}

export async function getCurrentUser() {
  const { data } = await http.get("/auth/me");
  window.localStorage.setItem(USER_KEY, JSON.stringify(data));
  return data;
}

export async function getHealthDetail(options = {}) {
  const { data } = await http.get("/health/detail", options);
  return data;
}

export async function getDashboardSummary(options = {}) {
  const { data } = await http.get("/courses/dashboard-summary", options);
  return data;
}

export async function getCourses(options = {}) {
  const { data } = await http.get("/courses", options);
  return data;
}

export async function createCourse(payload) {
  const { data } = await http.post("/courses", payload);
  return data;
}

export async function getCourse(id, options = {}) {
  const { data } = await http.get(`/courses/${id}`, options);
  return data;
}

export async function uploadDocument(courseId, file, options = {}) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await http.post(`/courses/${courseId}/documents`, form, {
    ...options,
    headers: { "Content-Type": "multipart/form-data" }
  });
  return data;
}

export async function deleteDocument(courseId, documentId, options = {}) {
  const { data } = await http.delete(`/courses/${courseId}/documents/${documentId}`, options);
  return data;
}

export async function reindexCourse(courseId, options = {}) {
  const { data } = await http.post(`/courses/${courseId}/reindex`, undefined, options);
  return data;
}

export async function reindexDocument(courseId, documentId, options = {}) {
  const { data } = await http.post(`/courses/${courseId}/documents/${documentId}/reindex`, undefined, options);
  return data;
}

export async function getProcessingJobs(courseId, options = {}) {
  const { data } = await http.get(`/courses/${courseId}/jobs`, options);
  return data;
}

export async function retryProcessingJob(courseId, jobId, options = {}) {
  const { data } = await http.post(`/courses/${courseId}/jobs/${jobId}/retry`, undefined, options);
  return data;
}

export async function cancelProcessingJob(courseId, jobId, options = {}) {
  const { data } = await http.post(`/courses/${courseId}/jobs/${jobId}/cancel`, undefined, options);
  return data;
}

export async function ocrDocument(courseId, documentId, payload, options = {}) {
  const { data } = await http.post(`/courses/${courseId}/documents/${documentId}/ocr`, payload, options);
  return data;
}

export async function visionDocument(courseId, documentId, options = {}) {
  const { data } = await http.post(`/courses/${courseId}/documents/${documentId}/vision`, undefined, options);
  return data;
}

export async function getOcrJob(courseId, documentId, jobId, options = {}) {
  const { data } = await http.get(`/courses/${courseId}/documents/${documentId}/ocr-jobs/${jobId}`, options);
  return data;
}

export async function cancelOcrJob(courseId, documentId, jobId, options = {}) {
  const { data } = await http.post(`/courses/${courseId}/documents/${documentId}/ocr-jobs/${jobId}/cancel`, undefined, options);
  return data;
}

export async function askCourse(courseId, question, options = {}) {
  const { data } = await http.post(`/courses/${courseId}/ask`, {
    question,
    top_k: 5
  }, options);
  return data;
}

export async function getSourceChunk(courseId, chunkId, params = {}, options = {}) {
  const { data } = await http.get(`/courses/${courseId}/chunks/${chunkId}`, { ...options, params });
  return data;
}

export async function generateOutline(courseId, options = {}) {
  const { data } = await http.post(`/courses/${courseId}/review-outline`, undefined, options);
  return data;
}

export async function generatePractice(courseId, payload, options = {}) {
  const request = typeof payload === "number" ? { count: payload } : payload;
  const { data } = await http.post(`/courses/${courseId}/practice`, request, options);
  return data;
}

export async function analyzeCppCode(courseId, payload, options = {}) {
  const { data } = await http.post(`/courses/${courseId}/cpp/analyze`, payload, options);
  return data;
}

export async function getLearningProfile(courseId, options = {}) {
  const { data } = await http.get(`/courses/${courseId}/learning/profile`, options);
  return data;
}

export async function getKnowledgeGraph(courseId, options = {}) {
  const { data } = await http.get(`/courses/${courseId}/learning/graph`, options);
  return data;
}

export async function getWrongAttempts(courseId, options = {}) {
  const { data } = await http.get(`/courses/${courseId}/learning/wrong-attempts`, options);
  return data;
}

export async function submitPracticeAttempt(courseId, payload, options = {}) {
  const { data } = await http.post(`/courses/${courseId}/learning/attempts`, payload, options);
  return data;
}

export async function generateReviewPlan(courseId, payload, options = {}) {
  const { data } = await http.post(`/courses/${courseId}/learning/review-plan`, payload, options);
  return data;
}

export async function updateReviewTask(courseId, taskId, status, options = {}) {
  const { data } = await http.patch(`/courses/${courseId}/learning/tasks/${taskId}`, { status }, options);
  return data;
}

export async function downloadLearningReport(courseId, options = {}) {
  const { data } = await http.get(`/courses/${courseId}/learning/report.pdf`, {
    ...options,
    responseType: "blob"
  });
  return data;
}

export function isRequestCanceled(error) {
  return axios.isCancel(error) || error?.code === "ERR_CANCELED" || error?.name === "AbortError";
}

function shouldRedirectToLogin(error) {
  if (error?.response?.status !== 401) return false;
  if (window.location.pathname === "/login") return false;
  const url = String(error?.config?.url || "");
  return !url.startsWith("/auth/login") && !url.startsWith("/auth/register");
}
