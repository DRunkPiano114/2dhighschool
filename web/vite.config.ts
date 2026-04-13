import { defineConfig, createLogger } from 'vite'
import react from '@vitejs/plugin-react'

// TopBar pings /api/health on load to decide whether to grey out 角色扮演.
// When `uv run api` isn't running, those pings are ECONNREFUSED — the
// expected signal, not a bug. Vite's default logger prints a full stack
// per failed proxy request, which drowns real errors. Wrap the logger to
// swallow that specific line (and only that line).
const logger = createLogger()
const origError = logger.error.bind(logger)
logger.error = (msg, opts) => {
  if (typeof msg === 'string' && msg.includes('http proxy error') && msg.includes('ECONNREFUSED')) return
  origError(msg, opts)
}

export default defineConfig({
  customLogger: logger,
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
