import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API runs on :3001; the dev server proxies /api so the browser stays
// same-origin and page images stream through without CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:3001", changeOrigin: true },
    },
  },
});
