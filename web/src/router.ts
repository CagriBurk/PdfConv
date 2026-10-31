import { useEffect, useState } from "react";

/** Basit karma (#) yönlendirici: "#/duzenle/abc?x=1" → { path: ["duzenle", "abc"], query } */
export interface Route {
  path: string[];
  query: URLSearchParams;
}

function parse(): Route {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [p, q = ""] = raw.split("?");
  return { path: p.split("/").filter(Boolean).map(decodeURIComponent), query: new URLSearchParams(q) };
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(parse);
  useEffect(() => {
    const onHash = () => setRoute(parse());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return route;
}

export function navigate(path: string, query?: Record<string, string | string[]>): void {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) {
    params.set(k, Array.isArray(v) ? v.join(",") : v);
  }
  const qs = params.toString();
  window.location.hash = `#/${path}${qs ? `?${qs}` : ""}`;
}

export function idsFrom(route: Route, key = "dosya"): string[] {
  return (route.query.get(key) ?? "").split(",").filter(Boolean);
}
