// Regenerates the committed icon files from the SVG sources in scripts/icons.
// Run from frontend/: npm run icons (needs `npm ci` first; sharp comes with Next).
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..", "src", "app");
const ball16 = readFileSync(join(here, "icons", "ball-16.svg"));
const ball32 = readFileSync(join(here, "icons", "ball-32.svg"));
// iOS applies its own corner mask, so the touch icon is a flat square.
const flat32 = Buffer.from(ball32.toString("utf8").replace('rx="14"', 'rx="0"'));

const png = (svg, px) => sharp(svg, { density: 384 }).resize(px, px).png().toBuffer();

function ico(frames) {
  const head = Buffer.alloc(6);
  head.writeUInt16LE(0, 0);
  head.writeUInt16LE(1, 2);
  head.writeUInt16LE(frames.length, 4);
  let offset = 6 + 16 * frames.length;
  const dir = frames.map(({ px, data }) => {
    const e = Buffer.alloc(16);
    e.writeUInt8(px >= 256 ? 0 : px, 0);
    e.writeUInt8(px >= 256 ? 0 : px, 1);
    e.writeUInt16LE(1, 4);
    e.writeUInt16LE(32, 6);
    e.writeUInt32LE(data.length, 8);
    e.writeUInt32LE(offset, 12);
    offset += data.length;
    return e;
  });
  return Buffer.concat([head, ...dir, ...frames.map((f) => f.data)]);
}

writeFileSync(
  join(app, "favicon.ico"),
  ico([
    { px: 16, data: await png(ball16, 16) },
    { px: 32, data: await png(ball32, 32) },
    { px: 48, data: await png(ball32, 48) },
  ]),
);
writeFileSync(join(app, "icon.svg"), ball32);
writeFileSync(join(app, "apple-icon.png"), await png(flat32, 180));
console.log("wrote favicon.ico, icon.svg and apple-icon.png in src/app");
