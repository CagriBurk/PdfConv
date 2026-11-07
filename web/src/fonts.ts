// Tarayıcıdaki CSS adları; sunucu aynı TTF'i gömer (core/fonts.py FAMILIES). Önizleme ile
// PDF'teki yazı aynı fontla çizilsin.
//
// Noto ailesi uygulamayla gelir (OFL) ve sunucudan yüklenir: Windows fontlarına bağımlı değil.
// Windows fontları bilgisayarda varsa ek seçenektir (tarayıcı onları zaten tanır).
export const FONT_CSS: Record<string, string> = {
  "noto-sans": '"PA Noto Sans"',
  "noto-serif": '"PA Noto Serif"',
  "noto-mono": '"PA Noto Sans Mono"',
  segoe: '"Segoe UI"',
  arial: "Arial",
  calibri: "Calibri",
  times: '"Times New Roman"',
  georgia: "Georgia",
  consolas: "Consolas",
};

export const DEFAULT_FONT = "noto-sans";

const BUNDLED: [string, string][] = [
  ["noto-sans", "PA Noto Sans"],
  ["noto-serif", "PA Noto Serif"],
  ["noto-mono", "PA Noto Sans Mono"],
];

let loading: Promise<void> | null = null;

/** Gömülü fontları tarayıcıya yükler (bir kez). Konva tuvali font yüklenmeden çizerse yazı
 * yedek fontla görünür; editör bunu bekler. Yüklenemezse sessizce yedek fonta düşülür. */
export function loadBundledFonts(): Promise<void> {
  if (!loading) {
    const faces = BUNDLED.flatMap(([key, family]) =>
      [false, true].map((bold) => {
        const face = new FontFace(family, `url(/api/fonts/${key}/file${bold ? "?bold=true" : ""})`, {
          weight: bold ? "700" : "400",
        });
        return face.load().then(
          (f) => {
            document.fonts.add(f);
          },
          () => undefined,
        );
      }),
    );
    loading = Promise.all(faces).then(() => undefined);
  }
  return loading;
}
