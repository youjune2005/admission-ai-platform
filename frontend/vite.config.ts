import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // 0.0.0.0 — 터널/LAN 접근용
    port: 5173,
    strictPort: true,
    proxy: {
      // 같은 출처로 API를 붙여 공개 URL 1개만으로 공유 가능
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
