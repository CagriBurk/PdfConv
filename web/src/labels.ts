/** İş türlerinin Türkçe adları. Arka uçtaki her iş türünün (`jobs/models.py` JobRequest) burada
 * adı olmalı: tests/test_settings_api.py bunu denetler. */
export const JOB_TYPE_LABEL: Record<string, string> = {
  compose: "Sayfa düzenleme",
  merge: "Birleştirme",
  split: "Bölme",
  images_to_pdf: "Resim → PDF",
  pdf_to_images: "PDF → Resim",
  md_to_pdf: "Markdown → PDF",
  office_to_pdf: "Office → PDF",
  apply: "İçerik ekleme",
  compress: "Sıkıştırma",
  ocr: "OCR (metin tanıma)",
  encrypt: "Şifreleme",
  decrypt: "Şifre kaldırma",
  clean_metadata: "Meta veri temizliği",
  repair: "Onarım",
  install_engine: "Motor kurulumu",
};

const ENGINE_NAME: Record<string, string> = { libreoffice: "LibreOffice" };

/** İşin ekranda görünen adı. Bilinmeyen türde (yeni sürümden kalmış kayıt) ham ad. */
export function jobLabel(type: string, request?: Record<string, unknown>): string {
  if (type === "install_engine" && typeof request?.engine === "string") {
    return `${ENGINE_NAME[request.engine] ?? request.engine} kurulumu`;
  }
  return JOB_TYPE_LABEL[type] ?? type;
}
