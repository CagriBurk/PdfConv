import {
  BookOpen,
  Code,
  Columns2,
  FlaskConical,
  Heading1,
  Lightbulb,
  ListTodo,
  MessageCircleQuestion,
  NotebookText,
  SeparatorHorizontal,
  Sigma,
  SquareFunction,
  Table,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

/** Markdown → PDF "Şablon ekle" menüsü: hazır şablonlar ve ekleme kuralları. Hazır şablonlar
 * yalnızca işleyicinin gerçekten desteklediği yapıları kullanır (callout türleri, `two-col`,
 * `page-break`, etiketli blok formül, görev listesi, tablo, kod, ön bilgideki `pdf:`). */

export const SNIPPET_GROUPS = ["Belge iskeletleri", "Kutular", "Yapı taşları"] as const;
export type SnippetGroup = (typeof SNIPPET_GROUPS)[number];

export interface SnippetPreset {
  id: string;
  label: string;
  /** Menüde adın altındaki kısa açıklama. */
  hint: string;
  group: SnippetGroup;
  icon: LucideIcon;
  /** `{{tarih}}` ekleme anındaki günün tarihine (YYYY-AA-GG) çevrilir. */
  body: string;
  /** Notta zaten ön bilgi varsa imlece eklenecek gövde. Yoksa gövdenin ön bilgisi atlanır. */
  bodyWithFrontMatter?: string;
}

export const SNIPPETS: readonly SnippetPreset[] = [
  {
    id: "ders-baslik",
    label: "Ders Notu Başlığı",
    hint: "Başlık, yazar ve ilk bölüm; notun en başına",
    group: "Belge iskeletleri",
    icon: Heading1,
    body: "---\ntitle: Ders Notu Başlığı\nauthor: Ders / Konu\npdf:\n  tema: ders\n---\n\n# Ders Notu Başlığı\n",
    bodyWithFrontMatter: "# Ders Notu Başlığı\n\n> [!abstract] Konu Özeti\n> Bu bölümdeki temel kavramlar ve formüller.",
  },
  {
    id: "rapor",
    label: "Ödev / Lab Raporu",
    hint: "Kapaklı rapor: amaç, kuram, yöntem, ölçüm tablosu, tartışma",
    group: "Belge iskeletleri",
    icon: FlaskConical,
    body: [
      "---",
      "title: Deney 1 — Deneyin Adı",
      "author: Ad Soyad (Öğrenci No)",
      "date: {{tarih}}",
      "pdf:",
      "  kapak: true",
      "---",
      "",
      "## 1. Amaç",
      "",
      "Deneyin ya da ödevin amacını bir iki cümleyle yaz.",
      "",
      "## 2. Kuram",
      "",
      "Kullanılan temel bağıntı:",
      "",
      "$$",
      "V = I \\cdot R",
      "$$ (1)",
      "",
      "## 3. Yöntem",
      "",
      "1. Düzeneği kur.",
      "2. Ölçümleri al ve tabloya yaz.",
      "",
      "## 4. Ölçümler ve Sonuçlar",
      "",
      "| Ölçüm | Gerilim (V) | Akım (mA) |",
      "| --- | --- | --- |",
      "| 1 |  |  |",
      "| 2 |  |  |",
      "",
      "## 5. Tartışma",
      "",
      "Sonuçları beklenen değerlerle karşılaştır; hata kaynaklarını yaz.",
      "",
      "## Kaynaklar",
      "",
      "1. Yazar, *Kitabın Adı*, Yayınevi, yıl.",
    ].join("\n"),
  },
  {
    id: "tanim",
    label: "Tanım Kutusu",
    hint: "Kavramın adı ve kesin tanımı",
    group: "Kutular",
    icon: BookOpen,
    body: "> [!definition] Tanım: Kavramın Adı\n> Kısa ve kesin tanım. Örneğin: $\\lim_{x \\to a} f(x) = f(a)$ ise $f$, $a$ noktasında süreklidir.",
  },
  {
    id: "teorem",
    label: "Teorem Kutusu",
    hint: "Teorem adı, hipotez ve sonuç",
    group: "Kutular",
    icon: Sigma,
    body: "> [!theorem] Teorem Adı\n> Hipotez ve sonuç ifadesi. Örneğin: $f$ sürekli ise $\\int_a^b f(x)\\,dx$ tanımlıdır.",
  },
  {
    id: "ornek",
    label: "Örnek ve Çözüm",
    hint: "Soru ifadesi, altında çözümü",
    group: "Kutular",
    icon: Lightbulb,
    body: "> [!example] Örnek 1\n> $f(x) = x^2$ için $f'(3)$ değerini bul.\n>\n> **Çözüm:** $f'(x) = 2x$ olduğundan $f'(3) = 6$ bulunur.",
  },
  {
    id: "soru-cevap",
    label: "Soru – Cevap",
    hint: "Soru kutusu, altında ayrı renkte cevap kutusu",
    group: "Kutular",
    icon: MessageCircleQuestion,
    body: "> [!question] Soru 1\n> Sorunun metni?\n\n> [!check] Cevap\n> Cevap ve kısa gerekçesi.",
  },
  {
    id: "dikkat",
    label: "Dikkat Kutusu",
    hint: "Sık yapılan hata ya da uyarı",
    group: "Kutular",
    icon: TriangleAlert,
    body: "> [!warning] Dikkat\n> Sık yapılan hata: birimleri dönüştürmeden işlem yapmak.",
  },
  {
    id: "ozet",
    label: "Özet Kutusu",
    hint: "Bölüm sonu: madde madde ana fikirler",
    group: "Kutular",
    icon: NotebookText,
    body: "> [!summary] Bölüm Özeti\n> - Birinci ana fikir\n> - İkinci ana fikir\n> - Akılda tutulacak formül: $a^2 + b^2 = c^2$",
  },
  {
    id: "iki-sutun",
    label: "2 Sütunlu Sınav Özeti",
    hint: "Formüller ve kısa notlar yan yana (Ders notu, Rapor teması)",
    group: "Yapı taşları",
    icon: Columns2,
    body: [
      '<div class="two-col">',
      "",
      "### Önemli Formüller",
      "",
      "- **Özdeşlik:** $a^2 + b^2 = c^2$",
      "- **Türev:** $\\frac{d}{dx}(x^n) = n x^{n-1}$",
      "",
      "### Kısa Notlar",
      "",
      "- Birimleri ve sınır koşullarını kontrol et.",
      "- Sınır durumlarını ayrı incele.",
      "",
      "</div>",
    ].join("\n"),
  },
  {
    id: "formul",
    label: "Numaralı Formül",
    hint: "Ortalanmış blok formül, sağında (1) etiketi",
    group: "Yapı taşları",
    icon: SquareFunction,
    body: "$$\nF = G \\frac{m_1 m_2}{r^2}\n$$ (1)",
  },
  {
    id: "tablo",
    label: "Tablo",
    hint: "Üç sütunlu tablo; hücrede formül de olur",
    group: "Yapı taşları",
    icon: Table,
    body: [
      "| Kavram | Açıklama | Formül |",
      "| --- | --- | --- |",
      "| Hız | Konumun zamana göre değişimi | $v = \\frac{dx}{dt}$ |",
      "| İvme | Hızın zamana göre değişimi | $a = \\frac{dv}{dt}$ |",
    ].join("\n"),
  },
  {
    id: "kod",
    label: "Kod Bloğu",
    hint: "Renklendirilmiş kod (dil adını değiştirebilirsin)",
    group: "Yapı taşları",
    icon: Code,
    body: "```python\ndef faktoriyel(n):\n    return 1 if n <= 1 else n * faktoriyel(n - 1)\n```",
  },
  {
    id: "gorev",
    label: "Görev Listesi",
    hint: "İşaretlenebilir yapılacaklar",
    group: "Yapı taşları",
    icon: ListTodo,
    body: "- [ ] Bölüm 3'ü oku\n- [ ] Alıştırmaları çöz\n- [x] Ders notlarını temize çek",
  },
  {
    id: "sayfa-sonu",
    label: "Sayfa Sonu",
    hint: "PDF'te sonraki içerik yeni sayfadan başlar",
    group: "Yapı taşları",
    icon: SeparatorHorizontal,
    body: '<div class="page-break"></div>',
  },
];

function isoDate(now: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Hazır şablonun eklenecek gövdesi (yer tutucular doldurulmuş). */
export function presetBody(preset: SnippetPreset, now = new Date()): string {
  return preset.body.replaceAll("{{tarih}}", isoDate(now));
}

const FRONT_MATTER_RE = /^---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/;

/** Gövdenin başındaki YAML ön bilgisi (`---` … `---`) ve geri kalanı. */
export function splitFrontMatter(body: string): { front: string | null; rest: string } {
  const m = FRONT_MATTER_RE.exec(body);
  return m ? { front: m[0], rest: body.slice(m[0].length).replace(/^\s*\n/, "") } : { front: null, rest: body };
}

export const noteHasFrontMatter = (text: string) => text.trimStart().startsWith("---");

/** İmleç konumuna eklerken önüne ve arkasına gereken kadar boş satır koyar. */
export function formatSnippetInsertion(before: string, after: string, body: string): string {
  const lead = before.length === 0 || before.endsWith("\n\n") ? "" : before.endsWith("\n") ? "\n" : "\n\n";
  const trimmedBody = body.replace(/\n+$/, "");
  const trail = after.length === 0 ? "\n" : after.startsWith("\n\n") ? "" : after.startsWith("\n") ? "\n" : "\n\n";
  return `${lead}${trimmedBody}${trail}`;
}

export interface InsertionPlan {
  start: number;
  end: number;
  insertion: string;
  /** Notta zaten ön bilgi olduğu için şablonun ön bilgisi atlandı. */
  droppedFrontMatter: boolean;
}

/** Ön bilgili şablon: notta ön bilgi yoksa notun en başına eklenir; varsa ön bilgisi atlanır (ya da
 * `bodyWithFrontMatter` kullanılır), geri kalanı imlece. Diğerleri imlece (seçim varsa yerine).
 * Eklenecek bir şey kalmadıysa null. */
export function planInsertion(
  text: string,
  selStart: number,
  selEnd: number,
  body: string,
  bodyWithFrontMatter?: string,
): InsertionPlan | null {
  let start = selStart;
  let end = selEnd;
  let content = body;
  let droppedFrontMatter = false;
  const { front, rest } = splitFrontMatter(body);
  if (front !== null) {
    if (!noteHasFrontMatter(text)) {
      start = 0;
      end = 0;
    } else if (bodyWithFrontMatter !== undefined) {
      content = bodyWithFrontMatter;
    } else {
      content = rest;
      droppedFrontMatter = true;
    }
  }
  if (!content.trim()) return null;
  const insertion = formatSnippetInsertion(text.slice(0, start), text.slice(end), content);
  return { start, end, insertion, droppedFrontMatter };
}

/** Kaydetme penceresinde önerilen ad: metnin ilk anlamlı satırı (başlık, kutu başlığı...). */
export function suggestName(text: string): string {
  const { rest } = splitFrontMatter(text);
  for (const raw of rest.split("\n")) {
    const line = raw
      .replace(/^\s*(?:>\s*)*/, "")
      .replace(/^\[![\w-]+\][+-]?\s*/, "")
      .replace(/^(?:#{1,6}\s+|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)/, "")
      .replace(/<[^>]*>|[`*_=$|]/g, "")
      .replace(/[<>:"/\\|?*]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (line.length >= 2 && !/^-+$/.test(line)) return line.length > 40 ? line.slice(0, 40).trimEnd() : line;
  }
  return "Yeni şablon";
}

/** Menüde kullanıcı şablonunun adının altında: ilk dolu satır. */
export function firstLine(body: string): string {
  return body.split("\n").find((l) => l.trim())?.trim() ?? "";
}
