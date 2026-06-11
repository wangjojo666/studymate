export function getApiErrorMessage(error, fallback = "请求失败，请检查后端服务是否启动") {
  if (error?.userMessage) return error.userMessage;
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || String(item))
      .filter(Boolean)
      .join("；") || fallback;
  }
  if (detail) return detail;
  if (error?.code === "ECONNABORTED") return "请求超时，任务可能仍在后台运行，请稍后刷新状态";
  if (error?.code === "ERR_NETWORK") return "后端服务未启动或网络异常";
  if (error?.message) return `${fallback}：${error.message}`;
  return fallback;
}
