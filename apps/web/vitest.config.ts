import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

// Keep application devtools/server plugins out of the test runner.
export default defineConfig({
  resolve: { alias: { '#': fileURLToPath(new URL('./src', import.meta.url)) } },
  esbuild: { jsx: 'automatic' },
})
