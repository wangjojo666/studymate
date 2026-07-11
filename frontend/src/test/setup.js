import { config } from "@vue/test-utils";

config.global.stubs = {
  transition: false,
  "transition-group": false
};

class ResizeObserverStub {
  observe() {}

  unobserve() {}

  disconnect() {}
}

globalThis.ResizeObserver = ResizeObserverStub;
globalThis.matchMedia = globalThis.matchMedia || (() => ({
  matches: false,
  addEventListener() {},
  removeEventListener() {},
  addListener() {},
  removeListener() {}
}));
