// Local adaptation of the canvas hero effect: https://21st.dev/@designali-in/components/canvas
export function renderCanvas(canvas: HTMLCanvasElement) {
  const context = canvas.getContext("2d");
  const surface = canvas.parentElement;
  if (!context || !surface) return;

  const motion = window.matchMedia("(prefers-reduced-motion: no-preference) and (pointer: fine)");
  let reducedMotion = false;
  try { reducedMotion = localStorage.getItem("lifeos.reduced-motion") === "true"; } catch { /* Use the system preference when storage is unavailable. */ }
  let points: { x: number; y: number; time: number }[] = [];
  let frame = 0;
  let width = 0;
  let height = 0;

  const clear = () => {
    window.cancelAnimationFrame(frame);
    frame = 0;
    points = [];
    context.clearRect(0, 0, width, height);
  };
  const resize = () => {
    clear();
    width = surface.clientWidth;
    height = surface.clientHeight;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
  };
  const draw = (time: number) => {
    frame = 0;
    context.clearRect(0, 0, width, height);
    points = points.filter((point) => time - point.time < 450);
    context.lineCap = "round";
    for (let i = 1; i < points.length; i++) {
      context.beginPath();
      context.moveTo(points[i - 1].x, points[i - 1].y);
      context.lineTo(points[i].x, points[i].y);
      context.strokeStyle = `rgba(52, 92, 244, ${0.3 * (1 - (time - points[i].time) / 450)})`;
      context.lineWidth = 2;
      context.stroke();
    }
    if (points.length) frame = window.requestAnimationFrame(draw);
  };
  const move = (event: PointerEvent) => {
    if (reducedMotion || !motion.matches || event.pointerType === "touch") return;
    const rect = surface.getBoundingClientRect();
    points.push({ x: event.clientX - rect.left, y: event.clientY - rect.top, time: performance.now() });
    points = points.slice(-40);
    if (!frame) frame = window.requestAnimationFrame(draw);
  };

  resize();
  surface.addEventListener("pointermove", move);
  surface.addEventListener("pointerleave", clear);
  motion.addEventListener("change", clear);
  const observer = new ResizeObserver(resize);
  observer.observe(surface);
  return () => {
    clear();
    surface.removeEventListener("pointermove", move);
    surface.removeEventListener("pointerleave", clear);
    motion.removeEventListener("change", clear);
    observer.disconnect();
  };
}
