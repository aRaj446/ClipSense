import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@openreel/core': path.resolve(__dirname, '../VideoEditor/openreel-video/packages/core/src/index.ts'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  // Tell Vite to compile @openreel/core source TS files (they're not pre-built)
  optimizeDeps: {
    include: ['mediabunny', 'uuid', 'immer'],
    exclude: ['@openreel/core'],
  },
  build: {
    rollupOptions: {
      // Ensure WASM files are handled as assets
      output: {
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith('.wasm')) {
            return 'assets/wasm/[name]-[hash][extname]'
          }
          return 'assets/[name]-[hash][extname]'
        },
      },
    },
  },
  assetsInclude: ['**/*.wasm'],
})
