import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useCourseDocumentProcessing } from "./useCourseDocumentProcessing";
import { getOcrJob, getProcessingJobs } from "../api/client";

vi.mock("element-plus", () => ({
  ElMessage: {
    error: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
    warning: vi.fn()
  },
  ElMessageBox: {
    confirm: vi.fn(),
    prompt: vi.fn()
  }
}));

vi.mock("../api/client", () => ({
  cancelOcrJob: vi.fn(),
  cancelProcessingJob: vi.fn(),
  deleteDocument: vi.fn(),
  getOcrJob: vi.fn(),
  getProcessingJobs: vi.fn(),
  isRequestCanceled: (error) => error?.name === "AbortError" || error?.code === "ERR_CANCELED",
  ocrDocument: vi.fn(),
  reindexCourse: vi.fn(),
  reindexDocument: vi.fn(),
  retryProcessingJob: vi.fn(),
  uploadDocument: vi.fn(),
  visionDocument: vi.fn()
}));

const wrappers = [];

describe("useCourseDocumentProcessing polling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    getOcrJob.mockReset();
    getProcessingJobs.mockReset();
    getProcessingJobs.mockResolvedValue([]);
  });

  afterEach(() => {
    for (const wrapper of wrappers.splice(0)) wrapper.unmount();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("runs polling serially and prevents a second in-flight refresh", async () => {
    const pendingRefresh = deferred();
    const harness = mountHarness({
      documents: [{ id: 10, status: "queued" }],
      loadCourse: () => pendingRefresh.promise
    });

    harness.processing.syncDocumentPolling(harness.course.value.documents);
    await vi.advanceTimersByTimeAsync(2500);
    expect(harness.loadCourse).toHaveBeenCalledTimes(1);
    expect(harness.processing.pollInFlight.value).toBe(true);

    harness.processing.syncDocumentPolling(harness.course.value.documents);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(harness.loadCourse).toHaveBeenCalledTimes(1);

    harness.course.value = { documents: [] };
    pendingRefresh.resolve();
    await flushPromises();
    expect(getProcessingJobs).toHaveBeenCalledTimes(1);
    expect(harness.processing.pollInFlight.value).toBe(false);
  });

  it("pauses while the page is hidden and resumes silently when visible", async () => {
    let visibility = "visible";
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility);
    const harness = mountHarness({ documents: [{ id: 10, status: "queued" }] });
    harness.loadCourse.mockImplementation(async () => {
      harness.course.value = { documents: [] };
    });

    harness.processing.syncDocumentPolling(harness.course.value.documents);
    visibility = "hidden";
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(5000);
    expect(harness.loadCourse).not.toHaveBeenCalled();

    visibility = "visible";
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(0);
    await flushPromises();
    expect(harness.loadCourse).toHaveBeenCalledTimes(1);
    expect(harness.loadCourse).toHaveBeenCalledWith(
      expect.objectContaining({ silent: true, force: true, signal: expect.any(AbortSignal) })
    );
  });

  it("restores every active OCR task after a page refresh", async () => {
    const activeJobs = [
      { id: 101, document_id: 11, job_type: "ocr", status: "running", ocr_job_id: 201 },
      { id: 102, document_id: 12, job_type: "ocr", status: "queued", ocr_job_id: 202 }
    ];
    getProcessingJobs.mockResolvedValue(activeJobs);
    getOcrJob.mockImplementation(async (_courseId, documentId, ocrJobId) => ({
      id: ocrJobId,
      document_id: documentId,
      status: "running",
      processed_pages: documentId === 11 ? 2 : 4
    }));
    const harness = mountHarness({ documents: [] });

    await harness.processing.loadJobs();

    expect(getOcrJob).toHaveBeenCalledTimes(2);
    expect(harness.processing.activeOcrJob(11)).toEqual(
      expect.objectContaining({ id: 201, document_id: 11, processing_job_id: 101 })
    );
    expect(harness.processing.activeOcrJob(12)).toEqual(
      expect.objectContaining({ id: 202, document_id: 12, processing_job_id: 102 })
    );
  });
});

function mountHarness({ documents, loadCourse: loadCourseImplementation = async () => {} }) {
  const courseId = ref("1");
  const course = ref({ documents });
  const loadCourse = vi.fn(loadCourseImplementation);
  let processing;
  const Harness = defineComponent({
    setup() {
      processing = useCourseDocumentProcessing({ courseId, course, loadCourse });
      return () => h("div");
    }
  });
  const wrapper = mount(Harness);
  wrappers.push(wrapper);
  return { wrapper, courseId, course, loadCourse, processing };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}
