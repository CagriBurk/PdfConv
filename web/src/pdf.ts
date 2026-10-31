import * as pdfjs from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { api } from "./api";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export class PasswordNeededError extends Error {
  constructor(public wrong: boolean) {
    super(wrong ? "Şifre yanlış" : "Bu PDF şifreli");
  }
}

const docs = new Map<string, { task: ReturnType<typeof pdfjs.getDocument>; doc: Promise<PDFDocumentProxy> }>();

/** Aynı dosya + sürüm bir kez açılır, sonra önbellekten verilir. */
export function openPdf(fileId: string, version: number, password?: string): Promise<PDFDocumentProxy> {
  const key = `${fileId}@${version}`;
  let entry = docs.get(key);
  if (!entry) {
    const task = pdfjs.getDocument({ url: api.rawUrl(fileId, version), password, withCredentials: true });
    const doc = task.promise.catch((e: { name?: string; code?: number }) => {
      docs.delete(key);
      if (e?.name === "PasswordException") throw new PasswordNeededError(e.code === 2);
      throw e;
    });
    entry = { task, doc };
    docs.set(key, entry);
  }
  return entry.doc;
}

/** Dosyanın açık belgelerini kapatır (yeni sürüm kaydedilince). */
export function forgetPdf(fileId: string): void {
  for (const [key, entry] of [...docs.entries()]) {
    if (key.startsWith(`${fileId}@`)) {
      void entry.task.destroy().catch(() => undefined);
      docs.delete(key);
    }
  }
}

const thumbs = new Map<string, Promise<string>>();
// Aynı anda çok sayfa çizmek arayüzü kilitler; küçük bir sıra.
let running = 0;
const queue: (() => void)[] = [];
const MAX_PARALLEL = 3;

function slot<T>(fn: () => Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const start = () => {
      running++;
      fn()
        .then(resolve, reject)
        .finally(() => {
          running--;
          queue.shift()?.();
        });
    };
    if (running < MAX_PARALLEL) start();
    else queue.push(start);
  });
}

/** Sayfanın küçük resmi (data URL). Kaynaktaki döndürme pdf.js tarafından uygulanır. */
export function thumbnail(
  fileId: string,
  version: number,
  pageIndex: number,
  width: number,
  password?: string,
): Promise<string> {
  const key = `${fileId}@${version}#${pageIndex}w${width}`;
  let p = thumbs.get(key);
  if (!p) {
    p = slot(async () => {
      const doc = await openPdf(fileId, version, password);
      const page = await doc.getPage(pageIndex + 1);
      const base = page.getViewport({ scale: 1 });
      const ratio = window.devicePixelRatio || 1;
      const viewport = page.getViewport({ scale: (width / base.width) * ratio });
      const canvas = document.createElement("canvas");
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      await page.render({ canvas, viewport }).promise;
      const url = canvas.toDataURL("image/jpeg", 0.82);
      page.cleanup();
      return url;
    });
    p.catch(() => thumbs.delete(key));
    thumbs.set(key, p);
  }
  return p;
}
