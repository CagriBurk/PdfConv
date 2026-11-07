import { describe, expect, it, vi } from "vitest";
import { canRotate, createBox, isBox, KIND_LABELS, LINE_HEIGHT, measureText, newId, TOOL_LABELS, toOps } from "./model";

// vi.mock en üste taşınır (import'tan önce çalışır). Konva yazı ölçümü tuval ister (jsdom'da yok): satır yüksekliği × satır sayısı kadar ölçen sahte.
vi.mock("konva", () => ({
  default: {
    Text: class {
      private o: { text: string; fontSize: number; lineHeight: number };
      constructor(o: { text: string; fontSize: number; lineHeight: number }) {
        this.o = o;
      }
      height() {
        return this.o.text.split("\n").length * this.o.fontSize * this.o.lineHeight;
      }
      destroy() {}
    },
  },
}));

describe("createBox", () => {
  it("yazı kutusu metnin yüksekliğine göre boyutlanır", () => {
    const t = createBox("text", 2, 10, 20, 200, 5);
    expect(t).toMatchObject({ kind: "text", page: 2, x: 10, y: 20, w: 200, font: "noto-sans", rotation: 0 });
    expect(t && isBox(t) && t.h).toBeCloseTo(14 * LINE_HEIGHT);
  });

  it("çizgi ve ok kutunun ortasından yatay geçer", () => {
    const l = createBox("arrow", 0, 10, 20, 100, 40);
    expect(l).toMatchObject({ kind: "arrow", points: [10, 40, 110, 40] });
    expect(l && isBox(l)).toBe(false);
  });

  it("karartma siyah, beyazla kapat beyaz", () => {
    expect(createBox("redact", 0, 0, 0, 1, 1)).toMatchObject({ color: "#000000" });
    expect(createBox("whiteout", 0, 0, 0, 1, 1)).toMatchObject({ color: "#ffffff" });
  });

  it("kutuyla çizilmeyen araçlar nesne üretmez", () => {
    expect(createBox("select", 0, 0, 0, 1, 1)).toBeNull();
    expect(createBox("image", 0, 0, 0, 1, 1)).toBeNull();
    expect(createBox("signature", 0, 0, 0, 1, 1)).toBeNull();
  });
});

describe("toOps (sunucunun işlem şeması)", () => {
  it("kutuyu x0,y0,x1,y1 dikdörtgenine çevirir, döndürmeyi taşır", () => {
    const [op] = toOps([
      { id: "a", page: 1, kind: "rect", x: 10, y: 20, w: 30, h: 40, rotation: 15, stroke: "#d00", fill: null, width: 2, opacity: 0.5 },
    ]);
    expect(op).toEqual({ type: "rect", page: 1, rect: [10, 20, 40, 60], stroke: "#d00", fill: null, width: 2, opacity: 0.5, rotation: 15 });
  });

  it("yazı: Türkçe metin ve satır yüksekliği", () => {
    const [op] = toOps([
      { id: "t", page: 0, kind: "text", x: 0, y: 0, w: 100, h: 20, rotation: 0, text: "Çağrı İşçi ğüş", font: "noto-serif", bold: true, size: 12, color: "#111111", align: "center", opacity: 1 },
    ]);
    expect(op).toMatchObject({ type: "text", text: "Çağrı İşçi ğüş", font: "noto-serif", bold: true, line_height: LINE_HEIGHT });
  });

  it("karartma rengi `fill`, beyazla kapat `color` alanında gider", () => {
    const ops = toOps([
      { id: "r", page: 0, kind: "redact", x: 0, y: 0, w: 1, h: 1, rotation: 0, color: "#000000" },
      { id: "w", page: 0, kind: "whiteout", x: 0, y: 0, w: 1, h: 1, rotation: 0, color: "#ffffff" },
    ]);
    expect(ops[0]).toEqual({ type: "redact", page: 0, rect: [0, 0, 1, 1], fill: "#000000" });
    expect(ops[1]).toEqual({ type: "whiteout", page: 0, rect: [0, 0, 1, 1], color: "#ffffff" });
  });

  it("çizgi noktalarıyla gider (dikdörtgen değil)", () => {
    const [op] = toOps([{ id: "l", page: 3, kind: "line", points: [1, 2, 3, 4], stroke: "#000", width: 1, opacity: 1 }]);
    expect(op).toEqual({ type: "line", page: 3, points: [1, 2, 3, 4], stroke: "#000", width: 1, opacity: 1 });
  });

  it("vurgu ve karartma döndürülmez (sunucu eksen hizalı yapar)", () => {
    expect(canRotate({ kind: "highlight" } as never)).toBe(false);
    expect(canRotate({ kind: "redact" } as never)).toBe(false);
    expect(canRotate({ kind: "text" } as never)).toBe(true);
  });
});

describe("yardımcılar", () => {
  it("kimlikler benzersiz", () => {
    const ids = new Set(Array.from({ length: 200 }, () => newId()));
    expect(ids.size).toBe(200);
  });

  it("çok satırlı yazı daha uzun ölçülür", () => {
    const one = measureText({ text: "a", font: "noto-sans", bold: false, size: 10, w: 100, align: "left" });
    const two = measureText({ text: "a\nb", font: "noto-sans", bold: false, size: 10, w: 100, align: "left" });
    expect(two).toBeCloseTo(2 * one);
  });

  it("her araç ve nesne türünün Türkçe adı var", () => {
    expect(Object.values(TOOL_LABELS).every(Boolean)).toBe(true);
    expect(KIND_LABELS.whiteout).toBe("Beyazla kapat");
  });
});
