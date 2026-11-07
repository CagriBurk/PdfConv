/** Sayfa düzenleyicinin klavye mantığı (saf fonksiyonlar; vitest'li).
 *
 * Izgara bir seçim listesidir: oklar odağı taşır (ve tek sayfayı seçer), Shift+ok seçimi
 * genişletir, Ctrl+ok yalnızca odağı taşır, Boşluk odaktaki sayfanın seçimini değiştirir, Alt+ok
 * seçili sayfaları bir konum taşır, Enter büyük önizlemeyi açar. */

export interface Keyed {
  key: string;
}

/** Ok / Home / End tuşunda odaklanacak yeni konum; tuş gezinme tuşu değilse null. */
export function nextIndex(key: string, index: number, count: number, columns: number): number | null {
  if (count === 0) return null;
  const cols = Math.max(1, columns);
  let next: number;
  switch (key) {
    case "ArrowLeft":
      next = index - 1;
      break;
    case "ArrowRight":
      next = index + 1;
      break;
    case "ArrowUp":
      next = index - cols;
      break;
    case "ArrowDown":
      next = index + cols;
      break;
    case "Home":
      next = 0;
      break;
    case "End":
      next = count - 1;
      break;
    default:
      return null;
  }
  return Math.min(count - 1, Math.max(0, next));
}

/** Seçili öğeleri birlikte bir konum öne (-1) ya da arkaya (+1) taşır; göreli sıraları korunur.
 * Seçimden biri zaten uçtaysa taşınamaz (null). */
export function moveSelected<T extends Keyed>(items: T[], selected: Set<string>, delta: -1 | 1): T[] | null {
  if (!selected.size) return null;
  const idx = items.map((it, i) => (selected.has(it.key) ? i : -1)).filter((i) => i >= 0);
  if (!idx.length) return null;
  if (delta < 0 && idx[0] === 0) return null;
  if (delta > 0 && idx[idx.length - 1] === items.length - 1) return null;
  const out = [...items];
  const order = delta < 0 ? out.map((_, i) => i) : out.map((_, i) => out.length - 1 - i);
  for (const i of order) {
    const j = i + delta;
    if (j < 0 || j >= out.length) continue;
    if (selected.has(out[i].key) && !selected.has(out[j].key)) [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/** Bağlantı noktasıyla (anchor) hedef arasındaki öğelerin anahtarları (iki uç dahil). */
export function rangeKeys<T extends Keyed>(items: T[], anchorKey: string | null, toKey: string): string[] {
  const b = items.findIndex((i) => i.key === toKey);
  const a = anchorKey === null ? b : items.findIndex((i) => i.key === anchorKey);
  if (a === -1 || b === -1) return b === -1 ? [] : [toKey];
  const [lo, hi] = a < b ? [a, b] : [b, a];
  return items.slice(lo, hi + 1).map((i) => i.key);
}

/** Silmeden sonra odaklanacak öğe: silinenlerin ilkinin yerine gelen, yoksa bir öncesi. */
export function focusAfterDelete<T extends Keyed>(before: T[], after: T[], selected: Set<string>): string | null {
  if (!after.length) return null;
  const first = before.findIndex((i) => selected.has(i.key));
  const survivorsBefore = before.slice(0, Math.max(0, first)).filter((i) => !selected.has(i.key)).length;
  return after[Math.min(survivorsBefore, after.length - 1)].key;
}

/** Izgaradaki sütun sayısı: ilk satırdaki öğeler (aynı üst konumda olanlar). */
export function columnsOf(tops: number[]): number {
  if (!tops.length) return 1;
  const first = tops[0];
  let n = 0;
  while (n < tops.length && Math.abs(tops[n] - first) < 2) n++;
  return Math.max(1, n);
}
