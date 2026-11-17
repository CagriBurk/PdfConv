import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Job } from "./api";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// İş izleyicisi elle sürülür: sunucu yok.
let push: ((j: Job) => void) | null = null;
let lose: (() => void) | null = null;
const stopWatch = vi.fn();
vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  api: { submitJob: vi.fn(async () => job("calisiyor")) },
  watchJob: (_id: string, onUpdate: (j: Job) => void, onLost?: () => void) => {
    push = onUpdate;
    lose = onLost ?? null;
    return stopWatch;
  },
}));

const { clearFinishedJobs, useJob, useJobActivity } = await import("./hooks");

function job(status: Job["status"]): Job {
  return { id: "j1", type: "compress", status, created: 0, started: null, finished: null, progress: 0,
    message: "", outputs: [], warnings: [], error: null, request: {}, files: [] };
}

let activity: ReturnType<typeof useJobActivity> | null = null;
let starter: ReturnType<typeof useJob> | null = null;
function Badge() {
  activity = useJobActivity();
  return null;
}
function Screen() {
  starter = useJob();
  return null;
}

function mount(node: React.ReactNode) {
  const root = createRoot(document.createElement("div"));
  act(() => root.render(node));
  return () => act(() => root.unmount());
}

describe("üst çubuk iş rozeti", () => {
  afterEach(() => {
    clearFinishedJobs();
    stopWatch.mockClear();
  });

  it("ekranında biten iş rozette kalmaz", async () => {
    const unBadge = mount(<Badge />);
    const unScreen = mount(<Screen />);
    await act(async () => void (await starter!.start({ type: "compress" })));
    expect(activity).toEqual({ running: 1, done: 0, failed: 0 });
    act(() => push!(job("bitti")));
    expect(activity).toEqual({ running: 0, done: 0, failed: 0 });
    unScreen();
    unBadge();
  });

  it("ekrandan ayrıldıktan sonra biten iş görülene kadar sayılır; izleme sürer", async () => {
    const unBadge = mount(<Badge />);
    const unScreen = mount(<Screen />);
    await act(async () => void (await starter!.start({ type: "compress" })));
    unScreen();
    expect(stopWatch).not.toHaveBeenCalled();
    act(() => push!(job("bitti")));
    expect(activity).toEqual({ running: 0, done: 1, failed: 0 });
    act(() => clearFinishedJobs());
    expect(activity).toEqual({ running: 0, done: 0, failed: 0 });
    unBadge();
  });

  it("izleyici bırakınca (sunucu kapandı) rozet çalışıyor'da takılı kalmaz", async () => {
    const unBadge = mount(<Badge />);
    const unScreen = mount(<Screen />);
    await act(async () => void (await starter!.start({ type: "compress" })));
    unScreen();
    expect(activity).toEqual({ running: 1, done: 0, failed: 0 });
    act(() => lose!());
    expect(activity).toEqual({ running: 0, done: 0, failed: 0 });
    unBadge();
  });

  it("iş yokken ya da bitmişken ekrandan ayrılınca izleyici kapanır", async () => {
    const unScreen = mount(<Screen />);
    await act(async () => void (await starter!.start({ type: "compress" })));
    act(() => push!(job("hata")));
    unScreen();
    expect(stopWatch).toHaveBeenCalled();
  });
});
