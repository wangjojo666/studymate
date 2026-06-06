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

export async function ocrDocument(courseId, documentId, payload) {
  const { data } = await http.post(`/courses/${courseId}/documents/${documentId}/ocr`, payload);
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

export async function generatePractice(courseId, count) {
  const { data } = await http.post(`/courses/${courseId}/practice`, { count });
  return data;
}
