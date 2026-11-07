import { useSyncExternalStore } from "react";

/** Genel bildirimler (toast): her ekrandan `toast.ok("Kaydedildi")`, `toast.error(...)`.
 *
 * React bağlamı gerekmez (yönlendirici gibi modül düzeyinde bir depo); ekranın köşesinde
 * `<Toaster />` gösterir. Hatalar kendiliğinden kaybolmaz (okunmadan gitmesin), diğerleri birkaç
 * saniyede kapanır. Aynı ileti üst üste gelirse yenisi eklenmez, sayacı artar. */
export type ToastKind = "ok" | "info" | "error";

export interface Toast {
  id: number;
  kind: ToastKind;
  text: string;
  count: number;
}

const AUTO_CLOSE_MS = 5000;
const MAX_TOASTS = 4;
let items: Toast[] = [];
let nextId = 1;
const listeners = new Set<() => void>();
const timers = new Map<number, ReturnType<typeof setTimeout>>();

function emit(): void {
  listeners.forEach((l) => l());
}

export function dismiss(id: number): void {
  const t = timers.get(id);
  if (t) clearTimeout(t);
  timers.delete(id);
  const next = items.filter((i) => i.id !== id);
  if (next.length !== items.length) {
    items = next;
    emit();
  }
}

export function show(text: string, kind: ToastKind = "info"): number {
  const same = items.find((i) => i.text === text && i.kind === kind);
  if (same) {
    items = items.map((i) => (i === same ? { ...i, count: i.count + 1 } : i));
    emit();
    return same.id;
  }
  const id = nextId++;
  items = [...items, { id, kind, text, count: 1 }].slice(-MAX_TOASTS);
  if (kind !== "error") timers.set(id, setTimeout(() => dismiss(id), AUTO_CLOSE_MS));
  emit();
  return id;
}

export function clearAll(): void {
  timers.forEach((t) => clearTimeout(t));
  timers.clear();
  items = [];
  emit();
}

export const toast = {
  ok: (text: string) => show(text, "ok"),
  info: (text: string) => show(text, "info"),
  error: (text: string) => show(text, "error"),
};

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getToasts(): Toast[] {
  return items;
}

export function useToasts(): Toast[] {
  return useSyncExternalStore(subscribe, getToasts);
}
