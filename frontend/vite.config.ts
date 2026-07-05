import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (id.includes("echarts")) return "vendor-echarts";
          if (id.includes("@tanstack/react-query")) return "vendor-query";
          if (id.includes("lucide-react")) return "vendor-icons";
          if (id.includes("react")) return "vendor-react";
        }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000"
    }
  }
});
