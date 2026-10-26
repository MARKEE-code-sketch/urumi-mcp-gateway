import { defineConfig } from "@playwright/test";
const fixturePython =
  process.env.M8_PYTHON ?? "../.tools/m6/venv/Scripts/python.exe";
export default defineConfig({
  testDir: "tests/browser",
  timeout: 30000,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.M8_BASE_URL ?? "http://127.0.0.1:18080",
    trace: "off",
    video: "off",
    screenshot: "off",
  },
  webServer: process.env.M8_BASE_URL
    ? undefined
    : {
        command: '"' + fixturePython + '" ../scripts/m8/fixture_server.py',
        url: "http://127.0.0.1:18080/readyz",
        reuseExistingServer: false,
        timeout: 20000,
      },
});
