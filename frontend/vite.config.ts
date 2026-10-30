import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// build ออกมาเป็นไฟล์ static กองเดียว แล้วให้ Flask เสิร์ฟจาก frontend/dist
// ตอน dev (npm run dev) จะ proxy /api ไปหา Flask ที่พอร์ต 5000 ให้เอง
// จึงเป็น same-origin ทั้งตอน dev และตอนใช้จริง — ไม่ต้องยุ่งกับ CORS เลย
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:5000',
    },
  },
  build: {
    outDir: 'dist',
    // ไม่เอา sourcemap ขึ้น production — ไฟล์ใหญ่ และเปิดเผยโครงสร้างโค้ดฟรี ๆ
    sourcemap: false,
    chunkSizeWarningLimit: 700,
  },
})
