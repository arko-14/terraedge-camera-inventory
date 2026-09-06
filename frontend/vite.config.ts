import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // In development the API is proxied under the same origin as the app, so
    // the session cookie is a plain first-party SameSite=Lax cookie and there
    // is no CORS involved. In production VITE_API_BASE_URL points at the
    // deployed API instead (see src/lib/api.ts).
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
})
