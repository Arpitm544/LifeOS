import { bytesToBase64 } from "./syllabus.ts";

export const MAX_PHOTO_SIDE = 2048;
export const MAX_PHOTO_UPLOAD_BYTES = 4_500_000; // under the server's 5 MB limit
const qualities = [0.85, 0.7, 0.55, 0.4];

/** Scale (width, height) to fit within `max` on the longer side, never enlarging. */
export function fitWithin(width: number, height: number, max = MAX_PHOTO_SIDE): { width: number; height: number } {
  if (!(width > 0) || !(height > 0)) throw new Error("That image has no size.");
  const scale = Math.min(1, max / Math.max(width, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

/** The first JPEG quality whose output fits the upload limit; `encode` returns the encoded size. */
export async function pickQuality(encode: (quality: number) => Promise<number>, limit = MAX_PHOTO_UPLOAD_BYTES): Promise<number | null> {
  for (const quality of qualities) if (await encode(quality) <= limit) return quality;
  return null;
}

/**
 * Browser only: decode the photo (applying its EXIF rotation), shrink it and re-encode as JPEG.
 * Re-encoding also strips location and camera metadata before upload.
 */
export async function preparePhoto(file: Blob): Promise<{ base64: string; dataUrl: string; bytes: number; width: number; height: number }> {
  let bitmap: ImageBitmap;
  try { bitmap = await createImageBitmap(file, { imageOrientation: "from-image" }); }
  catch { throw new Error("This browser cannot open that photo. Use a JPEG or PNG, or take the photo again."); }
  const size = fitWithin(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = size.width; canvas.height = size.height;
  const context = canvas.getContext("2d");
  if (!context) { bitmap.close(); throw new Error("Could not prepare the photo. Please try again."); }
  context.fillStyle = "#fff"; context.fillRect(0, 0, size.width, size.height); // transparent PNGs become white, not black
  context.drawImage(bitmap, 0, 0, size.width, size.height);
  bitmap.close();
  const blobs = new Map<number, Blob>();
  const encode = async (quality: number) => {
    const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/jpeg", quality));
    if (!blob) throw new Error("Could not prepare the photo. Please try again.");
    blobs.set(quality, blob);
    return blob.size;
  };
  const quality = await pickQuality(encode);
  if (quality === null) throw new Error("That photo is too detailed to send. Crop it or take it closer.");
  const blob = blobs.get(quality)!;
  const base64 = bytesToBase64(new Uint8Array(await blob.arrayBuffer()));
  return { base64, dataUrl: `data:image/jpeg;base64,${base64}`, bytes: blob.size, ...size };
}
