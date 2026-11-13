import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, watchJob, type FileMeta, type Job } from "./api";
import { passwords } from "./passwords";
import { toast } from "./toast";

/** Dosya yükleme durumu: ilerleme ve hata. `toastErrors`: hatayı ekranında göstermeyen
 * ekranlar için bildirim (sayfa düzenleyiciye çok büyük dosya bırakılınca hiçbir şey olmuyor
 * sanılıyordu: sunucu reddediyor ama hata görünmüyordu). */
export function useUpload({ toastErrors = false }: { toastErrors?: boolean } = {}) {
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const upload = useCallback(async (files: File[]): Promise<FileMeta[]> => {
    setError(null);
    setProgress(0);
    try {
      return await api.upload(files, setProgress);
    } catch (e) {
      setError(errorMessage(e));
      if (toastErrors) toast.error(errorMessage(e));
      return [];
    } finally {
      setProgress(null);
    }
  }, [toastErrors]);

  return { upload, uploading: progress !== null, progress, error, setError };
}

/** İş başlatır ve bitene kadar canlı izler. */
export function useJob() {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stop = useRef<(() => void) | null>(null);

  useEffect(() => () => stop.current?.(), []);

  const start = useCallback(async (payload: Record<string, unknown>) => {
    stop.current?.();
    setError(null);
    setJob(null);
    try {
      const j = await api.submitJob(payload);
      setJob(j);
      stop.current = watchJob(j.id, setJob);
      return j;
    } catch (e) {
      setError(errorMessage(e));
      return null;
    }
  }, []);

  const reset = useCallback(() => {
    stop.current?.();
    setJob(null);
    setError(null);
  }, []);

  const running = !!job && (job.status === "bekliyor" || job.status === "calisiyor");
  return { job, start, reset, running, error };
}

/** Kimliği verilen dosyaların meta verisini yükler (sayfa yenilenince URL'den geri gelir). */
export function useFiles(ids: string[]) {
  const key = ids.join(",");
  const [files, setFiles] = useState<FileMeta[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    if (!key) {
      setFiles([]);
      return;
    }
    Promise.all(key.split(",").map((id) => api.file(id)))
      .then((f) => alive && setFiles(f))
      .catch((e) => alive && setError(errorMessage(e)));
    return () => {
      alive = false;
    };
  }, [key]);

  return { files, setFiles, error };
}

export interface UnlockQueueOptions {
  onUnlock?: (files: FileMeta[]) => void;
  onCancel?: (file: FileMeta) => void;
}

/** Sayfaya URL / yönlendirmeyle gelen dosyalar arasında şifreli olanlar için PasswordDialog
 * kuyruğunu yönetir. Şifresi çözülenler onUnlock ile verilir, vazgeçilenler onCancel ile bildirilir. */
export function useUnlockQueue(options: UnlockQueueOptions = {}) {
  const [queue, setQueue] = useState<FileMeta[]>([]);
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const lastKey = useRef("");

  const queueFiles = useCallback((files: FileMeta[]) => {
    const key = files.map((f) => f.id).join(",");
    if (!key || key === lastKey.current) return;
    lastKey.current = key;

    const ready: FileMeta[] = [];
    const locked: FileMeta[] = [];
    for (const f of files) {
      if (f.encrypted && !passwords.get(f.id)) {
        locked.push(f);
      } else {
        ready.push(f);
      }
    }

    if (ready.length) {
      const needsCount = ready.some((f) => f.encrypted && f.page_count == null && passwords.get(f.id));
      if (needsCount) {
        Promise.all(
          ready.map(async (f) => {
            if (f.encrypted && f.page_count == null) {
              const pw = passwords.get(f.id);
              if (pw) {
                try {
                  const res = await api.checkPassword(f.id, pw);
                  return { ...f, page_count: res.page_count };
                } catch {
                  return f;
                }
              }
            }
            return f;
          }),
        )
          .then((enriched) => optionsRef.current.onUnlock?.(enriched))
          .catch(() => optionsRef.current.onUnlock?.(ready));
      } else {
        optionsRef.current.onUnlock?.(ready);
      }
    }

    if (locked.length) {
      setQueue((prev) => [...prev, ...locked]);
    }
  }, []);

  const onDone = useCallback(
    async (ok: boolean) => {
      const head = queue[0];
      if (!head) return;
      setQueue((prev) => prev.slice(1));

      if (ok) {
        let unlocked: FileMeta = head;
        if (unlocked.page_count == null) {
          const pw = passwords.get(unlocked.id);
          if (pw) {
            try {
              const res = await api.checkPassword(unlocked.id, pw);
              unlocked = { ...unlocked, page_count: res.page_count };
            } catch {
              // yoksay
            }
          }
        }
        optionsRef.current.onUnlock?.([unlocked]);
      } else {
        lastKey.current = "";
        optionsRef.current.onCancel?.(head);
      }
    },
    [queue],
  );

  return {
    locked: queue[0] ?? null,
    onDone,
    queue: queueFiles,
  };
}

const KEEPALIVE_MS = 10 * 60 * 1000;

/** Ekranda açık dosyaları düzenli aralıklarla yoklar: sunucu bunları "kullanımda" sayar ve otomatik
 * temizlik (saklama süresi) açık bir düzenleyicinin altından dosyayı silmez. */
export function useKeepAlive(ids: (string | null | undefined)[]) {
  const key = ids.filter(Boolean).join(",");
  useEffect(() => {
    if (!key) return;
    const ping = () => key.split(",").forEach((id) => void api.file(id).catch(() => undefined));
    const t = window.setInterval(ping, KEEPALIVE_MS);
    return () => window.clearInterval(t);
  }, [key]);
}
