import assert from "node:assert/strict";
import test from "node:test";
import { fitWithin, MAX_PHOTO_UPLOAD_BYTES, pickQuality } from "../src/lib/photo.ts";

test("photos shrink to 2048 px on the longer side and are never enlarged", () => {
  assert.deepEqual(fitWithin(4032, 3024), { width: 2048, height: 1536 });
  assert.deepEqual(fitWithin(3024, 4032), { width: 1536, height: 2048 });
  assert.deepEqual(fitWithin(800, 600), { width: 800, height: 600 });
  assert.deepEqual(fitWithin(10000, 3), { width: 2048, height: 1 });
  assert.throws(() => fitWithin(0, 100), /no size/);
  assert.throws(() => fitWithin(Number.NaN, 100), /no size/);
});

test("the best JPEG quality that fits the upload limit is used", async () => {
  const tried: number[] = [];
  const sizes: Record<number, number> = { 0.85: 6_000_000, 0.7: 4_000_000, 0.55: 3_000_000, 0.4: 2_000_000 };
  assert.equal(await pickQuality(async q => { tried.push(q); return sizes[q]; }), 0.7);
  assert.deepEqual(tried, [0.85, 0.7]);
  assert.equal(await pickQuality(async () => 100), 0.85);
  assert.equal(await pickQuality(async () => MAX_PHOTO_UPLOAD_BYTES + 1), null);
  assert.ok(MAX_PHOTO_UPLOAD_BYTES < 5 * 1024 * 1024, "must stay under the server's 5 MB limit");
});
