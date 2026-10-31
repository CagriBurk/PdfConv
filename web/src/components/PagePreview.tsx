import { useEffect, useState, type ReactNode } from "react";
import type { FileMeta } from "../api";
import { passwords } from "../passwords";
import { openPdf, thumbnail } from "../pdf";

interface Props {
  file: FileMeta;
  page?: number;
  width?: number;
  /** Önizleme üstüne çizilecekler; `scale` = ekran pikseli / PDF noktası. */
  children: (scale: number, size: { w: number; h: number }) => ReactNode;
}

/** Sayfanın küçük resmi + üstünde yaklaşık önizleme (filigran, sayfa numarası). */
export default function PagePreview({ file, page = 0, width = 320, children }: Props) {
  const [src, setSrc] = useState<string | null>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    let alive = true;
    const pw = passwords.get(file.id);
    void openPdf(file.id, file.version, pw)
      .then((doc) => doc.getPage(page + 1))
      .then((p) => {
        const v = p.getViewport({ scale: 1 });
        if (alive) setSize({ w: v.width, h: v.height });
      })
      .catch(() => undefined);
    thumbnail(file.id, file.version, page, width, pw)
      .then((u) => alive && setSrc(u))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [file.id, file.version, page, width]);

  if (!size || !src) return <div className="page-preview loading" style={{ width, height: width * 1.41 }} />;
  const scale = width / size.w;
  return (
    <div className="page-preview" style={{ width, height: size.h * scale }}>
      <img src={src} alt="" width={width} />
      <div className="page-preview-overlay">{children(scale, size)}</div>
    </div>
  );
}
