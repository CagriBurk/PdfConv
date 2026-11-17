import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";
import { applyTheme, storedTheme } from "./theme";

// Kayıtlı tema: ilk boyamadan önce public/tema.js uygular; burada yeniden (ör. betik yüklenemediyse).
applyTheme(storedTheme());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
