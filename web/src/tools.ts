import type { EngineKey } from "./api";

export interface Tool {
  id: string;
  title: string;
  description: string;
  route: string;
  group: "Düzenle" | "Dönüştür" | "Ekle" | "Optimize ve güvenlik";
  needs?: EngineKey[];
}

export const TOOLS: Tool[] = [
  { id: "organize", title: "Sayfa Düzenle", description: "Sürükleyerek sırala, sil, döndür, başka PDF'ten sayfa ekle", route: "duzenle", group: "Düzenle" },
  { id: "merge", title: "Birleştir", description: "Birden fazla PDF'i tek dosyada topla", route: "birlestir", group: "Düzenle" },
  { id: "split", title: "Böl", description: "Aralıklara, her N sayfaya veya yer imlerine göre ayır", route: "bol", group: "Düzenle" },
  { id: "md", title: "Markdown → PDF", description: "Formüller, Obsidian callout'ları, kod renklendirme", route: "md", group: "Dönüştür", needs: ["browser"] },
  { id: "office", title: "Office → PDF", description: "Word, Excel, PowerPoint, ODT, RTF, HTML, TXT", route: "office", group: "Dönüştür", needs: ["libreoffice"] },
  { id: "img2pdf", title: "Resim → PDF", description: "JPG, PNG, HEIC fotoğraflardan PDF", route: "resimden", group: "Dönüştür" },
  { id: "pdf2img", title: "PDF → Resim", description: "Sayfaları PNG / JPG olarak çıkar", route: "resme", group: "Dönüştür" },
  { id: "edit", title: "İçerik Ekle", description: "Yazı, resim, imza, vurgu, şekil, karartma", route: "editor", group: "Ekle" },
  { id: "watermark", title: "Filigran", description: "Yazı veya resim filigranı", route: "filigran", group: "Ekle" },
  { id: "pagenum", title: "Sayfa Numarası", description: "\"Sayfa 3 / 10\" biçiminde numaralandır", route: "sayfa-no", group: "Ekle" },
  { id: "compress", title: "Sıkıştır", description: "Kayıpsız, dengeli veya güçlü küçültme", route: "sikistir", group: "Optimize ve güvenlik" },
  { id: "ocr", title: "OCR", description: "Taranmış PDF'i aranabilir yap (Türkçe)", route: "ocr", group: "Optimize ve güvenlik", needs: ["tesseract", "ghostscript"] },
  { id: "protect", title: "Güvenlik ve Bakım", description: "AES-256 şifre, şifre kaldırma, meta veri temizliği, onarım", route: "guvenlik", group: "Optimize ve güvenlik" },
];

export const GROUPS: Tool["group"][] = ["Düzenle", "Dönüştür", "Ekle", "Optimize ve güvenlik"];

export const ACCEPT = {
  pdf: ".pdf,application/pdf",
  images: ".jpg,.jpeg,.png,.webp,.gif,.bmp,.tif,.tiff,.heic,.heif",
  markdown: ".md,.markdown,.txt",
  // Tek kaynak: src/pdfatolye/formats.py (tests/test_robustness.py tutarlılığı denetler).
  office: ".docx,.doc,.docm,.odt,.rtf,.wpd,.xlsx,.xls,.xlsm,.ods,.csv,.pptx,.ppt,.pptm,.odp,.html,.htm,.txt",
};
