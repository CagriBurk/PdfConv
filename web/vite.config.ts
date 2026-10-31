import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Geliştirme sırasında /api isteklerini Python sunucusuna yönlendir.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
