import { Component, type ErrorInfo, type ReactNode } from "react";
import { api } from "../api";

interface Props {
  children: ReactNode;
  /** Hatanın nerede olduğu (ekran adı); günlüğe yazılır. */
  where: string;
}

interface State {
  error: Error | null;
  errorId: string | null;
}

/** Bir ekranda beklenmeyen bir hata olursa beyaz sayfa yerine ne olduğunu ve ne yapılacağını
 * söyler; ayrıntı hata kimliğiyle sunucu günlüğüne yazılır. Üst çubuk ve gezinme çalışmaya devam
 * eder: başka ekrana geçince (ya da "Yeniden dene") ekran sıfırdan kurulur. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, errorId: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    const stack = `${error.stack ?? ""}\n--- bileşenler ---${info.componentStack ?? ""}`;
    api
      .clientError({ message: `${error.name}: ${error.message}`, stack, where: this.props.where })
      .then((r) => this.setState({ errorId: r.id }))
      .catch(() => undefined);
  }

  componentDidUpdate(prev: Props): void {
    if (prev.where !== this.props.where && this.state.error) this.setState({ error: null, errorId: null });
  }

  render() {
    const { error, errorId } = this.state;
    if (!error) return this.props.children;
    return (
      <section className="crash" role="alert">
        <h2>Bu ekranda bir şeyler ters gitti</h2>
        <p>
          Dosyaların güvende: sunucudaki dosyalar ve sürümler etkilenmedi. Ekranı yeniden açmayı dene; olmazsa ana
          sayfaya dönüp işini oradan sürdür.
        </p>
        <p className="mono small break">{error.message}</p>
        {errorId && (
          <p className="muted small">
            Hata kimliği: <strong className="mono">{errorId}</strong> (ayrıntısı günlük dosyasında, yolu Ayarlar →
            Gelişmiş'te).
          </p>
        )}
        <div className="crash-actions">
          <button type="button" className="primary" onClick={() => this.setState({ error: null, errorId: null })}>
            Yeniden dene
          </button>
          <a className="button" href="#/araclar">
            Ana sayfaya dön
          </a>
          <button type="button" onClick={() => window.location.reload()}>
            Sayfayı yenile
          </button>
        </div>
      </section>
    );
  }
}
