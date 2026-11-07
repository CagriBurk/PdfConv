import { useEffect, useRef } from "react";
import type { EnginesResponse } from "../api";
import { EngineList } from "./Settings";

interface Props {
  engines: EnginesResponse | null;
  onRefresh: () => void;
  onDone: () => void;
}

const TOUR = [
  ["Dosyayı bırak", "Ana sayfadaki alana bir ya da birkaç dosya bırak; türüne göre doğru araç açılır (PDF, Word, Markdown, fotoğraf)."],
  ["Orijinaline dokunulmaz", "Her işlem yeni bir sürüm oluşturur. Beğenmezsen “Önceki sürüme dön” ile geri alırsın."],
  ["Dosyalar bu bilgisayarda kalır", "Hiçbir şey internete gönderilmez. Dosyalar bir süre sonra kendiliğinden silinir; saklamak istediklerini İşler ve dosyalar'da sabitle."],
  ["Klavyeyle de olur", "Sayfa düzenleyicide oklarla gez, Boşluk ile seç, Delete ile sil, R ile döndür, Ctrl+Z ile geri al."],
] as const;

/** İlk açılış: motorların durumu (eksikse ne yapılacağı) ve kısa tanıtım. */
export default function Welcome({ engines, onRefresh, onDone }: Props) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  const missing = engines?.engines.filter((e) => !e.ok) ?? [];
  return (
    <section className="welcome" aria-labelledby="hosgeldin">
      <h1 id="hosgeldin" ref={heading} tabIndex={-1}>
        PDF Atölyesi'ne hoş geldin
      </h1>
      <p className="lead">
        PDF birleştirme, sayfa düzenleme, imza ve yazı ekleme, sıkıştırma, OCR, Word/Markdown → PDF: hepsi bu bilgisayarda,
        kayıt ve reklam olmadan.
      </p>

      <ol className="tour">
        {TOUR.map(([title, text]) => (
          <li key={title}>
            <strong>{title}</strong>
            <span>{text}</span>
          </li>
        ))}
      </ol>

      <h2>Hazırlık</h2>
      {!engines ? (
        <p className="muted">Motorlar denetleniyor…</p>
      ) : missing.length === 0 ? (
        <p className="ok-line">Her şey hazır: bütün araçlar kullanılabilir.</p>
      ) : (
        <>
          <p>
            Araçların çoğu hemen çalışır. Aşağıdakiler eksik; yalnızca yanında yazan araçlar için gerekir, istersen sonra
            Ayarlar'dan da kurabilirsin.
          </p>
          <EngineList data={{ ...engines, engines: missing }} onRefresh={onRefresh} />
        </>
      )}

      <div className="form-actions">
        <button type="button" className="primary" onClick={onDone}>
          Başla
        </button>
        <a href="#/ayarlar" onClick={onDone}>
          Önce ayarlara bak
        </a>
      </div>
    </section>
  );
}
