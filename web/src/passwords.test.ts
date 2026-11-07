import { describe, expect, it } from "vitest";
import { passwords } from "./passwords";

describe("passwords", () => {
  it("yalnızca bilinen dosyaların şifrelerini işe ekler", () => {
    passwords.set("a", "gizli-ğ");
    passwords.set("b", "");
    expect(passwords.get("a")).toBe("gizli-ğ");
    expect(passwords.forFiles(["a", "b", "c"])).toEqual({ a: "gizli-ğ" });
    expect(passwords.forFiles([])).toEqual({});
  });

  it("tarayıcı deposuna hiçbir şey yazılmaz", () => {
    passwords.set("x", "çok-gizli");
    const all = JSON.stringify({ ...window.localStorage }) + JSON.stringify({ ...window.sessionStorage });
    expect(all).not.toContain("çok-gizli");
  });
});
