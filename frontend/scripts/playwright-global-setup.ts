import { fileURLToPath } from "node:url";

import { createServer } from "vite";

import { prepareRealBackend, realBackendApiBaseUrl } from "./playwright-real-backend";

const projectRoot = fileURLToPath(new URL("..", import.meta.url));
const configFile = fileURLToPath(new URL("../vite.config.ts", import.meta.url));

export default async function globalSetup() {
  const backend = await prepareRealBackend();
  process.env.VITE_API_BASE_URL = realBackendApiBaseUrl;
  const server = await createServer({
    configFile,
    root: projectRoot,
    server: {
      host: "127.0.0.1",
      port: 4173,
      strictPort: true,
    },
  });

  await server.listen();

  return async () => {
    await server.close();
    await backend.stop();
  };
}
