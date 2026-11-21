import { useSyncExternalStore } from "react";

const KEY = "pa-favoriler";
const listeners = new Set<() => void>();
let cache: string[] | null = null;

function read(): string[] {
  if (cache) return cache;
  try {
    const raw = window.localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    cache = Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    cache = [];
  }
  return cache;
}

function write(next: string[]): void {
  cache = next;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Depolama kapalıysa yalnız bu oturumda tutulur.
  }
  listeners.forEach((l) => l());
}

export function toggleFavorite(toolId: string): void {
  const cur = read();
  write(cur.includes(toolId) ? cur.filter((id) => id !== toolId) : [...cur, toolId]);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useFavorites(): string[] {
  return useSyncExternalStore(subscribe, read);
}
