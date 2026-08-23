import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(() => {
  const apiBase = process.env.VITE_STUDIO_API_BASE ?? 'http://127.0.0.1:8765';
  const devToken = process.env.MINIMAXH3_STUDIO_DEV_TOKEN;

  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': {
          target: apiBase,
          changeOrigin: false,
          headers: devToken ? { 'X-Studio-Token': devToken } : undefined,
        },
      },
    },
    preview: {
      host: '127.0.0.1',
      port: 4173,
      strictPort: true,
    },
  };
});
