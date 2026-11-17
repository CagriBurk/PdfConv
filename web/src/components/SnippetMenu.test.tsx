import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { UserSnippet } from "../api";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Sunucu yok: şablon klasörü bellekte.
let stored: UserSnippet[] = [];
const fake = {
  snippets: vi.fn(async () => ({ folder: "C:\\veri\\sablonlar", items: [...stored] })),
  addSnippet: vi.fn(async (name: string, body: string) => {
    const s = { name, body, updated: 1 };
    stored.push(s);
    return s;
  }),
  updateSnippet: vi.fn(async (name: string, change: { new_name?: string; body?: string }) => {
    const s = stored.find((x) => x.name === name)!;
    Object.assign(s, change.new_name ? { name: change.new_name } : {}, change.body ? { body: change.body } : {});
    return s;
  }),
  removeSnippet: vi.fn(async (name: string) => {
    stored = stored.filter((x) => x.name !== name);
    return { ok: true };
  }),
};
vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), api: fake }));

const { default: SnippetMenu } = await import("./SnippetMenu");

// jsdom'da <dialog> yöntemleri eksik olabilir.
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
}

let root: Root;
let host: HTMLDivElement;
const onInsert = vi.fn();
let source = { text: "> [!tip] Kısa yol\n> içerik", selection: true };

const flush = () => act(async () => {
  await new Promise((r) => setTimeout(r, 0));
});
const trigger = () => host.querySelector<HTMLButtonElement>(".snippet-trigger")!;
const rowNamed = (name: string) =>
  [...host.querySelectorAll<HTMLButtonElement>(".snippet-row")].find((b) => b.textContent?.includes(name));
const byLabel = (label: string) => document.querySelector<HTMLButtonElement>(`[aria-label="${label}"]`)!;
const buttonText = (text: string) =>
  [...document.querySelectorAll<HTMLButtonElement>("dialog button")].find((b) => b.textContent === text)!;

beforeEach(async () => {
  stored = [];
  onInsert.mockReset();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  await act(async () => root.render(<SnippetMenu getSource={() => source} onInsert={onInsert} />));
  await flush();
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

describe("Şablon menüsü", () => {
  it("gruplu hazır şablonları ve boş durumu gösterir, hazır şablonu ekler", async () => {
    await act(async () => trigger().click());
    await flush();
    const heads = [...host.querySelectorAll(".snippet-head")].map((h) => h.textContent);
    expect(heads).toEqual(["Benim şablonlarım", "Belge iskeletleri", "Kutular", "Yapı taşları"]);
    expect(host.textContent).toContain("Sık kullandığın bir metni");
    expect(rowNamed("Seçimi şablon olarak kaydet")).toBeTruthy();
    await act(async () => rowNamed("Tanım Kutusu")!.click());
    expect(onInsert).toHaveBeenCalledWith(expect.objectContaining({ label: "Tanım Kutusu", user: false }));
    expect(onInsert.mock.calls[0][0].body).toContain("[!definition]");
    expect(host.querySelector(".snippet-panel")).toBeNull();
  });

  it("klavye: aşağı ok açar ve gezinir, Escape kapatıp odağı düğmeye verir", async () => {
    trigger().focus();
    await act(async () => {
      trigger().dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
      await new Promise((r) => requestAnimationFrame(() => r(null)));
    });
    expect(trigger().getAttribute("aria-expanded")).toBe("true");
    expect(document.activeElement?.textContent).toContain("Seçimi şablon olarak kaydet");
    await act(async () => {
      document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    });
    expect(document.activeElement?.textContent).toContain("Ders Notu Başlığı");
    await act(async () => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    expect(host.querySelector(".snippet-panel")).toBeNull();
    expect(document.activeElement).toBe(trigger());
  });

  it("seçimi ad vererek kaydeder, listede gösterir ve kullanıcı şablonu olarak ekler", async () => {
    await act(async () => trigger().click());
    await act(async () => rowNamed("Seçimi şablon olarak kaydet")!.click());
    const input = document.querySelector<HTMLInputElement>("dialog input")!;
    expect(input.value).toBe("Kısa yol"); // ilk satırdan öneri
    expect(document.querySelector("dialog pre")!.textContent).toBe(source.text); // düz metin
    await act(async () => buttonText("Kaydet").closest("form")!.requestSubmit());
    await flush();
    expect(fake.addSnippet).toHaveBeenCalledWith("Kısa yol", source.text);
    expect(document.querySelector("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger()); // odak düğmeye döndü

    await act(async () => trigger().click());
    await flush();
    await act(async () => rowNamed("Kısa yol")!.click());
    expect(onInsert).toHaveBeenCalledWith({ label: "Kısa yol", body: source.text, user: true });
  });

  it("yeniden adlandırır; silme onay ister", async () => {
    stored = [{ name: "Eski", body: "x", updated: 1 }];
    await act(async () => trigger().click());
    await flush();
    await act(async () => byLabel("Eski: yeniden adlandır").click());
    const input = document.querySelector<HTMLInputElement>("dialog input")!;
    await act(async () => {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      set.call(input, "Yeni ad");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => input.closest("form")!.requestSubmit());
    await flush();
    expect(fake.updateSnippet).toHaveBeenCalledWith("Eski", { new_name: "Yeni ad" });

    await act(async () => trigger().click());
    await flush();
    await act(async () => byLabel("Yeni ad: üzerine yaz").click());
    expect(document.querySelector("dialog")!.textContent).toContain("seçili metinle");
    await act(async () => buttonText("Üzerine yaz").click());
    await flush();
    expect(fake.updateSnippet).toHaveBeenLastCalledWith("Yeni ad", { body: source.text });
    expect(stored[0].body).toBe(source.text);

    await act(async () => trigger().click());
    await flush();
    await act(async () => byLabel("Yeni ad: sil").click());
    expect(fake.removeSnippet).not.toHaveBeenCalled(); // önce onay
    await act(async () => buttonText("Vazgeç").click());
    expect(stored).toHaveLength(1);
    await act(async () => trigger().click());
    await flush();
    await act(async () => byLabel("Yeni ad: sil").click());
    await act(async () => buttonText("Sil").click());
    await flush();
    expect(fake.removeSnippet).toHaveBeenCalledWith("Yeni ad");
    expect(stored).toHaveLength(0);
  });

  it("seçim yoksa notun tamamını kaydetmeyi önerir", async () => {
    source = { text: "# Not\nmetin", selection: false };
    await act(async () => trigger().click());
    expect(rowNamed("Notu şablon olarak kaydet")).toBeTruthy();
  });
});
