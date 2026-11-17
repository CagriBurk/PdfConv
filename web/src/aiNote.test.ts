import { describe, expect, it } from "vitest";
import { fixAiNote, FORMULA_FIX_HINT, formulaFixMessage } from "./aiNote";

describe("Formülleri onar", () => {
  it("\\( \\) ve \\[ \\] formüllerini $ / $$ biçimine çevirir", () => {
    const res = fixAiNote("Enerji \\(E = mc^2\\) ve:\n\\[\n\\int_0^1 x\\,dx\n\\]\nson");
    expect(res.converted).toBe(2);
    expect(res.text).toBe("Enerji $E = mc^2$ ve:\n\n$$\n\\int_0^1 x\\,dx\n$$\n\nson");
  });

  it("kod bloklarına ve satır içi koda dokunmaz", () => {
    const src = "```\n\\(a\\)\n```\n\n`\\[b\\]` ve \\(c\\)";
    const res = fixAiNote(src);
    expect(res.converted).toBe(1);
    expect(res.text).toBe("```\n\\(a\\)\n```\n\n`\\[b\\]` ve $c$");
  });

  it("$ ile yazılmış not değişmez ve bildirim nedenini söyler", () => {
    const res = fixAiNote("Zaten doğru: $x^2$\n\n$$\ny = 1\n$$\n");
    expect(res.changed).toBe(false);
    const msg = formulaFixMessage(res);
    expect(msg.kind).toBe("info");
    expect(msg.text).toContain("\\( … \\) ya da \\[ … \\]");
    expect(msg.text).toContain("zaten doğru");
  });

  it("başarı bildirimleri ne yapıldığını söyler", () => {
    expect(formulaFixMessage({ converted: 3, changed: true }).text).toContain("3 formül");
    expect(formulaFixMessage({ converted: 0, changed: true }).text).toContain("boş satırlar");
    expect(FORMULA_FIX_HINT).toContain("\\( … \\)");
  });
});
