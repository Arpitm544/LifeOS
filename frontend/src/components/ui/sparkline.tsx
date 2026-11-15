import { sparklinePoints } from "@/lib/sparkline";

/** A small 14-day trend line for a metric card. The values are also given to screen readers as text. */
export function Sparkline({ values, label, max, width = 120, height = 28 }: { values: (number | null)[]; label: string; max?: number; width?: number; height?: number }) {
  const points = sparklinePoints(values, width, height, max);
  if (!points) return null;
  return <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={label} preserveAspectRatio="none">
    <polyline points={points} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
  </svg>;
}
