import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// dev 时把 /api 代理到 FastAPI,前端代码里只写相对路径,免去跨域问题
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
