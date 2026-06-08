import axios from "axios";

const http = axios.create({
  baseURL: "/api",
  timeout: 600000
});

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

export async function ocrDocument(courseId, documentId, payload) {
  const { data } = await http.post(`/courses/${courseId}/documents/${documentId}/ocr`, payload);
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

export async function generateOutline(courseId) {
  const { data } = await http.post(`/courses/${courseId}/review-outline`);
  return data;
}

export async function generatePractice(courseId, payload) {
  const request = typeof payload === "number" ? { count: payload } : payload;
  const { data } = await http.post(`/courses/${courseId}/practice`, request);
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
