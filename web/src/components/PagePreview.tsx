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
    let pageObj: { cleanup?: () => void } | null = null;
    const canvas = document.createElement("canvas");
    const pw = passwords.get(file.id);
    void openPdf(file, pw)
      .then((doc) => doc.getPage(page + 1))
      .then((p) => {
        pageObj = p;
        try {
          const v = p.getViewport({ scale: 1 });
          if (alive) setSize({ w: v.width, h: v.height });
        } finally {
          p.cleanup();
        }
      })
      .catch(() => undefined);
    thumbnail(file, page, width, pw)
      .then((u) => alive && setSrc(u))
      .catch(() => undefined);
    return () => {
      alive = false;
      try {
        pageObj?.cleanup?.();
      } catch {
        /* yoksay */
      }
      canvas.width = 0;
      canvas.height = 0;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file.id, file.version, file.updated, page, width]);

  if (!size || !src) return <div className="page-preview loading" style={{ width, height: width * 1.41 }} />;
  const scale = width / size.w;
  return (
    <div className="page-preview" style={{ width, height: size.h * scale }}>
      <img src={src} alt="" width={width} />
      <div className="page-preview-overlay">{children(scale, size)}</div>
    </div>
  );
}
