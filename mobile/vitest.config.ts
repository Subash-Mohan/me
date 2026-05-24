import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

/**
 * Pure-logic test runner for the mobile streaming pipeline. We deliberately
 * stay off React Native — every file under test (`sse-parser`, `packet-router`,
 * `reducer`, `adapter`) is RN-free, so Node + Vitest is all we need and tests
 * run in milliseconds.
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./", import.meta.url)),
    },
  },
  test: {
    include: ["lib/**/__tests__/**/*.test.ts"],
    environment: "node",
    reporters: "default",
  },
});
