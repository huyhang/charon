/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

const CHARON_URL = process.env.CHARON_URL ?? "http://127.0.0.1:8080";
const FAKE_DS_URL = process.env.FAKE_DS_URL ?? "http://127.0.0.1:5000";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "apple-touch-icon.png"],
      manifest: {
        name: "Charon",
        short_name: "Charon",
        description: "Downloads, renamed and filed for you.",
        theme_color: "#0b0d14",
        background_color: "#0b0d14",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "pwa-192x192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512x512.png", sizes: "512x512", type: "image/png" },
          {
            src: "maskable-icon-512x512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      // The app shell works offline; API calls always go to the network.
      workbox: { navigateFallbackDenylist: [/^\/api\//] },
    }),
  ],
  build: {
    rolldownOptions: {
      output: {
        // Libraries change less often than the app, so they get their own cacheable chunks.
        codeSplitting: {
          groups: [
            {
              name: "react",
              test: /node_modules[\\/](react|react-dom|react-router|scheduler)[\\/]/,
            },
            { name: "vendor", test: /node_modules[\\/]/ },
          ],
        },
      },
    },
  },
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": CHARON_URL,
      // Dev-only simulator panel: steers the fake Download Station.
      "/_fake": { target: FAKE_DS_URL, rewrite: (path) => path.replace(/^\/_fake/, "") },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.test.{ts,tsx}",
        "src/test/**",
        "src/api/schema.d.ts",
        // The composition root: it only wires real implementations together, and the
        // Playwright suite (`make ui-e2e`) runs it for real.
        "src/main.tsx",
      ],
      reporter: [["text", { skipFull: true }], "text-summary", "html"],
      // `make ui-coverage` (and `make check`) fail below these.
      thresholds: { statements: 90, branches: 90, functions: 90, lines: 90 },
    },
  },
});
