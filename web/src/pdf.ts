// "legacy" derleme: pdf.js'in normal derlemesi yalnızca en yeni tarayıcıda çalışır
// (Map.getOrInsertComputed, Math.sumPrecise... yedeksiz kullanılır). Biraz eski bir Edge/Chrome'da
// hiçbir sayfa çizilmez; legacy derleme bu API'leri kendisi sağlar.
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import type { PDFDocumentProxy } from "pdfjs-dist/legacy/build/pdf.mjs";
import workerUrl from "pdfjs-dist/legacy/build/pdf.worker.min.mjs?url";
import { api } from "./api";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export class PasswordNeededError extends Error {
  constructor(public wrong: boolean) {
    super(wrong ? "Şifre yanlış" : "Bu PDF şifreli");
  }
}

/** Önbellek anahtarı için sürüm kimliği. Sürüm NUMARASI yeniden kullanılır (Kaydet → v2, Önceki
 * sürüme dön → v1, Kaydet → yeni v2); `updated` (sürümün oluşturulma zamanı) her sürümde farklıdır.
 * `FileMeta` bu alanları taşır. */
export interface PdfRef {
  id: string;
  version: number;
  updated: number;
}

const refKey = (ref: PdfRef) => `${ref.id}@${ref.version}:${ref.updated}`;

const docs = new Map<string, { task: ReturnType<typeof pdfjs.getDocument>; doc: Promise<PDFDocumentProxy> }>();

/** Aynı dosya + sürüm bir kez açılır, sonra önbellekten verilir. */
export function openPdf(ref: PdfRef, password?: string): Promise<PDFDocumentProxy> {
  const key = refKey(ref);
  let entry = docs.get(key);
  if (!entry) {
    // Büyük dosya (GB'lar): yalnızca çizilen sayfaların baytları aralık isteğiyle istenir. Yoksa
    // pdf.js arka planda bütün dosyayı tarayıcı belleğine çeker (ölçüldü: 2 GB'lık dosyada 15 sn'de
    // 578 MB ve sürüyordu; 8 GB'ta tarayıcı belleği tükenir). Parça boyutu varsayılanda (64 KB)
    // kalır: pdf.js açılışta bütün sayfa nesnelerini okur, bunlar resimlerin arasına dağılmıştır;
    // 1 MB'lık parçayla her küçük nesne 1 MB indirme demekti. Büyük resim yine tek istekte gelir
    // (bitişik parçalar birleştirilir).
    const task = pdfjs.getDocument({
      url: api.rawUrl(ref.id, ref.version),
      password,
      withCredentials: true,
      disableAutoFetch: true,
      disableStream: true,
    });
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

/** Dosyanın açık belgelerini ve küçük resimlerini bırakır (yeni sürüm kaydedilince, geri alınınca).
 * Anahtarlar zaten sürüme özgü; bu bellek içindir. */
export function forgetPdf(fileId: string): void {
  for (const [key, entry] of [...docs.entries()]) {
    if (key.startsWith(`${fileId}@`)) {
      void entry.task.destroy().catch(() => undefined);
      docs.delete(key);
    }
  }
  for (const key of [...thumbs.keys()]) {
    if (key.startsWith(`${fileId}@`)) thumbs.delete(key);
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
export function thumbnail(ref: PdfRef, pageIndex: number, width: number, password?: string): Promise<string> {
  const key = `${refKey(ref)}#${pageIndex}w${width}`;
  let p = thumbs.get(key);
  if (!p) {
    p = slot(async () => {
      const doc = await openPdf(ref, password);
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
