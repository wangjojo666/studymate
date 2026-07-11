import { flushPromises, shallowMount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LearningDiagnosisView from "./LearningDiagnosisView.vue";
import {
  getCourse,
  getKnowledgeGraph,
  getLearningProfile,
  getWrongAttempts
} from "../api/client";

const routerMocks = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: routerMocks.push })
}));

vi.mock("element-plus", () => ({
  ElMessage: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn()
  }
}));

vi.mock("vue-echarts", () => ({
  default: { name: "VChart", template: "<div />" }
}));

vi.mock("echarts/core", () => ({ use: vi.fn() }));
vi.mock("echarts/charts", () => ({
  BarChart: {},
  GaugeChart: {},
  GraphChart: {},
  PieChart: {},
  RadarChart: {}
}));
vi.mock("echarts/components", () => ({
  GridComponent: {},
  LegendComponent: {},
  TitleComponent: {},
  TooltipComponent: {}
}));
vi.mock("echarts/renderers", () => ({ CanvasRenderer: {} }));

vi.mock("../api/client", () => ({
  downloadLearningReport: vi.fn(),
  generateReviewPlan: vi.fn(),
  getCourse: vi.fn(),
  getKnowledgeGraph: vi.fn(),
  getLearningProfile: vi.fn(),
  getWrongAttempts: vi.fn(),
  isRequestCanceled: (error) => error?.name === "AbortError" || error?.code === "ERR_CANCELED",
  submitPracticeAttempt: vi.fn(),
  updateReviewTask: vi.fn()
}));

describe("LearningDiagnosisView course lifecycle", () => {
  beforeEach(() => {
    routerMocks.push.mockReset();
    getCourse.mockReset();
    getKnowledgeGraph.mockReset();
    getLearningProfile.mockReset();
    getWrongAttempts.mockReset();
  });

  it("aborts the old course session, clears stale state, and ignores late responses", async () => {
    const requests = new Map([
      ["1", diagnosisRequests()],
      ["2", diagnosisRequests()]
    ]);
    const courseSignals = new Map();
    getCourse.mockImplementation((id, options) => {
      courseSignals.set(String(id), options.signal);
      return requests.get(String(id)).course.promise;
    });
    getLearningProfile.mockImplementation((id) => requests.get(String(id)).profile.promise);
    getKnowledgeGraph.mockImplementation((id) => requests.get(String(id)).graph.promise);
    getWrongAttempts.mockImplementation((id) => requests.get(String(id)).wrong.promise);

    const wrapper = shallowMount(LearningDiagnosisView, {
      props: { id: "1" },
      global: { directives: { loading: () => {} } }
    });
    await flushPromises();
    expect(getCourse).toHaveBeenCalledWith("1", expect.objectContaining({ signal: expect.any(AbortSignal) }));

    await wrapper.setProps({ id: "2" });
    expect(courseSignals.get("1").aborted).toBe(true);
    expect(wrapper.text()).not.toContain("First diagnosis");

    resolveDiagnosis(requests.get("2"), 2, "Second diagnosis");
    await flushPromises();
    expect(wrapper.text()).toContain("Second diagnosis");

    resolveDiagnosis(requests.get("1"), 1, "First diagnosis");
    await flushPromises();
    expect(wrapper.text()).toContain("Second diagnosis");
    expect(wrapper.text()).not.toContain("First diagnosis");

    wrapper.unmount();
  });
});

function diagnosisRequests() {
  return {
    course: deferred(),
    profile: deferred(),
    graph: deferred(),
    wrong: deferred()
  };
}

function resolveDiagnosis(requests, id, name) {
  requests.course.resolve({ id, name, description: `${name} description` });
  requests.profile.resolve({
    summary: {
      overall_mastery: 0,
      knowledge_point_count: 0,
      study_actions: 0,
      question_count: 0,
      practice_accuracy: 0
    },
    knowledge_points: [],
    weak_points: [],
    recommendations: [],
    pending_tasks: []
  });
  requests.graph.resolve({ nodes: [], edges: [] });
  requests.wrong.resolve([]);
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
