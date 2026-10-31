import type { EngineKey } from "./api";

export interface Tool {
  id: string;
  title: string;
  description: string;
  phase: number;
  group: "Düzenle" | "Dönüştür" | "Ekle" | "Optimize ve güvenlik";
  needs?: EngineKey[];
}

// Arayüzde hangi fazda kullanılabilir olacağı (PLAN.md §10).
export const TOOLS: Tool[] = [
  { id: "organize", title: "Sayfa Düzenle", description: "Sürükleyerek sırala, sil, döndür, başka PDF'ten sayfa ekle", phase: 3, group: "Düzenle" },
  { id: "merge", title: "Birleştir", description: "Birden fazla PDF'i tek dosyada topla", phase: 3, group: "Düzenle" },
  { id: "split", title: "Böl", description: "Aralıklara, her N sayfaya veya yer imlerine göre ayır", phase: 3, group: "Düzenle" },
  { id: "md", title: "Markdown → PDF", description: "Formüller, Obsidian callout'ları, kod renklendirme", phase: 3, group: "Dönüştür", needs: ["browser"] },
  { id: "office", title: "Office → PDF", description: "Word, Excel, PowerPoint, ODT, RTF", phase: 4, group: "Dönüştür", needs: ["libreoffice"] },
  { id: "img2pdf", title: "Resim → PDF", description: "JPG, PNG, HEIC fotoğraflardan PDF", phase: 3, group: "Dönüştür" },
  { id: "pdf2img", title: "PDF → Resim", description: "Sayfaları PNG / JPG olarak çıkar", phase: 3, group: "Dönüştür" },
  { id: "edit", title: "İçerik Ekle", description: "Yazı, resim, imza, vurgu, şekil, karartma", phase: 5, group: "Ekle" },
  { id: "watermark", title: "Filigran", description: "Yazı veya resim filigranı", phase: 5, group: "Ekle" },
  { id: "pagenum", title: "Sayfa Numarası", description: "\"Sayfa 3 / 10\" biçiminde numaralandır", phase: 5, group: "Ekle" },
  { id: "compress", title: "Sıkıştır", description: "Kayıpsız, dengeli veya güçlü küçültme", phase: 6, group: "Optimize ve güvenlik" },
  { id: "ocr", title: "OCR", description: "Taranmış PDF'i aranabilir yap (Türkçe)", phase: 6, group: "Optimize ve güvenlik", needs: ["tesseract", "ghostscript"] },
  { id: "protect", title: "Şifrele / Şifre Kaldır", description: "AES-256 şifre, izinler, meta veri temizliği", phase: 6, group: "Optimize ve güvenlik" },
];

export const GROUPS: Tool["group"][] = ["Düzenle", "Dönüştür", "Ekle", "Optimize ve güvenlik"];
