import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  // Not VITE_-prefixed on purpose: these are for this dev server only and never reach the browser.
  const env = loadEnv(mode, process.cwd(), "");
  // Where the backend lives, from this server's point of view (same machine by default; a Docker
  // container reaches it by service name, e.g. http://backend:8000).
  const backendUrl = env.BACKEND_URL || "http://127.0.0.1:8000";
  // Extra names this server may be opened by (e.g. a company domain), comma separated. Localhost, every
  // IP address and this Mac's own .local name are always allowed.
  const extraHosts = (env.ALLOWED_HOSTS || "").split(",").map((h) => h.trim()).filter(Boolean);

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      host: true,
      port: 5173,
      allowedHosts: [".local", ...extraHosts],
      // The browser talks only to this server and it forwards /api to the backend, so the app works from
      // any address (localhost, a network address, a machine name, another device) with no cross-origin
      // setup and without exposing the backend port itself.
      proxy: {
        "/api": { target: backendUrl },
      },
    },
  };
});
