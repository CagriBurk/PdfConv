import { afterEach, describe, expect, it, vi } from "vitest";
import { applyTheme, currentTheme, resetTheme, setTheme, storedTheme } from "./theme";

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
    resetTheme();
    expect(storedTheme()).toBeNull();
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    applyTheme(null);
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("pencere başlık çubuğu (theme-color) seçilen temayı izler, seçim yoksa sisteme döner", () => {
    document.head.innerHTML =
      '<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)" />' +
      '<meta name="theme-color" content="#161a22" media="(prefers-color-scheme: dark)" />';
    const colors = () =>
      [...document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')].map((m) => m.content);
    setTheme("dark"); // Windows açık temada bile çubuk koyu olmalı (0.12.1'de beyaz kalıyordu)
    expect(colors()).toEqual(["#161a22", "#161a22"]);
    setTheme("light");
    expect(colors()).toEqual(["#ffffff", "#ffffff"]);
    applyTheme(null);
    expect(colors()).toEqual(["#ffffff", "#161a22"]);
    document.head.innerHTML = "";
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
