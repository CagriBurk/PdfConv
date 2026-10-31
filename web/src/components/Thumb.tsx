import { useEffect, useRef, useState } from "react";
import { passwords } from "../passwords";
import { thumbnail } from "../pdf";

interface Props {
  fileId: string;
  version: number;
  page: number;
  rotate: number;
  width?: number;
}

/** Görünür olunca çizilen sayfa küçük resmi. Ek döndürme CSS ile gösterilir. */
export default function Thumb({ fileId, version, page, rotate, width = 150 }: Props) {
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
    thumbnail(fileId, version, page, width, passwords.get(fileId))
      .then((u) => alive && setSrc(u))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [visible, fileId, version, page, width]);

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
