import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
import path from "path";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw-custom.ts",
      registerType: "autoUpdate",
      injectRegister: "auto",
      devOptions: {
        enabled: true,  // 개발 모드에서 서비스 워커 활성화
        type: "module",
      },
      includeAssets: ["favicon.ico", "apple-touch-icon.png"],
      manifest: {
        name: "SENTIO - Sense · Protect · Care",
        short_name: "SENTIO",
        description: "고령자 낙상 감지 및 AI 안전 모니터링 시스템",
        theme_color: "#0f172a",
        background_color: "#0f172a",
        display: "standalone",
        scope: "/",
        start_url: "/",
        icons: [
          {
            src: "icon-192x192.png",
            sizes: "192x192",
            type: "image/png",
          },
          {
            src: "icon-512x512.png",
            sizes: "512x512",
            type: "image/png",
          },
          {
            src: "icon-512x512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any maskable",
          },
        ],
      },
      injectManifest: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg,woff2}"],
        maximumFileSizeToCacheInBytes: 3 * 1024 * 1024, // 3MB
      },
    }),
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          ui: ["lucide-react", "i18next", "react-i18next"],
          charts: ["recharts"],
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8001",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8001",
        ws: true,
      },
      "/webrtc": {
        target: "http://localhost:1984",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/webrtc/, ""),
        ws: true,
      },
    },
  },
});
