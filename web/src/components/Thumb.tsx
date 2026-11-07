import { useEffect, useRef, useState } from "react";
import { passwords } from "../passwords";
import { thumbnail, type PdfRef } from "../pdf";

interface Props {
  file: PdfRef;
  page: number;
  rotate: number;
  width?: number;
}

/** Görünür olunca çizilen sayfa küçük resmi. Ek döndürme CSS ile gösterilir. */
export default function Thumb({ file, page, rotate, width = 150 }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setVisible(true), {
      rootMargin: "400px",
    });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    let alive = true;
    thumbnail(file, page, width, passwords.get(file.id))
      .then((u) => alive && setSrc(u))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, file.id, file.version, file.updated, page, width]);

  return (
    <div ref={ref} className="thumb-box">
      {src ? (
        <img src={src} alt="" draggable={false} style={{ transform: `rotate(${rotate}deg)` }} />
      ) : (
        <span className="thumb-placeholder">{failed ? "Çizilemedi" : ""}</span>
      )}
    </div>
  );
}
