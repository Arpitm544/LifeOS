"use client";

import { useEffect, useRef } from "react";
import { renderCanvas } from "@/lib/render-canvas";

export function Canvas() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (ref.current) return renderCanvas(ref.current);
  }, []);
  return <canvas ref={ref} className="hero-canvas" aria-hidden="true" />;
}
