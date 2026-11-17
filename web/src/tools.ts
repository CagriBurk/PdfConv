import {
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
  { id: "organize", title: "Sayfa Düzenle", description: "Sürükleyerek sırala, sil, döndür, başka PDF'ten sayfa ekle", route: "duzenle", group: "Düzenle", icon: LayoutGrid },
  { id: "merge", title: "Birleştir", description: "Birden fazla PDF'i tek dosyada topla", route: "birlestir", group: "Düzenle", icon: Layers },
  { id: "split", title: "Böl", description: "Aralıklara, her N sayfaya veya yer imlerine göre ayır", route: "bol", group: "Düzenle", icon: Scissors },
  { id: "layout", title: "Sayfa Düzeni ve Yazdırma", description: "N-up çoklu sayfa, ders slayt not alanı, kenar kırpma, poster bölme", route: "yazdirma", group: "Düzenle", icon: Printer },
  { id: "md", title: "Markdown → PDF", description: "Formüller, Obsidian callout'ları, kod renklendirme", route: "md", group: "Dönüştür", icon: FileCode, needs: ["browser"] },
  { id: "office", title: "Office → PDF", description: "Word, Excel, PowerPoint, ODT, RTF, HTML, TXT", route: "office", group: "Dönüştür", icon: FileText, needs: ["libreoffice"] },
  { id: "img2pdf", title: "Resim → PDF", description: "JPG, PNG, HEIC fotoğraflardan PDF", route: "resimden", group: "Dönüştür", icon: ImageIcon },
  { id: "pdf2img", title: "PDF → Resim", description: "Sayfaları PNG / JPG olarak çıkar", route: "resme", group: "Dönüştür", icon: Images },
  { id: "pdf2word", title: "PDF → Word", description: "Düzenlenebilir Word belgesi (.docx)", route: "word", group: "Dönüştür", icon: FileIcon },
  { id: "pdf2excel", title: "PDF → Excel", description: "Tabloları Excel'e aktar (.xlsx)", route: "excel", group: "Dönüştür", icon: Table },
  { id: "edit", title: "İçerik Ekle", description: "Yazı, resim, imza, vurgu, şekil, karartma", route: "editor", group: "Ekle", icon: PenLine },
  { id: "watermark", title: "Filigran", description: "Yazı veya resim filigranı", route: "filigran", group: "Ekle", icon: Droplet },
  { id: "pagenum", title: "Sayfa Numarası", description: "\"Sayfa 3 / 10\" biçiminde numaralandır", route: "sayfa-no", group: "Ekle", icon: Hash },
  { id: "compress", title: "Sıkıştır", description: "Kayıpsız, dengeli veya güçlü küçültme", route: "sikistir", group: "Optimize ve güvenlik", icon: Minimize2 },
  { id: "ocr", title: "OCR", description: "Taranmış PDF'i aranabilir yap (Türkçe)", route: "ocr", group: "Optimize ve güvenlik", icon: ScanText, needs: ["tesseract", "ghostscript"] },
  { id: "protect", title: "Güvenlik ve Bakım", description: "AES-256 şifre, şifre kaldırma, meta veri temizliği, onarım", route: "guvenlik", group: "Optimize ve güvenlik", icon: Lock },
];

export const TOOLS: Tool[] = DEFS.map((t) => ({ ...t, tone: GROUP_TONE[t.group] }));

export const GROUPS: ToolGroup[] = ["Düzenle", "Dönüştür", "Ekle", "Optimize ve güvenlik"];

/** Rotanın ilk parçasından araç ("duzenle" → Sayfa Düzenle). */
export function toolForRoute(section: string | undefined): Tool | undefined {
  return TOOLS.find((t) => t.route === section);
}

// Kağıt boyutları. Tek kaynak: src/pdfatolye/core/paper.py (tests/test_robustness.py denetler).
export const PAPERS = ["A4", "A5", "A3", "A2", "A1", "A0", "Letter", "Legal"];

export const ACCEPT = {
  pdf: ".pdf,application/pdf",
  images: ".jpg,.jpeg,.png,.webp,.gif,.bmp,.tif,.tiff,.heic,.heif",
  markdown: ".md,.markdown,.txt",
  // Tek kaynak: src/pdfatolye/formats.py (tests/test_robustness.py tutarlılığı denetler).
  office: ".docx,.doc,.docm,.odt,.rtf,.wpd,.xlsx,.xls,.xlsm,.ods,.csv,.pptx,.ppt,.pptm,.odp,.html,.htm,.txt",
};
