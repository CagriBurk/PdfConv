// Kayıtlı temayı ilk boyamadan önce uygular (anahtar src/theme.ts ile aynı). Satır içi betik
// olamaz (içerik güvenlik politikası); bu küçük dosya <head>'de engelleyici yüklenir. Modül
// betiği ertelendiği için main.tsx'teki uygulama tek başına ilk karede açık zemin gösteriyordu.
// Pencerenin başlık çubuğu (theme-color) da seçilen temayı izler (src/theme.ts syncThemeColor).
try {
  var tema = localStorage.getItem("pa-tema");
  if (tema === "light" || tema === "dark") {
    document.documentElement.dataset.theme = tema;
    var renk = tema === "dark" ? "#161a22" : "#ffffff";
    var etiketler = document.querySelectorAll('meta[name="theme-color"]');
    for (var i = 0; i < etiketler.length; i++) etiketler[i].content = renk;
  }
} catch (e) {
  // Depolama kapalı: sistem tercihi geçerli.
}
