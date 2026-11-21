import {
  ArrowLeftRight,
  Droplet,
  FileCode,
  FileIcon,
  FileText,
  Hash,
  ImageIcon,
  Images,
  Layers,
  LayoutGrid,
  Lock,
  Minimize2,
  PenLine,
  Printer,
  ScanText,
  Scissors,
  Table,
  type LucideIcon,
} from "lucide-react";
import type { EngineKey } from "./api";

export type ToolGroup = "Düzenle" | "Dönüştür" | "Ekle" | "Optimize ve güvenlik";

/** Grup renk tonu: CSS'te `.g1`…`.g4` (ikon kutusu, nokta). */
export type Tone = "g1" | "g2" | "g3" | "g4";

export const GROUP_TONE: Record<ToolGroup, Tone> = {
  Düzenle: "g1",
  Dönüştür: "g2",
  Ekle: "g3",
  "Optimize ve güvenlik": "g4",
};

export interface Tool {
  id: string;
  title: string;
  description: string;
  route: string;
  group: ToolGroup;
  icon: LucideIcon;
  tone: Tone;
  needs?: EngineKey[];
}

const DEFS: Omit<Tool, "tone">[] = [
  // `needs` yok: resimler ve PDF dönüştürmeleri LibreOffice olmadan çalışır; uyarı Office seçilince çıkar.
  { id: "convert", title: "Biçim Dönüştür", description: "PDF, resim ve Office dosyalarını tek ekranda dönüştür (JPG ↔ PNG ↔ PDF, DOCX ↔ ODT, XLSX ↔ CSV…)", route: "donustur", group: "Dönüştür", icon: ArrowLeftRight },
  { id: "md", title: "Markdown → PDF", description: "Formüller, Obsidian callout'ları, kod renklendirme", route: "md", group: "Dönüştür", icon: FileCode, needs: ["browser"] },
  { id: "office", title: "Office → PDF", description: "Word, Excel, PowerPoint, ODT, RTF, HTML, TXT", route: "office", group: "Dönüştür", icon: FileText, needs: ["libreoffice"] },
  { id: "img2pdf", title: "Resim → PDF", description: "JPG, PNG, HEIC fotoğraflardan PDF", route: "resimden", group: "Dönüştür", icon: ImageIcon },
  { id: "pdf2img", title: "PDF → Resim", description: "Sayfaları PNG / JPG olarak çıkar", route: "resme", group: "Dönüştür", icon: Images },
  { id: "pdf2word", title: "PDF → Word", description: "Düzenlenebilir Word belgesi (.docx)", route: "word", group: "Dönüştür", icon: FileIcon },
  { id: "pdf2excel", title: "PDF → Excel", description: "Tabloları Excel'e aktar (.xlsx)", route: "excel", group: "Dönüştür", icon: Table },
  { id: "organize", title: "Sayfa Düzenle", description: "Sürükleyerek sırala, sil, döndür, başka PDF'ten sayfa ekle", route: "duzenle", group: "Düzenle", icon: LayoutGrid },
  { id: "merge", title: "Birleştir", description: "Birden fazla PDF'i tek dosyada topla", route: "birlestir", group: "Düzenle", icon: Layers },
  { id: "split", title: "Böl", description: "Aralıklara, her N sayfaya veya yer imlerine göre ayır", route: "bol", group: "Düzenle", icon: Scissors },
  { id: "layout", title: "Sayfa Düzeni ve Yazdırma", description: "N-up çoklu sayfa, ders slayt not alanı, kenar kırpma, poster bölme", route: "yazdirma", group: "Düzenle", icon: Printer },
  { id: "edit", title: "İçerik Ekle", description: "Yazı, resim, imza, vurgu, şekil, karartma", route: "editor", group: "Ekle", icon: PenLine },
  { id: "watermark", title: "Filigran", description: "Yazı veya resim filigranı", route: "filigran", group: "Ekle", icon: Droplet },
  { id: "pagenum", title: "Sayfa Numarası", description: "\"Sayfa 3 / 10\" biçiminde numaralandır", route: "sayfa-no", group: "Ekle", icon: Hash },
  { id: "compress", title: "Sıkıştır", description: "Kayıpsız, dengeli veya güçlü küçültme", route: "sikistir", group: "Optimize ve güvenlik", icon: Minimize2 },
  { id: "ocr", title: "OCR", description: "Taranmış PDF'i aranabilir yap (Türkçe)", route: "ocr", group: "Optimize ve güvenlik", icon: ScanText, needs: ["tesseract", "ghostscript"] },
  { id: "protect", title: "Güvenlik ve Bakım", description: "AES-256 şifre, şifre kaldırma, meta veri temizliği, onarım", route: "guvenlik", group: "Optimize ve güvenlik", icon: Lock },
];

