import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// На сервере КБТУ проект отдаётся не с корня домена, а по пути вида
// esg.kbtu.kz/air-quality. Базовый путь задаётся переменной сборки, чтобы
// префикс не был зашит в код: локально это «/», на сервере — «/air-quality/».
const base = process.env.VITE_BASE_PATH ?? '/'

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // В режиме разработки Vite сам проксирует API, поэтому фронтенд обращается
    // по относительному пути так же, как и в контейнере за nginx.
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_API ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Recharts и Leaflet весят больше самого приложения и меняются редко —
        // выносим их в отдельные чанки, чтобы браузер кэшировал их между релизами.
        manualChunks: {
          charts: ['recharts'],
          maps: ['leaflet', 'react-leaflet'],
        },
      },
    },
  },
})
