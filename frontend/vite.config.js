var _a;
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// Builds into the backend's static dir so FastAPI serves the SPA in one
// Cloud Run container. During dev, proxy API + SSE to the backend.
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        proxy: {
            "/api": {
                target: "http://127.0.0.1:8090",
                changeOrigin: true,
            },
        },
    },
    build: {
        // Local builds drop straight into the backend's static dir; the Docker
        // frontend stage overrides this to a local 'dist' it can copy from.
        outDir: (_a = process.env.BUILD_OUT_DIR) !== null && _a !== void 0 ? _a : "../backend/app/static",
        emptyOutDir: true,
    },
});
