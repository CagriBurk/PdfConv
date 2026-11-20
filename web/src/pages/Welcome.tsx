import { ArrowRight, CircleCheck, HardDrive, History, Keyboard, Upload, type LucideIcon } from "lucide-react";
import { useEffect, useRef } from "react";
import type { EnginesResponse } from "../api";
import BrandMark from "../components/BrandMark";
import Icon from "../components/Icon";
import { EngineList } from "./Settings";

interface Props {
  engines: EnginesResponse | null;
  onRefresh: () => void;
  onDone: () => void;
}

const TOUR: readonly (readonly [LucideIcon, string, string])[] = [
  [Upload, "Dosyayı bırak", "Ana sayfadaki alana bir ya da birkaç dosya bırak; türüne göre doğru araç açılır (PDF, Word, Markdown, fotoğraf)."],
  [History, "Orijinaline dokunulmaz", "Her işlem yeni bir sürüm oluşturur. Beğenmezsen “Önceki sürüme dön” ile geri alırsın."],
  [HardDrive, "Dosyalar bu bilgisayarda kalır", "Hiçbir şey internete gönderilmez. Dosyalar bir süre sonra kendiliğinden silinir; saklamak istediklerini İşler ve dosyalar'da sabitle."],
  [Keyboard, "Klavyeyle de olur", "Sayfa düzenleyicide oklarla gez, Boşluk ile seç, Delete ile sil, R ile döndür, Ctrl+Z ile geri al."],
];

/** İlk açılış: motorların durumu (eksikse ne yapılacağı) ve kısa tanıtım. */
export default function Welcome({ engines, onRefresh, onDone }: Props) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  const missing = engines?.engines.filter((e) => !e.ok) ?? [];
  return (
    <section className="card welcome" aria-labelledby="hosgeldin">
      <div className="welcome-head">
        {/* Üst çubuktaki marka işaretinin büyüğü. */}
        <BrandMark size={56} className="welcome-mark" />
        <h1 id="hosgeldin" ref={heading} tabIndex={-1}>
          Toolia'ya hoş geldin
        </h1>
        <p className="lead">
          PDF birleştirme, sayfa düzenleme, imza ve yazı ekleme, sıkıştırma, OCR, Word/Markdown → PDF: hepsi bu bilgisayarda,
          kayıt ve reklam olmadan.
        </p>
      </div>

      <ol className="tour">
        {TOUR.map(([icon, title, text]) => (
          <li key={title}>
            <span className="tour-icon">
              <Icon icon={icon} size={19} strokeWidth={1.9} />
            </span>
            <span className="tour-text">
              <strong>{title}</strong>
              <span>{text}</span>
            </span>
          </li>
        ))}
      </ol>

      <div className="welcome-ready">
        <h2>Hazırlık</h2>
        {!engines ? (
          <p className="muted">Motorlar denetleniyor…</p>
        ) : missing.length === 0 ? (
          <p className="ok-line">
            <Icon icon={CircleCheck} />
            Her şey hazır: bütün araçlar kullanılabilir.
          </p>
        ) : (
          <>
            <p className="welcome-missing">
              Araçların çoğu hemen çalışır. Aşağıdakiler eksik; yalnızca yanında yazan araçlar için gerekir, istersen sonra
              Ayarlar'dan da kurabilirsin.
            </p>
            <EngineList data={{ ...engines, engines: missing }} onRefresh={onRefresh} />
          </>
        )}
      </div>

      <div className="form-actions welcome-actions">
        <button type="button" className="primary" onClick={onDone}>
          Başla
          <Icon icon={ArrowRight} />
        </button>
        <a className="text-link" href="#/ayarlar" onClick={onDone}>
          Önce ayarlara bak
        </a>
      </div>
    </section>
  );
}
