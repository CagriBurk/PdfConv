import type { EnginesResponse } from "../api";
import { GROUPS, TOOLS } from "../tools";

export default function Home({ engines }: { engines: EnginesResponse | null }) {
  const missing = (keys: string[] = []) =>
    engines
      ? engines.engines.filter((e) => keys.includes(e.key) && !e.ok).map((e) => e.name)
      : [];

  return (
    <>
      <section className="dropzone" aria-disabled="true">
        <p className="dropzone-title">Dosyayı buraya bırak</p>
        <p className="muted">
          PDF, Word, Excel, PowerPoint, Markdown veya resim. Yükleme Faz 3'te açılacak.
        </p>
      </section>

      {GROUPS.map((group) => (
        <section key={group} className="tool-group">
          <h2>{group}</h2>
          <div className="tool-grid">
            {TOOLS.filter((t) => t.group === group).map((t) => {
              const lacking = missing(t.needs);
              return (
                <article key={t.id} className="tool-card" aria-disabled="true">
                  <div className="tool-card-head">
                    <h3>{t.title}</h3>
                    <span className="phase">Faz {t.phase}</span>
                  </div>
                  <p>{t.description}</p>
                  {lacking.length > 0 && (
                    <p className="warn-line">Eksik: {lacking.join(", ")}</p>
                  )}
                </article>
              );
            })}
          </div>
        </section>
      ))}
    </>
  );
}
