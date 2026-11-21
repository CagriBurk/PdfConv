import { Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useUpload } from "../hooks";
import { homeRoute } from "../pages/Home";
import { navigate } from "../router";
import { toast } from "../toast";
import Icon from "./Icon";

const PASSIVE_SECTIONS = new Set(["araclar", "isler", "ayarlar"]);

/** Pencerenin herhangi bir yerine dosya sürüklenince açılan manyetik bırakma perdesi.
 * Kendi dosya bırakma alanı olan araç ekranlarına karışmaz; yalnızca Ana Sayfa, İşler ve Ayarlar'da
 * etkinleşir (ve Ana Sayfa'daki DropZone üstündeyken ona bırakır). */
export default function GlobalDropOverlay({ section }: { section: string }) {
  const [active, setActive] = useState(false);
  const depth = useRef(0);
  const { upload, uploading } = useUpload({ toastErrors: true });
  const enabled = PASSIVE_SECTIONS.has(section);

  useEffect(() => {
    if (!enabled) {
      depth.current = 0;
      setActive(false);
      return;
    }

    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    const insideDropzone = (target: EventTarget | null) =>
      target instanceof Element && !!target.closest(".dropzone");

    const onDragEnter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth.current++;
      if (!insideDropzone(e.target)) setActive(true);
    };
    const onDragOver = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      if (insideDropzone(e.target)) {
        setActive(false);
        return;
      }
      e.preventDefault();
      setActive(true);
    };
    const onDragLeave = () => {
      depth.current = Math.max(0, depth.current - 1);
      if (depth.current === 0) setActive(false);
    };
    const onDrop = async (e: DragEvent) => {
      depth.current = 0;
      setActive(false);
      if (!hasFiles(e) || insideDropzone(e.target)) return;
      e.preventDefault();
      const files = Array.from(e.dataTransfer?.files ?? []);
      if (!files.length) return;
      const metas = await upload(files);
      if (!metas.length) return;
      const next = homeRoute(metas);
      if (next.type === "go") navigate(next.path, next.query);
      else if (next.type === "choose") navigate("donustur", { dosya: next.ids });
      else toast.error(next.message);
    };

    window.addEventListener("dragenter", onDragEnter);
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onDragEnter);
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("drop", onDrop);
    };
  }, [enabled, upload]);

  if (!active && !uploading) return null;
  if (!active) return null;

  return (
    <div className="global-drop" aria-hidden="true">
      <div className="global-drop-card">
        <span className="global-drop-icon">
          <Icon icon={Upload} size={28} strokeWidth={2.1} />
        </span>
        <strong>Dosyayı buraya bırak</strong>
        <span>PDF, resim, Office ya da Markdown — Toolia uygun aracı otomatik açar.</span>
      </div>
    </div>
  );
}
