// Kayıtlı temayı ilk boyamadan önce uygular (anahtar src/theme.ts ile aynı). Satır içi betik
// olamaz (içerik güvenlik politikası); bu küçük dosya <head>'de engelleyici yüklenir. Modül
// betiği ertelendiği için main.tsx'teki uygulama tek başına ilk karede açık zemin gösteriyordu.
try {
  var tema = localStorage.getItem("pa-tema");
  if (tema === "light" || tema === "dark") document.documentElement.dataset.theme = tema;
} catch (e) {
  // Depolama kapalı: sistem tercihi geçerli.
}
