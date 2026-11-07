/** Markdown canlı önizlemesinin yardımcıları (tarayıcı API'si gerektirmeyenler; vitest'li).
 *
 * Önizleme her güncellemede yeniden yüklenirse (`srcdoc`) kaydırma başa atlar. Bunun yerine:
 * belgenin "kabuğu" (tema CSS'i, makrolar, kağıt yönü) aynıysa yalnızca gövde yerinde değiştirilir,
 * formüller çerçevenin kendi KaTeX'iyle çizilir; kabuk değiştiyse çerçeve yeniden yüklenir ve
 * kaydırma oranı korunur. Her yanıt bir sıra numarası taşır: geç gelen eski yanıt yenisinin
 * üstüne yazılmaz. */

/** Kabuğu karşılaştırmak için: her istekte değişen nonce'lar çıkarılır. */
export function shellKey(html: string): string {
  const head = html.split(/<body[\s>]/i)[0] ?? "";
  const bodyTag = /<body([^>]*)>/i.exec(html)?.[1] ?? "";
  return (head + "|" + bodyTag).replace(/ nonce="[^"]*"/g, "").replace(/'nonce-[^']*'/g, "");
}

/** Gövdenin içeriği (son KaTeX başlatıcısı hariç: yerinde güncellemede çerçeve zaten çizer). */
export function bodyInner(html: string): string {
  const m = /<body[^>]*>([\s\S]*)<\/body>/i.exec(html);
  const inner = m ? m[1] : "";
  const lastScript = inner.lastIndexOf("<script");
  return lastScript === -1 ? inner : inner.slice(0, lastScript);
}

/** Kaydırma oranı (0–1): yükseklik değişse de aynı yere yakın dönülür. */
export function scrollRatio(top: number, scrollHeight: number, clientHeight: number): number {
  const max = scrollHeight - clientHeight;
  return max > 0 ? Math.min(1, Math.max(0, top / max)) : 0;
}

/** Sıra denetimi: yalnızca en son gönderilen isteğin yanıtı kabul edilir. */
export function createSequencer() {
  let latest = 0;
  return {
    next: () => ++latest,
    isLatest: (n: number) => n === latest,
  };
}
