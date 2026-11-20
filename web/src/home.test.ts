import { describe, expect, it } from "vitest";
import type { FileMeta } from "./api";
import { homeRoute, targetNames } from "./pages/Home";

const file = (id: string, name: string, kind: FileMeta["kind"]) => ({ id, name, kind });

describe("ana sayfa: bırakılan dosyalar", () => {
  it("PDF'ler düzenleyiciye ya da birleştirmeye gider", () => {
    expect(homeRoute([file("a", "a.pdf", "pdf")])).toEqual({ type: "go", path: "duzenle/a" });
    expect(homeRoute([file("a", "a.pdf", "pdf"), file("b", "b.pdf", "pdf")])).toEqual({
      type: "go",
      path: "birlestir",
      query: { dosya: ["a", "b"] },
    });
  });

  it("Markdown varsa yanındakiler eki sayılır", () => {
    expect(homeRoute([file("m", "not.md", "markdown")])).toEqual({ type: "go", path: "md", query: { dosya: "m" } });
    expect(homeRoute([file("r", "r.png", "image"), file("m", "not.md", "markdown")])).toEqual({
      type: "go",
      path: "md",
      query: { dosya: "m", ek: ["r"] },
    });
  });

  it("resimler: PDF ile başka biçim arasında seçim", () => {
    expect(homeRoute([file("a", "a.jpg", "image"), file("b", "b.PNG", "image")])).toEqual({
      type: "choose",
      pdfPath: "resimden",
      ids: ["a", "b"],
      targets: [".jpg", ".png", ".webp", ".tiff"],
      what: "2 resim yüklendi.",
    });
    expect(homeRoute([file("a", "a.heic", "image")])).toMatchObject({ type: "choose", targets: [".jpg", ".png", ".webp", ".tiff"] });
  });

  it("Office belgeleri: aynı ailedeyse seçim, değilse doğrudan PDF", () => {
    expect(homeRoute([file("w", "rapor.docx", "office")])).toEqual({
      type: "choose",
      pdfPath: "office",
      ids: ["w"],
      targets: [".odt", ".rtf", ".txt"],
      what: "Belge yüklendi.",
    });
    expect(homeRoute([file("w", "a.docx", "office"), file("o", "b.odt", "office")])).toMatchObject({
      type: "choose",
      what: "2 belge yüklendi.",
    });
    // Ortak hedef yok (metin + tablo): bugünkü gibi Office → PDF.
    expect(homeRoute([file("w", "a.docx", "office"), file("x", "b.xlsx", "office")])).toEqual({
      type: "go",
      path: "office",
      query: { dosya: ["w", "x"] },
    });
  });

  it("HTML / TXT içeren seçim ve hedefsiz resim doğrudan PDF'e gider", () => {
    expect(homeRoute([file("h", "sayfa.html", "html")])).toEqual({ type: "go", path: "office", query: { dosya: ["h"] } });
    expect(homeRoute([file("w", "a.docx", "office"), file("t", "b.txt", "text")])).toEqual({
      type: "go",
      path: "office",
      query: { dosya: ["w", "t"] },
    });
    expect(homeRoute([file("s", "çizim.svg", "image")])).toEqual({ type: "go", path: "resimden", query: { dosya: ["s"] } });
  });

  it("birlikte işlenemeyen türler uyarı verir", () => {
    expect(homeRoute([file("a", "a.pdf", "pdf"), file("r", "r.png", "image")])).toMatchObject({ type: "error" });
    expect(homeRoute([file("r", "r.png", "image"), file("w", "a.docx", "office")])).toMatchObject({ type: "error" });
    expect(homeRoute([file("z", "arsiv.zip", "other")])).toMatchObject({ type: "error" });
  });

  it("hedeflerin kısa adları", () => {
    expect(targetNames([".jpg", ".png", ".webp", ".tiff"])).toBe("JPG, PNG, WEBP, TIFF");
    expect(targetNames([".docx", ".odt"])).toBe("DOCX, ODT");
    expect(targetNames([])).toBe("");
  });
});