export const TOOLS: Tool[] = DEFS.map((t) => ({ ...t, tone: GROUP_TONE[t.group] }));

export const GROUPS: ToolGroup[] = ["Dönüştür", "Düzenle", "Ekle", "Optimize ve güvenlik"];

/** Rotanın ilk parçasından araç ("duzenle" → Sayfa Düzenle). */
export function toolForRoute(section: string | undefined): Tool | undefined {
  return TOOLS.find((t) => t.route === section);
}

// Kağıt boyutları. Tek kaynak: src/toolia/core/paper.py (tests/test_robustness.py denetler).
export const PAPERS = ["A4", "A5", "A3", "A2", "A1", "A0", "Letter", "Legal"];

// Biçim Dönüştür: aile başına kaynak ve hedef uzantılar. Tek kaynak: src/toolia/formats.py
// (RASTER_IMAGE_EXTS + IMAGE_CONVERT_TARGETS, OFFICE_CONVERT_FAMILIES, _SAME;
// tests/test_robustness.py tutarlılığı denetler). Hedeflerin sırası ekrandaki düğme sırasıdır.
export const CONVERT_TARGETS: Record<string, { sources: string[]; targets: string[] }> = {
  image: { sources: [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".heif"], targets: [".jpg", ".png", ".webp", ".tiff"] },
  word: { sources: [".docx", ".doc", ".docm", ".odt", ".rtf", ".wpd"], targets: [".docx", ".odt", ".rtf", ".txt"] },
  sheet: { sources: [".xlsx", ".xls", ".xlsm", ".ods", ".csv"], targets: [".xlsx", ".ods", ".csv"] },
  slides: { sources: [".pptx", ".ppt", ".pptm", ".odp"], targets: [".pptx", ".odp"] },
};
// Aynı biçimin iki yazılışı: kaynağın kendi biçimi hedeflerden çıkarılırken eş sayılır.
const CONVERT_SAME: Record<string, string> = { ".jpeg": ".jpg", ".tif": ".tiff", ".heif": ".heic" };

/** Dosya adının küçük harfli uzantısı (".JPEG" → ".jpeg"; yoksa ""). */
export function lowerExt(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot).toLowerCase() : "";
}

/** Dosyanın dönüştürme ailesi ("image", "word", "sheet", "slides"); desteklenmiyorsa null. */
export function convertFamily(name: string): string | null {
  const ext = lowerExt(name);
  return Object.keys(CONVERT_TARGETS).find((k) => CONVERT_TARGETS[k].sources.includes(ext)) ?? null;
}

/** Dosyanın biçimi (".JPEG" → ".jpg", ".tif" → ".tiff"; sunucudaki `same_format`). */
export function sameFormat(name: string): string {
  const ext = lowerExt(name);
  return CONVERT_SAME[ext] ?? ext;
}

/** Ailenin bütün hedefleri, kendi biçimi dahil (sunucudaki `family_targets`). */
export function familyTargets(name: string): string[] {
  const family = convertFamily(name);
  return family ? CONVERT_TARGETS[family].targets : [];
}

/** Tek dosyanın çevrilebileceği hedefler (kendi biçimi hariç; sunucudaki `convert_targets`). */
export function convertTargets(name: string): string[] {
  return familyTargets(name).filter((t) => t !== sameFormat(name));
}

/** Seçimin ortak hedefleri: hepsinin ailesinde olan, ama hepsinin zaten o biçimde olmadığı
 * biçimler (JPG + PNG → JPG da seçilir; zaten JPG olan dosyayı sunucu olduğu gibi alır). */
export function commonConvertTargets(names: string[]): string[] {
  if (!names.length) return [];
  const [first, ...rest] = names.map(familyTargets);
  return first.filter((t) => rest.every((r) => r.includes(t)) && !names.every((n) => sameFormat(n) === t));
}

export const ACCEPT = {
  pdf: ".pdf,application/pdf",
  images: ".jpg,.jpeg,.png,.webp,.gif,.bmp,.tif,.tiff,.heic,.heif",
  markdown: ".md,.markdown,.txt",
  // Tek kaynak: src/toolia/formats.py (tests/test_robustness.py tutarlılığı denetler).
  office: ".docx,.doc,.docm,.odt,.rtf,.wpd,.xlsx,.xls,.xlsm,.ods,.csv,.pptx,.ppt,.pptm,.odp,.html,.htm,.txt",
  // Biçim Dönüştür'ün kaynakları; yukarıdaki tablodan türer.
  convert: Object.values(CONVERT_TARGETS)
    .flatMap((f) => f.sources)
    .join(","),
};
