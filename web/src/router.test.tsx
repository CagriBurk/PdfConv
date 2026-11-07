import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { confirmLeave, idsFrom, LEAVE_MESSAGE, navigate, useLeaveGuard, useRoute, type Route } from "./router";

// React'e "test ortamı" de: act() uyarısı çıkmasın.
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let seen: Route | null = null;
function Probe({ dirty }: { dirty: boolean }) {
  seen = useRoute();
  useLeaveGuard(dirty);
  return null;
}

function mount(dirty: boolean) {
  const el = document.createElement("div");
  const root = createRoot(el);
  act(() => root.render(<Probe dirty={dirty} />));
  return { rerender: (d: boolean) => act(() => root.render(<Probe dirty={d} />)), unmount: () => act(() => root.unmount()) };
}

const fireHashChange = (hash: string) =>
  act(() => {
    window.location.hash = hash;
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });

describe("router", () => {
  beforeEach(() => {
    navigate("araclar", undefined, { force: true });
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("karma adresi yol ve sorguya ayırır (Türkçe kimlik ve virgüllü liste)", () => {
    const view = mount(false);
    act(() => navigate("duzenle/ab%C3%A7", { dosya: ["a1", "b2"], islem: "onar" }));
    expect(window.location.hash).toBe("#/duzenle/ab%C3%A7?dosya=a1%2Cb2&islem=onar");
    expect(seen?.path).toEqual(["duzenle", "abç"]);
    expect(idsFrom(seen!)).toEqual(["a1", "b2"]);
    expect(idsFrom(seen!, "yok")).toEqual([]);
    view.unmount();
  });

  it("kaydedilmemiş iş varken gezinme sorar; vazgeçilirse ekran yerinde kalır", () => {
    const ask = vi.spyOn(window, "confirm").mockReturnValue(false);
    const view = mount(true);
    act(() => navigate("isler"));
    expect(ask).toHaveBeenCalledWith(LEAVE_MESSAGE);
    expect(seen?.path).toEqual(["araclar"]);
    expect(window.location.hash).toBe("#/araclar");
    ask.mockReturnValue(true);
    act(() => navigate("isler"));
    expect(seen?.path).toEqual(["isler"]);
    view.unmount();
  });

  it("geri/ileri düğmesi (hashchange) da sorar ve vazgeçilince adresi geri yazar", () => {
    const ask = vi.spyOn(window, "confirm").mockReturnValue(false);
    const push = vi.spyOn(history, "pushState");
    const view = mount(true);
    fireHashChange("#/ayarlar");
    expect(ask).toHaveBeenCalledTimes(1);
    expect(push).toHaveBeenCalledWith(null, "", "#/araclar");
    expect(seen?.path).toEqual(["araclar"]);
    view.unmount();
  });

  it("koruma kalkınca (kaydedildi) sormaz; `force` hiç sormaz", () => {
    const ask = vi.spyOn(window, "confirm").mockReturnValue(false);
    const view = mount(true);
    act(() => navigate("md", undefined, { force: true }));
    expect(seen?.path).toEqual(["md"]);
    view.rerender(false);
    expect(confirmLeave()).toBe(true);
    act(() => navigate("isler"));
    expect(seen?.path).toEqual(["isler"]);
    expect(ask).not.toHaveBeenCalled();
    view.unmount();
  });

  it("sekme kapanırken tarayıcı uyarısı yalnızca kaydedilmemiş iş varken", () => {
    const view = mount(true);
    const e = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(e);
    expect(e.defaultPrevented).toBe(true);
    view.rerender(false);
    const e2 = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(e2);
    expect(e2.defaultPrevented).toBe(false);
    view.unmount();
  });
});
