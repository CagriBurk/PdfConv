/**
 * Şifreli PDF'lerin şifreleri yalnızca bu sekmenin belleğinde tutulur; sunucuya her işte
 * yeniden gönderilir, diske ya da tarayıcı deposuna yazılmaz. Sayfa yenilenince unutulur.
 */
const store = new Map<string, string>();

export const passwords = {
  get: (fileId: string) => store.get(fileId),
  set: (fileId: string, pw: string) => store.set(fileId, pw),
  /** İş isteğine eklenecek { dosyaId: şifre } sözlüğü. */
  forFiles(ids: string[]): Record<string, string> {
    const out: Record<string, string> = {};
    for (const id of ids) {
      const pw = store.get(id);
      if (pw) out[id] = pw;
    }
    return out;
  },
};
