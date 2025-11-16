import { defineConfig } from 'vite'

export default defineConfig({
  root: 'static',
  server: {
    port: 5173,
    proxy: {
      '/generate': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/create_episode_batched': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/generated': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true
  }
})

