import { readFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const deployment = resolve(process.argv[2] ?? ".");
const release = await readFile(join(deployment, "cloudflare-worker-data.json"), "utf8");
const outfile = join(deployment, "worker.js");
await build({
  entryPoints: [fileURLToPath(new URL("worker.mjs", import.meta.url))],
  outfile,
  bundle: true,
  minify: true,
  platform: "browser",
  format: "esm",
  legalComments: "inline",
  plugins: [{
    name: "webgis-release",
    setup(builder) {
      builder.onResolve({ filter: /^webgis:release$/ }, (args) => ({ path: args.path, namespace: "webgis" }));
      builder.onLoad({ filter: /.*/, namespace: "webgis" }, () => ({ contents: release, loader: "json" }));
    },
  }],
});
await build({
  entryPoints: [fileURLToPath(new URL("pmtiles-client.mjs", import.meta.url))],
  outfile: join(deployment, "pmtiles-client.mjs"),
  bundle: true,
  minify: true,
  platform: "browser",
  format: "esm",
  legalComments: "inline",
});
console.log(outfile);
