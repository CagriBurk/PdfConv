import { useEffect } from "react";
import { useJob } from "../hooks";
import JobPanel from "./JobPanel";

/** LibreOffice uygulamaya gömülmez (~350 MB). Kullanıcı onaylarsa winget ile kurulur; Windows
 * izin (UAC) penceresi açabilir. Bitince motorlar yeniden taranır (`onInstalled`). */
export default function InstallLibreOffice({ onInstalled }: { onInstalled: () => void }) {
  const job = useJob();

  useEffect(() => {
    if (job.job?.status === "bitti") onInstalled();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.job?.status]);

  const start = () => {
    const ok = window.confirm(
      "LibreOffice (ücretsiz, yaklaşık 350 MB) internetten indirilip kurulacak. Windows izin isteyebilir. " +
        "Kurulum birkaç dakika sürer. Devam edilsin mi?",
    );
    if (ok) void job.start({ type: "install_engine", engine: "libreoffice" });
  };

  return (
    <div className="install-engine">
      <button type="button" onClick={start} disabled={job.running}>
        {job.running ? "LibreOffice kuruluyor…" : "LibreOffice'i kur"}
      </button>
      <JobPanel job={job.job} error={job.error} />
    </div>
  );
}
