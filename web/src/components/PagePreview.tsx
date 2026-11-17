import { useEffect, useRef, useState, type ReactNode } from "react";
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

/** Kapsayıcının iç genişliği: dar ekranda önizleme taşmasın diye küçülür. */
function useAvailableWidth(ref: React.RefObject<HTMLElement | null>) {
  const [avail, setAvail] = useState<number | null>(null);
  useEffect(() => {
    const parent = ref.current?.parentElement;
    if (!parent) return;
    const measure = () => {
      const cs = getComputedStyle(parent);
      setAvail(parent.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(parent);
    return () => ro.disconnect();
  }, [ref]);
  return avail;
}

/** Sayfanın küçük resmi + üstünde yaklaşık önizleme (filigran, sayfa numarası). */
export default function PagePreview({ file, page = 0, width = 320, children }: Props) {
  const [src, setSrc] = useState<string | null>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const avail = useAvailableWidth(box);
  // Resim `width` ile bir kez çizilir; ekrandaki boyut yalnızca CSS ile küçülür.
  const shown = avail ? Math.min(width, Math.floor(avail)) : width;

  useEffect(() => {
    let alive = true;
    let pageObj: { cleanup?: () => void } | null = null;
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
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file.id, file.version, file.updated, page, width]);

  if (!size || !src) {
    return <div ref={box} className="page-preview loading" style={{ width: shown, height: shown * 1.41 }} />;
  }
  const scale = shown / size.w;
  return (
    <div ref={box} className="page-preview" style={{ width: shown, height: size.h * scale }}>
      <img src={src} alt="" width={shown} />
      <div className="page-preview-overlay">{children(scale, size)}</div>
    </div>
  );
}
