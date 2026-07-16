import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "vite";

const projectRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const outputDirectory = join(projectRoot, "dist");
const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".svg": "image/svg+xml",
};

await build({ configFile: join(projectRoot, "vite.config.ts") });

const server = createServer(async (request, response) => {
  const requestPath = new URL(request.url ?? "/", "http://127.0.0.1").pathname;
  const relativePath = requestPath === "/" ? "index.html" : requestPath.slice(1);
  const candidate = normalize(join(outputDirectory, relativePath));
  const safePath = candidate.startsWith(outputDirectory) && extname(candidate) ? candidate : join(outputDirectory, "index.html");

  try {
    response.writeHead(200, { "content-type": contentTypes[extname(safePath)] ?? "application/octet-stream" });
    response.end(await readFile(safePath));
  } catch {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("Not found");
  }
});

server.listen(4173, "127.0.0.1");

let closing = false;
function closeServer() {
  if (closing) return;
  closing = true;
  server.close(() => process.exit(0));
}

process.once("SIGINT", closeServer);
process.once("SIGTERM", closeServer);
