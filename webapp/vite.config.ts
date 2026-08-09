import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 🔥 Tailwind подключаем через плагин Vite
export default defineConfig({
  plugins: [react(), tailwindcss()],
})
