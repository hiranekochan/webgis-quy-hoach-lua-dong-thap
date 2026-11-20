import { PMTiles, Protocol } from "pmtiles";

const chunks = new Map();
const cacheLimit = 64;

function readChunk(url, size) {
  let pending = chunks.get(url);
  if (pending) {
    chunks.delete(url);
  } else {
    pending = fetch(url).then(async (response) => {
      if (!response.ok) throw new Error(`PMTiles HTTP ${response.status} · ${url}`);
      const bytes = new Uint8Array(await response.arrayBuffer());
      if (bytes.length !== size) throw new Error(`PMTiles kích thước không khớp · ${url}`);
      return bytes;
    }).catch((error) => {
      if (chunks.get(url) === pending) chunks.delete(url);
      throw error;
    });
  }
  chunks.set(url, pending);
  if (chunks.size > cacheLimit) chunks.delete(chunks.keys().next().value);
  return pending;
}

class StaticArchiveSource {
  constructor(url, size, chunkSize) {
    this.url = url;
    this.size = size;
    this.chunkSize = chunkSize;
  }

  getKey() {
    return this.url;
  }

  async getBytes(offset, length, signal) {
    signal?.throwIfAborted();
    const end = Math.min(this.size, offset + length);
    if (end <= offset) throw new Error(`PMTiles khoảng đọc không hợp lệ · ${this.url}`);
    const first = Math.floor(offset / this.chunkSize);
    const last = Math.floor((end - 1) / this.chunkSize);
    const reads = [];
    for (let chunk = first; chunk <= last; chunk++) {
      const start = chunk * this.chunkSize;
      reads.push(readChunk(`${this.url}/${chunk}.bin`, Math.min(this.chunkSize, this.size - start)));
    }
    const parts = await Promise.all(reads);
    signal?.throwIfAborted();
    const data = new Uint8Array(end - offset);
    let written = 0;
    for (const [index, part] of parts.entries()) {
      const start = index === 0 ? offset % this.chunkSize : 0;
      const slice = part.subarray(start, start + data.length - written);
      data.set(slice, written);
      written += slice.length;
    }
    return { data: data.buffer };
  }
}

export function registerTileArchives(maplibre, layers, origin) {
  const protocol = new Protocol();
  const urls = new Map();
  for (const { id, tileArchive } of layers) {
    if (!tileArchive) continue;
    const { path, size, chunkSize } = tileArchive;
    const url = new URL(path, origin).href;
    protocol.add(new PMTiles(new StaticArchiveSource(url, size, chunkSize)));
    urls.set(id, `pmtiles://${url}`);
  }
  maplibre.addProtocol("pmtiles", protocol.tile);
  return urls;
}
