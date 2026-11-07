/** Dosya adını kök + uzantıya ayırır. Sunucudaki `split_ext` ile aynı kural: uzantı yalnızca kısa
 * (en fazla 10), harf/rakamdan oluşan son parçadır ("Sürüm 1.2 son" uzantısızdır). */
export function splitName(name: string): { stem: string; ext: string } {
  const n = name.trim();
  const m = /\.[A-Za-z0-9]{1,10}$/.exec(n);
  if (!m || m.index === 0) return { stem: n, ext: "" };
  return { stem: n.slice(0, m.index), ext: m[0] };
}
