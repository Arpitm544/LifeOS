import assert from "node:assert/strict";
import test from "node:test";
import { renderCanvas } from "../src/lib/render-canvas.ts";

test("canvas respects reduced motion, scales to its surface, and releases listeners and frames", () => {
  const originals = ["window", "ResizeObserver", "localStorage"].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)] as const);
  let observed: unknown, disconnected = false, clears = 0, reduced = false;
  let onResize!: () => void;
  Object.defineProperty(globalThis, "ResizeObserver", { configurable: true, value: class {
    constructor(callback: () => void) { onResize = callback; }
    observe(surface: unknown) { observed = surface; }
    disconnect() { disconnected = true; }
  } });
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: { getItem: () => reduced ? "true" : null } });
  const frames = new Map<number, FrameRequestCallback>();
  let nextFrame = 0;
  let strokes = 0;
  const motion = Object.assign(new EventTarget(), { matches: false });
  const host = Object.assign(new EventTarget(), {
    devicePixelRatio: 3,
    matchMedia: () => motion,
    requestAnimationFrame: (callback: FrameRequestCallback) => { frames.set(++nextFrame, callback); return nextFrame; },
    cancelAnimationFrame: (id: number) => { frames.delete(id); },
  });
  Object.defineProperty(globalThis, "window", { value: host, configurable: true });
  try {
    const surface = Object.assign(new EventTarget(), {
      clientWidth: 500, clientHeight: 300,
      getBoundingClientRect: () => ({ left: 10, top: 20 }),
    });
    const canvas = { parentElement: surface, width: 0, height: 0, getContext: () => ({
      clearRect() { clears++; }, setTransform() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() { strokes++; },
    }) };
    const dispose = renderCanvas(canvas as unknown as HTMLCanvasElement);
    assert.equal(canvas.width, 1000, "pixel ratio is capped at two");
    assert.equal(canvas.height, 600);
    assert.equal(observed, surface);
    surface.clientHeight = 400; surface.clientWidth = 600;
    onResize();
    assert.equal(canvas.height, 800, "content changes resize the backing store");
    assert.equal(canvas.width, 1200);
    const move = () => surface.dispatchEvent(Object.assign(new Event("pointermove"), { clientX: 100, clientY: 80, pointerType: "mouse" }));
    move();
    assert.equal(frames.size, 0, "reduced motion schedules no work");
    motion.matches = true;
    move(); move();
    assert.equal(frames.size, 1, "pointer movement shares one animation frame");
    const flush = (time: number) => {
      const [id, callback] = frames.entries().next().value!;
      frames.delete(id);
      callback(time);
    };
    flush(performance.now());
    assert.ok(strokes > 0, "movement draws a trail");
    flush(performance.now() + 500);
    assert.equal(frames.size, 0, "idle trails expire without a permanent animation loop");
    move();
    motion.matches = false;
    motion.dispatchEvent(new Event("change"));
    assert.equal(frames.size, 0, "motion preference changes stop animation");
    motion.matches = true;
    move();
    dispose?.();
    assert.equal(frames.size, 0, "unmount cancels animation");
    const lastClears = clears;
    move();
    surface.dispatchEvent(new Event("pointerleave"));
    motion.dispatchEvent(new Event("change"));
    surface.clientHeight = 500;
    host.dispatchEvent(new Event("resize"));
    assert.equal(canvas.height, 800);
    assert.equal(clears, lastClears, "unmount removes leave and media listeners");
    assert.equal(disconnected, true, "unmount disconnects surface observation");
    assert.equal(frames.size, 0, "unmount removes pointer listener");
    reduced = true;
    const disposeReduced = renderCanvas(canvas as unknown as HTMLCanvasElement);
    move();
    assert.equal(frames.size, 0, "Profile reduced motion disables pointer trails");
    disposeReduced?.();
  } finally {
    for (const [key, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else Reflect.deleteProperty(globalThis, key);
    }
  }
});

test("canvas degrades gracefully when a rendering context is unavailable", () => {
  assert.equal(renderCanvas({ getContext: () => null } as unknown as HTMLCanvasElement), undefined);
});
