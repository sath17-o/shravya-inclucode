import { fileURLToPath } from "node:url";

import { createServer } from "vite";

const projectRoot = fileURLToPath(new URL("..", import.meta.url));
const configFile = fileURLToPath(new URL("../vite.config.ts", import.meta.url));

export default async function globalSetup() {
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
  };
}
