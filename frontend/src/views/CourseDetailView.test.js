import { flushPromises, shallowMount } from "@vue/test-utils";
import { reactive } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CourseDetailView from "./CourseDetailView.vue";
import { getCourse, getLearningProfile } from "../api/client";

const routerMocks = vi.hoisted(() => ({
  route: null,
  push: vi.fn(),
  replace: vi.fn()
}));

vi.mock("vue-router", () => ({
  useRoute: () => routerMocks.route,
  useRouter: () => ({ push: routerMocks.push, replace: routerMocks.replace })
}));

vi.mock("../api/client", () => ({
  analyzeCppCode: vi.fn(),
  askCourse: vi.fn(),
  cancelOcrJob: vi.fn(),
  cancelProcessingJob: vi.fn(),
  deleteDocument: vi.fn(),
  generateOutline: vi.fn(),
  generatePractice: vi.fn(),
  getCourse: vi.fn(),
  getLearningProfile: vi.fn(),
  getOcrJob: vi.fn(),
  getProcessingJobs: vi.fn(() => Promise.resolve([])),
  getSourceChunk: vi.fn(),
  isRequestCanceled: (error) => error?.name === "AbortError" || error?.code === "ERR_CANCELED",
  ocrDocument: vi.fn(),
  reindexCourse: vi.fn(),
  reindexDocument: vi.fn(),
  retryProcessingJob: vi.fn(),
  submitPracticeAttempt: vi.fn(),
  uploadDocument: vi.fn(),
  visionDocument: vi.fn()
}));

describe("CourseDetailView course lifecycle", () => {
  beforeEach(() => {
    routerMocks.route = reactive({ path: "/courses/1", query: { tab: "qa" } });
    routerMocks.push.mockReset();
    routerMocks.replace.mockReset();
    getCourse.mockReset();
    getLearningProfile.mockReset();
  });

  it("clears old state and ignores late responses when the id prop changes", async () => {
    const courseRequests = new Map([
      ["1", deferred()],
      ["2", deferred()]
    ]);
    const profileRequests = new Map([
      ["1", deferred()],
      ["2", deferred()]
    ]);
    getCourse.mockImplementation((id) => courseRequests.get(String(id)).promise);
    getLearningProfile.mockImplementation((id) => profileRequests.get(String(id)).promise);

    const wrapper = shallowMount(CourseDetailView, {
      props: { id: "1" },
      global: {
        directives: { loading: () => {} }
      }
    });
    await flushPromises();
    expect(getCourse).toHaveBeenCalledWith("1", expect.objectContaining({ signal: expect.any(AbortSignal) }));

    await wrapper.setProps({ id: "2" });
    expect(wrapper.text()).not.toContain("First course");

    courseRequests.get("2").resolve(coursePayload(2, "Second course"));
    profileRequests.get("2").resolve(profilePayload());
    await flushPromises();
    expect(wrapper.text()).toContain("Second course");

    courseRequests.get("1").resolve(coursePayload(1, "First course"));
    profileRequests.get("1").resolve(profilePayload());
    await flushPromises();
    expect(wrapper.text()).toContain("Second course");
    expect(wrapper.text()).not.toContain("First course");

    wrapper.unmount();
  });

  it("keeps the selected tab in the URL and follows history-driven query changes", async () => {
    getCourse.mockResolvedValue(coursePayload(1, "Course"));
    getLearningProfile.mockResolvedValue(profilePayload());

    const wrapper = shallowMount(CourseDetailView, {
      props: { id: "1" },
      global: {
        directives: { loading: () => {} },
        stubs: {
          ElTabs: {
            props: ["modelValue"],
            emits: ["update:modelValue"],
            template: `
              <div data-testid="tabs" :data-active="modelValue">
                <button data-testid="practice-tab" @click="$emit('update:modelValue', 'practice')">Practice</button>
                <slot />
              </div>
            `
          }
        }
      }
    });
    await flushPromises();

    expect(wrapper.get("[data-testid='tabs']").attributes("data-active")).toBe("qa");
    await wrapper.get("[data-testid='practice-tab']").trigger("click");
    await flushPromises();
    expect(routerMocks.push).toHaveBeenCalledWith({ query: { tab: "practice" } });

    routerMocks.push.mockClear();
    routerMocks.route.query.tab = "docs";
    await flushPromises();
    expect(wrapper.get("[data-testid='tabs']").attributes("data-active")).toBe("docs");
    expect(routerMocks.push).not.toHaveBeenCalled();

    wrapper.unmount();
  });
});

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function coursePayload(id, name) {
  return {
    id,
    name,
    description: `${name} description`,
    documents: [],
    recent_messages: []
  };
}

function profilePayload() {
  return {
    summary: { overall_mastery: 0 },
    knowledge_points: [],
    weak_points: []
  };
}
