export function getApiErrorMessage(error, fallback = "请求失败，请检查后端服务是否启动") {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || String(item))
      .filter(Boolean)
      .join("；") || fallback;
  }
  if (detail) return detail;
  if (error?.code === "ERR_NETWORK") return "请求失败，请检查后端服务是否启动";
  if (error?.message) return `${fallback}：${error.message}`;
  return fallback;
}
