var _a;
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
var proxyTarget = (_a = process.env.VITE_DEV_PROXY_TARGET) !== null && _a !== void 0 ? _a : "http://localhost:8000";
export default defineConfig({
    plugins: [react()],
    server: {
        proxy: {
            "/api": proxyTarget
        }
    }
});
