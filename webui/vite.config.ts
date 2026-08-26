import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // 相对路径 base，使构建产物可挂在任意前缀（/custom-news/webui/）下
  base: "./",
  build: {
    outDir: "dist",
    assetsDir: "assets",
    chunkSizeWarningLimit: 6000,
  },
  server: {
    port: 5180,
    proxy: {
      "/custom-news/api": "http://127.0.0.1:8700",
    },
  },
});
