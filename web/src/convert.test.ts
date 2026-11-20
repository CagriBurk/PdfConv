import { describe, expect, it } from "vitest";
import { alreadyNote, noTargetReason } from "./pages/Convert";
import { ACCEPT, commonConvertTargets, convertTargets, familyTargets, sameFormat } from "./tools";

describe("biçim dönüştürme hedefleri", () => {
  it("kaynağın kendi biçimi çıkar; eş yazılışlar aynı sayılır", () => {
    expect(convertTargets("foto.PNG")).toEqual([".jpg", ".webp", ".tiff"]);
    expect(convertTargets("foto.jpeg")).toEqual([".png", ".webp", ".tiff"]);
    expect(convertTargets("tarama.tif")).toEqual([".jpg", ".png", ".webp"]);
    expect(convertTargets("telefon.heic")).toEqual([".jpg", ".png", ".webp", ".tiff"]);
    expect(convertTargets("rapor.doc")).toEqual([".docx", ".odt", ".rtf", ".txt"]);
    expect(convertTargets("tablo.csv")).toEqual([".xlsx", ".ods"]);
    expect(convertTargets("sunu.odp")).toEqual([".pptx"]);
    expect(convertTargets("not.txt")).toEqual([]);
    expect(convertTargets("çizim.svg")).toEqual([]);
    expect(convertTargets("uzantisiz")).toEqual([]);
  });

  it("aile hedefleri kendi biçimini de içerir; eş yazılışlar tek biçim", () => {
    expect(familyTargets("a.JPEG")).toEqual([".jpg", ".png", ".webp", ".tiff"]);
    expect(familyTargets("a.csv")).toEqual([".xlsx", ".ods", ".csv"]);
    expect(familyTargets("a.svg")).toEqual([]);
    expect(sameFormat("a.JPEG")).toBe(".jpg");
    expect(sameFormat("a.tif")).toBe(".tiff");
    expect(sameFormat("a.heif")).toBe(".heic");
    expect(sameFormat("a.Docx")).toBe(".docx");
  });

  it("ortak hedefler: aile kesişimi, hepsinin zaten olduğu biçim hariç", () => {
    expect(commonConvertTargets([])).toEqual([]);
    expect(commonConvertTargets(["a.jpg"])).toEqual([".png", ".webp", ".tiff"]);
    expect(commonConvertTargets(["a.jpg", "b.jpeg"])).toEqual([".png", ".webp", ".tiff"]);
    expect(commonConvertTargets(["a.jpg", "b.png"])).toEqual([".jpg", ".png", ".webp", ".tiff"]);
    expect(commonConvertTargets(["a.pptx", "b.odp"])).toEqual([".pptx", ".odp"]);
    expect(commonConvertTargets(["a.docx", "b.odt"])).toEqual([".docx", ".odt", ".rtf", ".txt"]);
    expect(commonConvertTargets(["a.jpg", "b.docx"])).toEqual([]);
    expect(commonConvertTargets(["a.xlsx", "b.png"])).toEqual([]);
  });

  it("ortak hedef yoksa nedeni söylenir", () => {
    expect(noTargetReason([])).toBeNull();
    expect(noTargetReason(["a.jpg", "b.png"])).toBeNull();
    expect(noTargetReason(["a.pptx", "b.odp"])).toBeNull();
    expect(noTargetReason(["a.jpg", "b.svg"])).toContain("b.svg");
    expect(noTargetReason(["a.jpg", "b.xlsx"])).toContain("resim, tablo");
  });

  it("karışık seçimde zaten hedef biçimde olanlar için not", () => {
    expect(alreadyNote(["a.jpg", "b.png", "c.jpeg"], ".jpg")).toBe("Zaten JPG olan 2 dosya olduğu gibi alınır.");
    expect(alreadyNote(["a.jpg", "b.png"], ".webp")).toBeNull();
    expect(alreadyNote(["a.png"], ".jpg")).toBeNull();
    expect(alreadyNote(["a.jpg", "b.png"], "")).toBeNull();
  });

  it("kabul listesi tablonun kaynaklarından türer", () => {
    expect(ACCEPT.convert.split(",")).toContain(".heif");
    expect(ACCEPT.convert.split(",")).toContain(".wpd");
    expect(ACCEPT.convert.split(",")).not.toContain(".txt");
  });
});
