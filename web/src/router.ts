import { useEffect, useSyncExternalStore } from "react";

/** Basit karma (#) yönlendirici: "#/duzenle/abc?x=1" → { path: ["duzenle", "abc"], query }
 *
 * Kaydedilmemiş iş koruması: bir ekran `useLeaveGuard(dirty)` ile kayıt olur. Uygulama içi
 * gezinmede (bağlantı, `navigate`, geri/ileri düğmeleri) "çıkılsın mı?" sorulur; vazgeçilirse
 * adres eski hâline döner ve ekran yerinde kalır. Sekme kapanırken tarayıcının kendi uyarısı
 * (`beforeunload`) çıkar. Hash değişimi `beforeunload`'u tetiklemediği için ikisi de gerekir. */
export interface Route {
  path: string[];
  query: URLSearchParams;
}

export const LEAVE_MESSAGE = "Kaydedilmemiş değişiklikler var. Çıkarsan kaybolacak. Çıkılsın mı?";

function parse(hash: string): Route {
  const raw = hash.replace(/^#\/?/, "");
  const [p, q = ""] = raw.split("?");
  return { path: p.split("/").filter(Boolean).map(decodeURIComponent), query: new URLSearchParams(q) };
}

const guards = new Set<() => boolean>();
const listeners = new Set<() => void>();
let currentHash = window.location.hash;
let current: Route = parse(currentHash);

function isDirty(): boolean {
  for (const g of guards) if (g()) return true;
  return false;
}

/** Kullanıcıya sorar; onay verilirse ya da kaydedilmemiş iş yoksa true. */
export function confirmLeave(): boolean {
  return !isDirty() || window.confirm(LEAVE_MESSAGE);
}

function commit(hash: string): void {
  currentHash = hash;
  current = parse(hash);
  listeners.forEach((l) => l());
}

window.addEventListener("hashchange", () => {
  const next = window.location.hash;
  if (next === currentHash) return;
  if (!confirmLeave()) {
    // Adres çubuğu eski ekranı göstersin; pushState hashchange tetiklemez.
    history.pushState(null, "", currentHash || "#/");
    return;
  }
  commit(next);
});

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useRoute(): Route {
  return useSyncExternalStore(subscribe, () => current);
}

/** Ekran kaydedilmemiş iş taşırken uygulama içi gezinmeyi ve sekme kapatmayı sorar. */
export function useLeaveGuard(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return;
    const guard = () => true;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    guards.add(guard);
    window.addEventListener("beforeunload", warn);
    return () => {
      guards.delete(guard);
      window.removeEventListener("beforeunload", warn);
    };
  }, [dirty]);
}

/** Uygulama içi gezinme. `force`: kaydetme bittikten sonraki gibi, bilinçli geçişlerde sormaz. */
export function navigate(path: string, query?: Record<string, string | string[]>, opts: { force?: boolean } = {}): void {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) {
    params.set(k, Array.isArray(v) ? v.join(",") : v);
  }
  const qs = params.toString();
  const hash = `#/${path}${qs ? `?${qs}` : ""}`;
  if (hash === currentHash) return;
  if (!opts.force && !confirmLeave()) return;
  // Onay alındı: hashchange dinleyicisi yeniden sormasın.
  commit(hash);
  window.location.hash = hash;
}

export function idsFrom(route: Route, key = "dosya"): string[] {
  return (route.query.get(key) ?? "").split(",").filter(Boolean);
}
