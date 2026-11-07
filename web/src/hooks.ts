import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, watchJob, type FileMeta, type Job } from "./api";
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
