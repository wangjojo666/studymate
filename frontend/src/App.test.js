import axe from "axe-core";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import App from "./App.vue";
import { getHealthDetail } from "./api/client";

vi.mock("./api/client", () => ({
  clearAuthSession: vi.fn(),
  getHealthDetail: vi.fn(),
  getStoredUser: vi.fn(() => ({ email: "student@example.com", display_name: "Student" }))
}));

const elementStubs = {
  ElContainer: { template: "<div><slot /></div>" },
  ElAside: { template: "<aside><slot /></aside>" },
  ElDrawer: {
    props: ["modelValue"],
    template: "<aside v-if='modelValue'><slot /></aside>"
  },
  ElMenu: { template: "<div><slot /></div>" },
  ElMenuItem: {
    props: ["index"],
    template: "<a :href='index'><slot /></a>"
  },
  ElIcon: { template: "<span aria-hidden='true'><slot /></span>" },
  ElHeader: { template: "<header><slot /></header>" },
  ElMain: { template: "<main><slot /></main>" },
  ElButton: {
    template: "<button type='button'><slot /></button>"
  },
  Reading: { template: "<span aria-hidden='true' />" },
  Cpu: { template: "<span aria-hidden='true' />" },
  Expand: { template: "<span aria-hidden='true' />" }
};

describe("App navigation and capability status", () => {
  beforeEach(() => {
    getHealthDetail.mockResolvedValue({
      capability_label: "离线规则生成 · Hash 检索"
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("offers an accessible mobile drawer and never advertises unavailable providers", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/", component: { template: "<div>Dashboard</div>" } }]
    });
    await router.push("/");
    await router.isReady();

    const wrapper = mount(App, {
      attachTo: document.body,
      global: { plugins: [router], stubs: elementStubs }
    });
    await flushPromises();

    expect(wrapper.text()).toContain("离线规则生成 · Hash 检索");
    expect(wrapper.text()).not.toContain("DeepSeek");
    expect(wrapper.text()).not.toContain("本地 OCR");
    expect(wrapper.text()).not.toContain("错题本");
    expect(wrapper.text()).not.toContain("复习计划");
    expect(wrapper.text()).not.toContain("账号");

    const menuButton = wrapper.get("button[aria-label='打开主导航']");
    expect(menuButton.element.tagName).toBe("BUTTON");
    expect(wrapper.get("a.brand").attributes("href")).toBe("/");
    await menuButton.trigger("click");
    expect(wrapper.get("nav[aria-label='移动端主导航']").exists()).toBe(true);

    const results = await axe.run(wrapper.element, {
      rules: {
        region: { enabled: false },
        "color-contrast": { enabled: false }
      }
    });
    expect(results.violations).toEqual([]);
    wrapper.unmount();
  });

  it("serially refreshes the effective capability label", async () => {
    vi.useFakeTimers();
    getHealthDetail
      .mockResolvedValueOnce({ capability_label: "BGE Embedding（已配置，未验证）" })
      .mockResolvedValueOnce({ capability_label: "离线规则生成 · Hash 检索" });
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/", component: { template: "<div>Dashboard</div>" } }]
    });
    await router.push("/");
    await router.isReady();
    const wrapper = mount(App, {
      global: { plugins: [router], stubs: elementStubs }
    });
    await flushPromises();
    expect(wrapper.text()).toContain("BGE Embedding（已配置，未验证）");

    await vi.advanceTimersByTimeAsync(60_000);
    await flushPromises();

    expect(getHealthDetail).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("离线规则生成 · Hash 检索");
    wrapper.unmount();
  });
});
