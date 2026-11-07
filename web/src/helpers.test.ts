import { afterEach, describe, expect, it, vi } from "vitest";
import { splitName } from "./filename";
import { JOB_TYPE_LABEL, jobLabel } from "./labels";
import { bodyInner, createSequencer, scrollRatio, shellKey } from "./mdpreview";
import { columnsOf, focusAfterDelete, moveSelected, nextIndex, rangeKeys } from "./organizer";
import { clearAll, dismiss, getToasts, toast } from "./toast";

const k = (...keys: string[]) => keys.map((key) => ({ key }));
const keysOf = (items: { key: string }[] | null) => items?.map((i) => i.key).join("") ?? null;

describe("sayfa düzenleyici klavyesi", () => {
  it("oklar ızgarada gezer, uçlarda durur", () => {
    expect(nextIndex("ArrowRight", 0, 10, 4)).toBe(1);
    expect(nextIndex("ArrowLeft", 0, 10, 4)).toBe(0);
    expect(nextIndex("ArrowDown", 1, 10, 4)).toBe(5);
    expect(nextIndex("ArrowDown", 8, 10, 4)).toBe(9);
    expect(nextIndex("ArrowUp", 2, 10, 4)).toBe(0);
    expect(nextIndex("Home", 7, 10, 4)).toBe(0);
    expect(nextIndex("End", 0, 10, 4)).toBe(9);
    expect(nextIndex("a", 0, 10, 4)).toBeNull();
    expect(nextIndex("ArrowRight", 0, 0, 4)).toBeNull();
  });

  it("seçili sayfalar birlikte taşınır, göreli sıra korunur", () => {
    const items = k("a", "b", "c", "d", "e");
    expect(keysOf(moveSelected(items, new Set(["c"]), -1))).toBe("acbde");
    expect(keysOf(moveSelected(items, new Set(["b", "c"]), 1))).toBe("adbce");
    expect(keysOf(moveSelected(items, new Set(["b", "d"]), -1))).toBe("badce");
    expect(moveSelected(items, new Set(["a", "c"]), -1)).toBeNull(); // biri zaten başta
    expect(moveSelected(items, new Set(["e"]), 1)).toBeNull();
    expect(moveSelected(items, new Set(), 1)).toBeNull();
  });

  it("Shift ile aralık seçimi iki yönde de", () => {
    const items = k("a", "b", "c", "d");
    expect(rangeKeys(items, "b", "d")).toEqual(["b", "c", "d"]);
    expect(rangeKeys(items, "d", "b")).toEqual(["b", "c", "d"]);
    expect(rangeKeys(items, null, "c")).toEqual(["c"]);
    expect(rangeKeys(items, "yok", "c")).toEqual(["c"]);
  });

  it("silmeden sonra odak silinenin yerine gelen sayfada", () => {
    const before = k("a", "b", "c", "d");
    expect(focusAfterDelete(before, k("a", "d"), new Set(["b", "c"]))).toBe("d");
    expect(focusAfterDelete(before, k("a", "b", "c"), new Set(["d"]))).toBe("c");
    expect(focusAfterDelete(before, k("b", "c", "d"), new Set(["a"]))).toBe("b");
    expect(focusAfterDelete(before, [], new Set(["a", "b", "c", "d"]))).toBeNull();
  });

  it("sütun sayısı ilk satırdan", () => {
    expect(columnsOf([10, 10, 10, 200, 200])).toBe(3);
    expect(columnsOf([10, 11, 300])).toBe(2);
    expect(columnsOf([])).toBe(1);
  });
});

describe("Markdown önizlemesi", () => {
  const doc = (nonce: string, body: string, cls = "") =>
    `<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="script-src 'nonce-${nonce}'">` +
    `<style>x{}</style><script nonce="${nonce}" src="k.js"></script></head><body class="${cls}">\n${body}\n` +
    `<script nonce="${nonce}">başlat()</script>\n</body></html>`;

  it("yalnızca nonce'u farklı belgelerin kabuğu aynı", () => {
    expect(shellKey(doc("a1", "<p>x</p>"))).toBe(shellKey(doc("b2", "<p>y</p>")));
    expect(shellKey(doc("a1", "x"))).not.toBe(shellKey(doc("a1", "x", "yatay")));
    expect(shellKey(doc("a1", "x"))).not.toBe(shellKey(doc("a1", "x").replace("x{}", "y{}")));
  });

  it("gövde içeriği başlatıcı betik olmadan alınır", () => {
    const inner = bodyInner(doc("n", '<main class="content"><p>Çağrı</p></main>'));
    expect(inner).toContain("<p>Çağrı</p>");
    expect(inner).not.toContain("başlat()");
  });

  it("kaydırma oranı sınırlı", () => {
    expect(scrollRatio(500, 2000, 1000)).toBe(0.5);
    expect(scrollRatio(0, 500, 1000)).toBe(0);
    expect(scrollRatio(5000, 2000, 1000)).toBe(1);
  });

  it("geç gelen eski yanıt kabul edilmez", () => {
    const seq = createSequencer();
    const first = seq.next();
    const second = seq.next();
    expect(seq.isLatest(first)).toBe(false);
    expect(seq.isLatest(second)).toBe(true);
  });
});

describe("iş adları ve dosya adları", () => {
  it("her iş türünün Türkçe adı var; motor kurulumu motorun adıyla", () => {
    expect(jobLabel("office_to_pdf")).toBe("Office → PDF");
    expect(jobLabel("install_engine", { engine: "libreoffice" })).toBe("LibreOffice kurulumu");
    expect(jobLabel("gelecekte_eklenen")).toBe("gelecekte_eklenen");
    expect(Object.keys(JOB_TYPE_LABEL)).toHaveLength(15);
  });

  it("uzantı yalnızca kısa harf/rakam son parça", () => {
    expect(splitName("Rapor.pdf")).toEqual({ stem: "Rapor", ext: ".pdf" });
    expect(splitName("Sürüm 1.2 son")).toEqual({ stem: "Sürüm 1.2 son", ext: "" });
    expect(splitName("ödev.v2.docx")).toEqual({ stem: "ödev.v2", ext: ".docx" });
    expect(splitName(".gizli")).toEqual({ stem: ".gizli", ext: "" });
  });
});

describe("bildirimler", () => {
  afterEach(() => {
    clearAll();
    vi.useRealTimers();
  });

  it("bilgi kendiliğinden kapanır, hata kalır", () => {
    vi.useFakeTimers();
    toast.ok("Kaydedildi");
    toast.error("Olmadı");
    expect(getToasts()).toHaveLength(2);
    vi.advanceTimersByTime(6000);
    expect(getToasts().map((t) => t.text)).toEqual(["Olmadı"]);
    dismiss(getToasts()[0].id);
    expect(getToasts()).toHaveLength(0);
  });

  it("aynı ileti yığılmaz, sayılır; en fazla dört", () => {
    toast.error("Aynı");
    toast.error("Aynı");
    expect(getToasts()).toHaveLength(1);
    expect(getToasts()[0].count).toBe(2);
    for (const t of ["1", "2", "3", "4", "5"]) toast.error(t);
    expect(getToasts().map((t) => t.text)).toEqual(["2", "3", "4", "5"]);
  });
});
