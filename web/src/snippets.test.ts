import { describe, expect, it } from "vitest";
import { firstLine, planInsertion, presetBody, SNIPPET_GROUPS, SNIPPETS, splitFrontMatter, suggestName } from "./snippets";

const preset = (id: string) => SNIPPETS.find((s) => s.id === id)!;
const apply = (text: string, plan: NonNullable<ReturnType<typeof planInsertion>>) =>
  `${text.slice(0, plan.start)}${plan.insertion}${text.slice(plan.end)}`;

describe("hazır şablonlar", () => {
  it("eski dört şablon korunur, liste gruplara ayrılır", () => {
    for (const id of ["ders-baslik", "iki-sutun", "teorem", "sayfa-sonu"]) expect(preset(id)).toBeTruthy();
    expect(SNIPPETS.length).toBeGreaterThanOrEqual(10);
    expect(new Set(SNIPPETS.map((s) => s.id)).size).toBe(SNIPPETS.length);
    for (const s of SNIPPETS) expect(SNIPPET_GROUPS).toContain(s.group);
  });

  it("rapor şablonuna bugünün tarihi yazılır", () => {
    expect(presetBody(preset("rapor"), new Date(2026, 0, 5))).toContain("date: 2026-01-05");
  });
});

describe("şablon ekleme", () => {
  it("imlece boş satırları ayarlayarak ekler", () => {
    const text = "# Başlık\nmetin";
    const plan = planInsertion(text, 8, 8, "> [!tip] İpucu")!;
    expect(apply(text, plan)).toBe("# Başlık\n\n> [!tip] İpucu\n\nmetin");
  });

  it("seçim varsa yerine koyar", () => {
    const text = "a\n\nSEÇ\n\nb";
    const plan = planInsertion(text, 3, 6, "YENİ")!;
    expect(apply(text, plan)).toBe("a\n\nYENİ\n\nb");
  });

  it("ders başlığı: ön bilgisiz notta en başa, ön bilgili notta özel gövde imlece", () => {
    const p = preset("ders-baslik");
    const plain = "metin";
    const top = planInsertion(plain, 5, 5, p.body, p.bodyWithFrontMatter)!;
    expect(apply(plain, top).startsWith("---\ntitle: Ders Notu Başlığı")).toBe(true);
    const fm = "---\ntitle: x\n---\n\nmetin";
    const mid = planInsertion(fm, fm.length, fm.length, p.body, p.bodyWithFrontMatter)!;
    expect(apply(fm, mid)).toBe(`${fm}\n\n${p.bodyWithFrontMatter}\n`);
    expect(mid.droppedFrontMatter).toBe(false);
  });

  it("ön bilgili kullanıcı şablonu: notta ön bilgi varsa ön bilgisi atlanır", () => {
    const fm = "---\ntitle: x\n---\n\nmetin";
    const plan = planInsertion(fm, fm.length, fm.length, "---\ntitle: Şablon\n---\n\n## Bölüm\n")!;
    expect(plan.droppedFrontMatter).toBe(true);
    expect(apply(fm, plan)).toBe(`${fm}\n\n## Bölüm\n`);
    expect(planInsertion(fm, 0, 0, "---\ntitle: yalnız ön bilgi\n---\n")).toBeNull();
  });

  it("ön bilgiyi ayırır", () => {
    expect(splitFrontMatter("---\na: 1\n---\n\nmetin")).toEqual({ front: "---\na: 1\n---\n", rest: "metin" });
    expect(splitFrontMatter("metin\n---\n").front).toBeNull();
  });
});

describe("kaydetme yardımcıları", () => {
  it("ilk anlamlı satırdan ad önerir", () => {
    expect(suggestName("> [!definition] Tanım: Süreklilik\n> ...")).toBe("Tanım Süreklilik");
    expect(suggestName("---\ntitle: x\n---\n\n## Lab Raporu\n")).toBe("Lab Raporu");
    expect(suggestName("- [ ] Oku")).toBe("Oku");
    expect(suggestName("   \n")).toBe("Yeni şablon");
    expect(suggestName("x".repeat(80)).length).toBe(40);
  });

  it("menüde ilk dolu satır görünür", () => {
    expect(firstLine("\n\n  ## Başlık \nikinci")).toBe("## Başlık");
  });
});
