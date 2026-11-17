import { afterEach, describe, expect, it, vi } from "vitest";
import { applyTheme, currentTheme, setTheme, storedTheme } from "./theme";

describe("tema", () => {
  afterEach(() => {
    window.localStorage.clear();
    applyTheme(null);
  });

  it("seçim yoksa özniteliği kaldırır (sistem tercihi), seçimi saklar ve uygular", () => {
    expect(storedTheme()).toBeNull();
    setTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(storedTheme()).toBe("dark");
    expect(currentTheme()).toBe("dark");
    applyTheme(null);
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("bozuk kayıt ve erişilemeyen depolama sistem tercihine düşer", () => {
    window.localStorage.setItem("pa-tema", "mor");
    expect(storedTheme()).toBeNull();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("erişim yok");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("erişim yok");
    });
    expect(storedTheme()).toBeNull();
    expect(() => setTheme("light")).not.toThrow();
    expect(currentTheme()).toBe("light");
  });
});
