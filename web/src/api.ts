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
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`Sunucu ${res.status} döndürdü (${url})`);
  return (await res.json()) as T;
}

export const api = {
  health: () => getJson<{ status: string; version: string }>("/api/health"),
  engines: (refresh = false) =>
    getJson<EnginesResponse>(`/api/engines${refresh ? "?refresh=true" : ""}`),
};
