import { defineConfig } from "vitest/config";

// Arayüz birim testleri (saf mantık: düzenleyici modeli, yönlendirici, taslaklar, şifreler...).
// Uçtan uca testler Python tarafında (tests/e2e, gerçek Edge ile).
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    restoreMocks: true,
  },
});
