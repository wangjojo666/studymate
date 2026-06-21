import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      onwarn(warning, warn) {
        if (
          warning.code === "INVALID_ANNOTATION" &&
          warning.id?.replace(/\\/g, "/").includes("node_modules/@vueuse/core")
        ) {
          return;
        }
        warn(warning);
      },
      output: {
        manualChunks(id) {
          const normalizedId = id.replace(/\\/g, "/");
          if (!normalizedId.includes("node_modules")) return undefined;
          if (
            normalizedId.includes("node_modules/echarts") ||
            normalizedId.includes("node_modules/zrender") ||
            normalizedId.includes("node_modules/vue-echarts")
          ) {
            return "charts";
          }
          if (
            normalizedId.includes("node_modules/element-plus") ||
            normalizedId.includes("node_modules/@element-plus")
          ) {
            return "element-plus";
          }
          if (
            normalizedId.includes("node_modules/@vue") ||
            normalizedId.includes("node_modules/vue") ||
            normalizedId.includes("node_modules/vue-router")
          ) {
            return "vue-vendor";
          }
          if (normalizedId.includes("node_modules/axios")) {
            return "http-client";
          }
          return "vendor";
        }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true
      }
    }
  }
});
