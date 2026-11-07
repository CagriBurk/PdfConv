import { afterEach, describe, expect, it, vi } from "vitest";
import { draftKey, drafts, formatDraftTime } from "./drafts";

describe("drafts", () => {
  afterEach(() => window.localStorage.clear());

  it("kaydeder, okur, siler (Türkçe metin)", () => {
    const d = { text: "# Çalışma\n\nığdır ŞÖÇ", at: 1700000000000, name: "not.md" };
    expect(drafts.set("abc", d)).toBe(true);
    expect(drafts.get("abc")).toEqual(d);
    drafts.remove("abc");
    expect(drafts.get("abc")).toBeNull();
  });

  it("dosyasız not 'yeni' anahtarını kullanır", () => {
    expect(draftKey(null)).toBe("yeni");
    expect(draftKey(undefined)).toBe("yeni");
    expect(draftKey("f1")).toBe("f1");
  });

  it("bozuk kayıt yok sayılır", () => {
    window.localStorage.setItem("pa-md-taslak:x", "{bozuk");
    expect(drafts.get("x")).toBeNull();
    window.localStorage.setItem("pa-md-taslak:y", JSON.stringify({ text: 5 }));
    expect(drafts.get("y")).toBeNull();
  });

  it("depo kapalı ya da doluysa uygulama çökmez", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("dolu", "QuotaExceededError");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("kapalı", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("kapalı", "SecurityError");
    });
    expect(drafts.set("a", { text: "x", at: 0, name: "a.md" })).toBe(false);
    expect(drafts.get("a")).toBeNull();
    expect(() => drafts.remove("a")).not.toThrow();
  });

  it("tarih Türkçe biçimlenir", () => {
    expect(formatDraftTime(new Date(2026, 10, 7, 14, 5).getTime())).toMatch(/Kas/);
  });
});
