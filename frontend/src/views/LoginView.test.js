import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginView from "./LoginView.vue";
import { login } from "../api/client";

const routerMocks = vi.hoisted(() => ({
  route: { query: { redirect: "/courses" } },
  replace: vi.fn()
}));

vi.mock("vue-router", () => ({
  useRoute: () => routerMocks.route,
  useRouter: () => ({ replace: routerMocks.replace })
}));

vi.mock("element-plus", () => ({
  ElMessage: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn()
  }
}));

vi.mock("../api/client", () => ({
  login: vi.fn(),
  register: vi.fn()
}));

const elementStubs = {
  ElTabs: { template: "<div><slot /></div>" },
  ElTabPane: { template: "<div />" },
  ElForm: {
    emits: ["submit"],
    template: "<form @submit=\"$emit('submit', $event)\"><slot /></form>"
  },
  ElFormItem: { template: "<label><slot /></label>" },
  ElInput: {
    inheritAttrs: false,
    props: ["modelValue", "placeholder", "type"],
    emits: ["update:modelValue"],
    template: `
      <input
        :value="modelValue"
        :placeholder="placeholder"
        :type="type || 'text'"
        @input="$emit('update:modelValue', $event.target.value)"
      />
    `
  },
  ElButton: {
    props: ["nativeType"],
    template: "<button :type=\"nativeType || 'button'\"><slot /></button>"
  },
  ElIcon: { template: "<span aria-hidden='true'><slot /></span>" },
  Right: { template: "<span aria-hidden='true' />" }
};

describe("LoginView keyboard submission", () => {
  beforeEach(() => {
    login.mockReset();
    login.mockResolvedValue({ access_token: "test-token" });
    routerMocks.replace.mockReset();
  });

  it("uses a native submit button so Enter submits the login form", async () => {
    const wrapper = mount(LoginView, { global: { stubs: elementStubs } });

    await wrapper.get("input[placeholder='name@example.com']").setValue("student@example.com");
    await wrapper.get("input[placeholder='请输入密码']").setValue("secret-password");
    expect(wrapper.get("button").attributes("type")).toBe("submit");

    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(login).toHaveBeenCalledTimes(1);
    expect(login).toHaveBeenCalledWith({
      email: "student@example.com",
      password: "secret-password"
    });
    expect(routerMocks.replace).toHaveBeenCalledWith("/courses");
  });
});
