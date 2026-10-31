import type { ReactNode } from "react";

export default function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="page-header">
      <a href="#/araclar" className="back" aria-label="Araçlara dön">
        ←
      </a>
      <h1>{title}</h1>
      {children && <div className="page-header-extra">{children}</div>}
    </div>
  );
}
