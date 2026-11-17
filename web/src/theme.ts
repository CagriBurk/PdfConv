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

export function applyTheme(theme: Theme | null): void {
  const root = document.documentElement;
  if (theme) root.dataset.theme = theme;
  else delete root.dataset.theme;
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
