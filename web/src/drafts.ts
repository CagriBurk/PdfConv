/** Markdown taslakları: sekme kapanır ya da tarayıcı çökerse yazılan not kaybolmasın.
 *
 * Tarayıcının yerel deposunda (bu bilgisayarda, bu tarayıcı profilinde) tutulur; sunucuya
 * gönderilmez. Depo kapalı/dolu olabilir (gizli pencere, 5 MB sınırı): her çağrı try/catch ile
 * korunur, taslak tutulamazsa uygulama yine çalışır. */
export interface Draft {
  text: string;
  at: number; // ms
  name: string;
}

const PREFIX = "pa-md-taslak:";

export const drafts = {
  get(key: string): Draft | null {
    try {
      const raw = window.localStorage.getItem(PREFIX + key);
      if (!raw) return null;
      const d = JSON.parse(raw) as Draft;
      return typeof d?.text === "string" ? d : null;
    } catch {
      return null;
    }
  },
  set(key: string, draft: Draft): boolean {
    try {
      window.localStorage.setItem(PREFIX + key, JSON.stringify(draft));
      return true;
    } catch {
      return false;
    }
  },
  remove(key: string): void {
    try {
      window.localStorage.removeItem(PREFIX + key);
    } catch {
      /* depo kapalı */
    }
  },
};

export const draftKey = (fileId: string | null | undefined) => fileId ?? "yeni";

export function formatDraftTime(at: number): string {
  return new Date(at).toLocaleString("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
