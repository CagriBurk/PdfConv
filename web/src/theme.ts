import { useSyncExternalStore } from "react";

/** Açık / koyu tema. Seçim yoksa sistem tercihi geçerli (CSS `prefers-color-scheme`); seçim
 * `<html data-theme>` ile zorlanır ve bu tarayıcıda saklanır. İlk boyamadan önce `public/tema.js`
 * uygular (içerik güvenlik politikası satır içi betiğe izin vermiyor; anahtar orada da yazılı). */
export type Theme = "light" | "dark";

const KEY = "pa-tema";
const QUERY = "(prefers-color-scheme: dark)";
const listeners = new Set<() => void>();

export function storedTheme(): Theme | null {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null; // depolama kapalı (gizli pencere, ilke): sistem tercihi
  }
}

// Üst çubuğun zemini (`--surface`); index.html'deki theme-color etiketleriyle aynı.
const BAR_COLOR: Record<Theme, string> = { light: "#ffffff", dark: "#161a22" };

/** Pencerenin başlık çubuğu (Edge uygulama penceresi `theme-color`'ı kullanır) uygulamada seçilen
 * temayı izlesin: yoksa Windows açık temadayken koyu sayfanın üstünde beyaz bir şerit kalıyordu.
 * Seçim yoksa iki etiket sistem temasına göre (media sorgusu) kendi rengini alır. */
export function syncThemeColor(theme: Theme | null): void {
  document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]').forEach((meta) => {
    const scheme: Theme = (meta.getAttribute("media") ?? "").includes("dark") ? "dark" : "light";
    meta.content = BAR_COLOR[theme ?? scheme];
  });
}

export function applyTheme(theme: Theme | null): void {
  const root = document.documentElement;
  if (theme) root.dataset.theme = theme;
  else delete root.dataset.theme;
  syncThemeColor(theme);
}

export function currentTheme(): Theme {
  const forced = document.documentElement.dataset.theme;
  if (forced === "light" || forced === "dark") return forced;
  return window.matchMedia?.(QUERY).matches ? "dark" : "light";
}

export function setTheme(theme: Theme): void {
  applyTheme(theme);
  try {
    window.localStorage.setItem(KEY, theme);
  } catch {
    // Saklanamadı: seçim bu oturumda geçerli kalır.
  }
  listeners.forEach((l) => l());
}

/** Elle seçimi kaldırıp sistem tercihine döner. */
export function resetTheme(): void {
  applyTheme(null);
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // Saklanamadı: bu oturumda sistem tercihi geçerli.
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Seçim yokken sistem teması değişirse düğmenin simgesi de değişsin.
  const media = window.matchMedia?.(QUERY);
  media?.addEventListener("change", listener);
  return () => {
    listeners.delete(listener);
    media?.removeEventListener("change", listener);
  };
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, currentTheme);
}

export function useStoredTheme(): Theme | null {
  return useSyncExternalStore(subscribe, storedTheme);
}
