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

export async function getCourses() {
  const { data } = await http.get("/courses");
  return data;
}

export async function createCourse(payload) {
  const { data } = await http.post("/courses", payload);
  return data;
}

export async function getCourse(id) {
  const { data } = await http.get(`/courses/${id}`);
  return data;
}

export async function uploadDocument(courseId, file) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await http.post(`/courses/${courseId}/documents`, form, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return data;
}

export async function deleteDocument(courseId, documentId) {
  const { data } = await http.delete(`/courses/${courseId}/documents/${documentId}`);
  return data;
}

export async function reindexCourse(courseId) {
  const { data } = await http.post(`/courses/${courseId}/reindex`);
  return data;
}

export async function reindexDocument(courseId, documentId) {
  const { data } = await http.post(`/courses/${courseId}/documents/${documentId}/reindex`);
  return data;
}

export async function getProcessingJobs(courseId) {
  const { data } = await http.get(`/courses/${courseId}/jobs`);
  return data;
}

export async function retryProcessingJob(courseId, jobId) {
  const { data } = await http.post(`/courses/${courseId}/jobs/${jobId}/retry`);
  return data;
}

export async function cancelProcessingJob(courseId, jobId) {
  const { data } = await http.post(`/courses/${courseId}/jobs/${jobId}/cancel`);
  return data;
}

export async function ocrDocument(courseId, documentId, payload) {
  const { data } = await http.post(`/courses/${courseId}/documents/${documentId}/ocr`, payload);
  return data;
}

export async function visionDocument(courseId, documentId) {
  const { data } = await http.post(`/courses/${courseId}/documents/${documentId}/vision`);
  return data;
}

export async function getOcrJob(courseId, documentId, jobId) {
  const { data } = await http.get(`/courses/${courseId}/documents/${documentId}/ocr-jobs/${jobId}`);
  return data;
}

export async function cancelOcrJob(courseId, documentId, jobId) {
  const { data } = await http.post(`/courses/${courseId}/documents/${documentId}/ocr-jobs/${jobId}/cancel`);
  return data;
}

export async function askCourse(courseId, question) {
  const { data } = await http.post(`/courses/${courseId}/ask`, {
    question,
    top_k: 5
  });
  return data;
}

export async function getSourceChunk(courseId, chunkId, params = {}) {
  const { data } = await http.get(`/courses/${courseId}/chunks/${chunkId}`, { params });
  return data;
}

export async function generateOutline(courseId) {
  const { data } = await http.post(`/courses/${courseId}/review-outline`);
  return data;
}

export async function generatePractice(courseId, payload) {
  const request = typeof payload === "number" ? { count: payload } : payload;
  const { data } = await http.post(`/courses/${courseId}/practice`, request);
  return data;
}

export async function analyzeCppCode(courseId, payload) {
  const { data } = await http.post(`/courses/${courseId}/cpp/analyze`, payload);
  return data;
}

export async function getLearningProfile(courseId) {
  const { data } = await http.get(`/courses/${courseId}/learning/profile`);
  return data;
}

export async function getKnowledgeGraph(courseId) {
  const { data } = await http.get(`/courses/${courseId}/learning/graph`);
  return data;
}

export async function getWrongAttempts(courseId) {
  const { data } = await http.get(`/courses/${courseId}/learning/wrong-attempts`);
  return data;
}

export async function submitPracticeAttempt(courseId, payload) {
  const { data } = await http.post(`/courses/${courseId}/learning/attempts`, payload);
  return data;
}

export async function generateReviewPlan(courseId, payload) {
  const { data } = await http.post(`/courses/${courseId}/learning/review-plan`, payload);
  return data;
}

export async function updateReviewTask(courseId, taskId, status) {
  const { data } = await http.patch(`/courses/${courseId}/learning/tasks/${taskId}`, { status });
  return data;
}

export async function downloadLearningReport(courseId) {
  const { data } = await http.get(`/courses/${courseId}/learning/report.pdf`, {
    responseType: "blob"
  });
  return data;
}

function shouldRedirectToLogin(error) {
  if (error?.response?.status !== 401) return false;
  if (window.location.pathname === "/login") return false;
  const url = String(error?.config?.url || "");
  return !url.startsWith("/auth/login") && !url.startsWith("/auth/register");
}
