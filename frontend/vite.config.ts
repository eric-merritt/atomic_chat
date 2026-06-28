import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    allowedHosts: ['agent.eric-merritt.com'],
    port: 6612,
    // Never auto-migrate to the next free port — fail loudly on a conflict
    // instead of silently stealing another service's port.
    strictPort: true,
    proxy: {
      '/api': 'http://localhost:8297',
      '/static': 'http://localhost:8297',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test-setup.ts',
    passWithNoTests: true,
  },
})
