import { readFileSync } from "node:fs";
import { join } from "node:path";
import sharp from "sharp";

const app = join(__dirname, "..", "..", "app");
const sources = join(__dirname, "..", "..", "..", "scripts", "icons");
const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function icoFrames(file: Buffer) {
  const count = file.readUInt16LE(4);
  return Array.from({ length: count }, (_, i) => {
    const e = 6 + i * 16;
    const w = file.readUInt8(e) || 256;
    const size = file.readUInt32LE(e + 8);
    const offset = file.readUInt32LE(e + 12);
    return { w, isPng: file.subarray(offset, offset + 8).equals(PNG), size };
  });
}

describe("brand assets", () => {
  test("favicon.ico holds PNG frames at 16, 32 and 48 only (not the default 256 px art)", () => {
    const frames = icoFrames(readFileSync(join(app, "favicon.ico")));
    expect(frames.map((f) => f.w)).toEqual([16, 32, 48]);
    expect(frames.every((f) => f.isPng)).toBe(true);
  });

  test("icon.svg is the 32 px source art", () => {
    expect(readFileSync(join(app, "icon.svg"), "utf8")).toBe(
      readFileSync(join(sources, "ball-32.svg"), "utf8"),
    );
  });

  test("apple-icon.png is a 180x180 PNG", () => {
    const png = readFileSync(join(app, "apple-icon.png"));
    expect(png.subarray(0, 8).equals(PNG)).toBe(true);
    expect(png.readUInt32BE(16)).toBe(180);
    expect(png.readUInt32BE(20)).toBe(180);
  });

  test("apple-icon.png corner is opaque (full-bleed square)", async () => {
    const { data } = await sharp(join(app, "apple-icon.png"))
      .raw()
      .ensureAlpha()
      .toBuffer({ resolveWithObject: true });
    expect(data[3]).toBe(255);
  });

  test("both sources use the brand palette", () => {
    for (const name of ["ball-16.svg", "ball-32.svg"]) {
      const svg = readFileSync(join(sources, name), "utf8");
      expect(svg).toContain("#1b4332");
      expect(svg).toContain("#e9b84d");
    }
  });
});
