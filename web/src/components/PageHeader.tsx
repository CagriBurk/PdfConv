import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import { useRoute } from "../router";
import { TOOLS, toolForRoute } from "../tools";
import Icon from "./Icon";

/** Araç ekranının başlığı: konum (Araçlar / grup / araç), grup renkli ikon, başlık ve açıklama.
 * Araç, geçerli rotadan (yoksa başlıktan) bulunur; bulunamazsa yalnızca geri bağlantısı ve başlık. */
export default function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  const route = useRoute();
  const tool = toolForRoute(route.path[0]) ?? TOOLS.find((t) => t.title === title);

  // Üst menüdeki "Araçlar" bağlantısı ekranda tek kalsın: bunun adı farklı.
  const back = (
    <a href="#/araclar" className="crumb-back" aria-label="Araçlara dön">
      {!tool && <Icon icon={ArrowLeft} size={16} />}
      Araçlar
    </a>
  );

  return (
    <div className="page-header">
      <nav aria-label="Konum" className="crumbs">
        <ol>
          <li>{back}</li>
          {tool && (
            <>
              <li>{tool.group}</li>
              <li aria-current="page">{tool.title}</li>
            </>
          )}
        </ol>
      </nav>
      <div className="page-header-main">
        {tool && (
          <span className={`tile lg ${tool.tone}`}>
            <Icon icon={tool.icon} size={25} strokeWidth={1.9} />
          </span>
        )}
        <div className="page-header-text">
          <h1>{title}</h1>
          {tool && <p className="page-header-desc">{tool.description}</p>}
        </div>
        {children && <div className="page-header-extra">{children}</div>}
      </div>
    </div>
  );
}
