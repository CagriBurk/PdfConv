import { useEffect, useRef, useState } from "react";
import { bodyInner, scrollRatio, shellKey } from "../mdpreview";

type PreviewWindow = Window & { __paRender?: (root: ParentNode) => unknown; __sonuc?: unknown };

/** Markdown önizleme çerçevesi. Yazarken kaydırma konumu kaybolmasın diye içerik mümkünse
 * yerinde güncellenir (bkz. mdpreview.ts).
 *
 * Güvenlik: çerçevenin içerik güvenlik politikası (yalnızca sunucunun nonce verdiği KaTeX
 * betikleri) yerinde güncellemede de geçerlidir: `innerHTML` ile gelen <script> hiç çalışmaz,
 * satır içi olay işleyicileri (onerror=...) politika gereği engellenir. */
export default function PreviewFrame({ html }: { html: string }) {
  const ref = useRef<HTMLIFrameElement>(null);
  const shell = useRef<string | null>(null);
  const loading = useRef(false);
  const restoreRatio = useRef<number | null>(null);
  const [srcDoc, setSrcDoc] = useState("");

  useEffect(() => {
    if (!html) return;
    const frame = ref.current;
    const win = frame?.contentWindow as PreviewWindow | null | undefined;
    const doc = frame?.contentDocument;
    const key = shellKey(html);
    if (!loading.current && shell.current === key && win?.__paRender && doc?.body) {
      doc.body.innerHTML = bodyInner(html);
      win.__paRender(doc.body);
      return;
    }
    const el = doc?.scrollingElement;
    if (el && !loading.current) restoreRatio.current = scrollRatio(el.scrollTop, el.scrollHeight, el.clientHeight);
    shell.current = key;
    loading.current = true;
    setSrcDoc(html);
  }, [html]);

  const onLoad = () => {
    loading.current = false;
    const ratio = restoreRatio.current;
    restoreRatio.current = null;
    if (!ratio) return;
    // Formüller ve resimler çizilince (yükseklik oturunca) eski konuma dön.
    const started = Date.now();
    const restore = () => {
      const frame = ref.current;
      const win = frame?.contentWindow as PreviewWindow | null | undefined;
      const el = frame?.contentDocument?.scrollingElement;
      if (!win || !el) return;
      if (win.__sonuc === undefined && Date.now() - started < 3000) {
        window.setTimeout(restore, 50);
        return;
      }
      el.scrollTop = ratio * (el.scrollHeight - el.clientHeight);
    };
    restore();
  };

  return (
    <iframe ref={ref} title="Önizleme" sandbox="allow-scripts allow-same-origin" srcDoc={srcDoc} onLoad={onLoad} />
  );
}
