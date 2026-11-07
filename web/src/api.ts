export type EngineKey = "libreoffice" | "browser" | "tesseract" | "ghostscript";

export interface EngineStatus {
  key: EngineKey;
  name: string;
  available: boolean;
  ok: boolean;
  needed_for: string;
  path: string | null;
  version: string | null;
  problems: string[];
  install_hint: string | null;
}

export interface EnginesResponse {
  engines: EngineStatus[];
  libraries: Record<string, string | null>;
  data_dir: string;
  config_file: string | null;
  vault_path: string | null;
  retention_hours: number;
  log_file: string;
  version: string;
  installed: boolean;
  install_dir: string | null;
}

export interface UpdateInfo {
  current: string;
  latest: string | null;
  newer: boolean;
  url: string;
  message: string;
}

export interface LanInfo {
  enabled: boolean;
  urls?: string[];
  qr_svg?: string | null;
  devices?: { ip: string; paired_at: number }[];
}

export type FileKind = "pdf" | "image" | "markdown" | "text" | "office" | "html" | "other";

export interface FileVersion {
  n: number;
  note: string;
  created: number;
  size: number;
  page_count: number | null;
}

export interface FileMeta {
  id: string;
  name: string;
  kind: FileKind;
  created: number;
  updated: number;
  source: "upload" | "job";
  versions: FileVersion[];
  version: number;
  size: number;
  page_count: number | null;
  pinned: boolean;
  encrypted: boolean;
  job_id: string | null;
  tag: string | null;
}

export type JobStatus = "bekliyor" | "calisiyor" | "bitti" | "hata" | "iptal";

export interface Job {
  id: string;
  type: string;
  status: JobStatus;
  created: number;
  started: number | null;
  finished: number | null;
  progress: number;
  message: string;
  outputs: string[];
  warnings: string[];
  error: string | null;
  request: Record<string, unknown>;
  files: FileMeta[];
}

export interface MdPreview {
  html: string;
  warnings: string[];
  title: string | null;
  options: { theme: string; paper: string; toc: boolean; cover: boolean; landscape: boolean };
}

export interface PdfInfo {
  file_size: number;
  encrypted: boolean;
  needs_password: boolean;
  page_count: number;
  has_text: boolean | null;
  bookmark_count: number;
  metadata: Record<string, string>;
  pdf_version: string | null;
}

export interface FontInfo {
  key: string;
  name: string;
  bold: boolean;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    credentials: "same-origin",
    ...init,
    headers: { Accept: "application/json", ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = `Sunucu ${res.status} döndürdü`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* gövde JSON değil */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** Yükleme ilerlemesini bildirebilmek için fetch yerine XMLHttpRequest. */
function uploadFiles(files: File[], onProgress?: (fraction: number) => void): Promise<FileMeta[]> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f, f.name));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/files");
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as FileMeta[]);
      else reject(new ApiError(xhr.response?.detail ?? `Yükleme başarısız (${xhr.status})`, xhr.status));
    };
    xhr.onerror = () => reject(new ApiError("Sunucuya ulaşılamadı", 0));
    xhr.send(form);
  });
}

export const api = {
  session: () => request<{ ok: boolean; version: string }>("/api/session"),
  engines: (refresh = false) => request<EnginesResponse>(`/api/engines${refresh ? "?refresh=true" : ""}`),

  upload: uploadFiles,
  files: () => request<FileMeta[]>("/api/files"),
  file: (id: string) => request<FileMeta>(`/api/files/${id}`),
  /** Not / metin dosyası; kod çözümü sunucuda (UTF-8 değilse Windows-1254 ve `note`). */
  text: (id: string) => request<{ text: string; note: string | null }>(`/api/files/${id}/text`),
  undo: (id: string) => request<FileMeta>(`/api/files/${id}/undo`, { method: "POST" }),
  pin: (id: string, pinned: boolean) => request<FileMeta>(`/api/files/${id}/pin`, json({ pinned })),
  rename: (id: string, name: string) => request<FileMeta>(`/api/files/${id}/rename`, json({ name })),
  remove: (id: string) => request<{ ok: boolean }>(`/api/files/${id}`, { method: "DELETE" }),
  checkPassword: (id: string, password: string) =>
    request<{ ok: boolean; page_count: number }>(`/api/files/${id}/password`, json({ password })),

  rawUrl: (id: string, version?: number) => `/api/files/${id}/raw${version ? `?v=${version}` : ""}`,
  downloadUrl: (id: string, version?: number) => `/api/files/${id}/download${version ? `?v=${version}` : ""}`,
  zipUrl: (ids: string[], name = "dosyalar") =>
    `/api/zip?ids=${ids.join(",")}&name=${encodeURIComponent(name)}`,

  submitJob: (payload: Record<string, unknown>) => request<Job>("/api/jobs", json(payload)),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  jobs: (limit = 50) => request<Job[]>(`/api/jobs?limit=${limit}`),
  cancelJob: (id: string) => request<Job>(`/api/jobs/${id}/cancel`, { method: "POST" }),

  mdPreview: (text: string, attachments: string[], options: Record<string, unknown>) =>
    request<MdPreview>("/api/md/preview", json({ text, attachments, options })),

  lan: () => request<LanInfo>("/api/lan"),
  checkUpdate: () => request<UpdateInfo>("/api/update"),
  revokeDevices: () => request<{ revoked: number }>("/api/lan/devices", { method: "DELETE" }),
  info: (id: string) => request<PdfInfo>(`/api/files/${id}/info`),
  fonts: () => request<FontInfo[]>("/api/fonts"),
  signatures: () => request<FileMeta[]>("/api/signatures"),
  addSignature: (file: Blob, name: string) => {
    const form = new FormData();
    form.append("file", file, name);
    return request<FileMeta>("/api/signatures", { method: "POST", body: form });
  },
};

/** İşi canlı izler (SSE). Bağlantı koparsa yoklamaya düşer. Dönen fonksiyon izlemeyi durdurur. */
export function watchJob(id: string, onUpdate: (job: Job) => void): () => void {
  let stopped = false;
  let timer: number | undefined;
  const source = new EventSource(`/api/jobs/${id}/events`);
  const done = (j: Job) => ["bitti", "hata", "iptal"].includes(j.status);

  const poll = async () => {
    if (stopped) return;
    try {
      const j = await api.job(id);
      onUpdate(j);
      if (done(j)) return;
    } catch {
      /* geçici hata: yeniden dene */
    }
    timer = window.setTimeout(poll, 700);
  };

  source.onmessage = (e) => {
    const j = JSON.parse(e.data) as Job;
    onUpdate(j);
    if (done(j)) source.close();
  };
  source.onerror = () => {
    source.close();
    void poll();
  };
  return () => {
    stopped = true;
    source.close();
    window.clearTimeout(timer);
  };
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
