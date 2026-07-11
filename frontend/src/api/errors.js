export function normalizeApiError(error) {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) {
    const message = detail
      .map((item) => item?.msg || item?.message || String(item))
      .filter(Boolean)
      .join("；");
    if (message) return message;
  }
  if (detail) return String(detail);

  if (error?.code === "ECONNABORTED") {
    return "请求超时，任务可能仍在后台运行，请稍后刷新状态";
  }
  if (error?.code === "ERR_NETWORK") {
    return "后端服务未启动或网络异常";
  }

  if (error?.response?.status === 401) {
    return "登录已过期，请重新登录";
  }

  return "";
}

export function getApiErrorMessage(error, fallback = "请求失败，请检查后端服务是否启动") {
  const normalized = error?.userMessage || normalizeApiError(error);
  if (normalized) return normalized;
  if (error?.message) return `${fallback}：${error.message}`;
  return fallback;
}
