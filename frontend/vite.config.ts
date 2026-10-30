import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5273,
    proxy: {
      '/api': {
        target: process.env.LIGHTPANEL_UPSTREAM ?? 'http://127.0.0.1:9000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.spec.ts', 'src/**/*.spec.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,vue}'],
      exclude: ['src/main.ts', 'src/router/index.ts'],
    },
  },
})
