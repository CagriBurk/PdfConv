import { Download, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useJob } from "../hooks";
import Icon from "./Icon";
import JobPanel from "./JobPanel";
import Modal from "./Modal";

/** LibreOffice uygulamaya gömülmez (~350 MB). Kullanıcı onaylarsa winget ile kurulur; Windows
 * izin (UAC) penceresi açabilir. Bitince motorlar yeniden taranır (`onInstalled`). */
export default function InstallLibreOffice({ onInstalled }: { onInstalled: () => void }) {
  const job = useJob();
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (job.job?.status === "bitti") onInstalled();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.job?.status]);

  const start = () => {
    setConfirming(false);
    void job.start({ type: "install_engine", engine: "libreoffice" });
  };

  return (
    <div className="install-engine">
      <button type="button" onClick={() => setConfirming(true)} disabled={job.running}>
        <Icon icon={job.running ? LoaderCircle : Download} className={job.running ? "spin" : undefined} />
        {job.running ? "LibreOffice kuruluyor…" : "LibreOffice'i kur"}
      </button>
      <JobPanel job={job.job} error={job.error} />
      {confirming && (
        <Modal title="LibreOffice kurulsun mu?" onClose={() => setConfirming(false)}>
          <p>
            LibreOffice (ücretsiz, yaklaşık 350 MB) internetten indirilip kurulacak. Windows kurulum izni isteyebilir
            ve işlem birkaç dakika sürebilir.
          </p>
          <div className="modal-actions">
            <button type="button" data-autofocus onClick={() => setConfirming(false)}>
              Vazgeç
            </button>
            <button type="button" className="primary" onClick={start}>
              <Icon icon={Download} size={17} />
              Kurulumu başlat
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
