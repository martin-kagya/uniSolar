import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from "path"

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'deck.gl': [
            '@deck.gl/core',
            '@deck.gl/layers',
            '@deck.gl/google-maps',
            '@deck.gl/mesh-layers',
          ],
          'recharts': ['recharts'],
        },
      },
    },
  },
  server: {
    proxy: {
      '/simulate': 'http://127.0.0.1:8000',
      '/modules': 'http://127.0.0.1:8000',
      '/inverters': 'http://127.0.0.1:8000',
      '/size-system': 'http://127.0.0.1:8000',
      '/designs': 'http://127.0.0.1:8000',
    }
  }
})
