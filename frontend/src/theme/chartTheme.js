export const chartColors = {
  primary: "#4f46e5",
  primarySoft: "#eef2ff",
  primaryAlpha: "rgba(79, 70, 229, 0.2)",
  sky: "#0ea5e9",
  success: "#16a34a",
  warning: "#f59e0b",
  danger: "#ef4444",
  text: "#0f172a",
  textSub: "#334155",
  muted: "#64748b",
  border: "#e2e8f0",
  surface: "#f8fafc"
};

export const chartPalette = [
  chartColors.primary,
  chartColors.sky,
  chartColors.warning,
  chartColors.danger,
  chartColors.success
];

export function masteryColor(score, state = "") {
  if (state === "weak" || score < 60) return chartColors.danger;
  if (state === "solid" || score >= 80) return chartColors.success;
  return chartColors.primary;
}
