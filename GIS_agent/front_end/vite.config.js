import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { HttpsProxyAgent } from 'https-proxy-agent'
import process from 'node:process'

const proxyUrl = process.env.https_proxy || process.env.HTTPS_PROXY || process.env.http_proxy || process.env.HTTP_PROXY

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/basemap/': {
        target: 'https://tiles.openfreemap.org',
        changeOrigin: true,
        agent: proxyUrl ? new HttpsProxyAgent(proxyUrl) : undefined,
        rewrite: (path) => path.replace(/^\/basemap\//, '/'),
        proxyTimeout: 15000,
      },
    },
  },
})
