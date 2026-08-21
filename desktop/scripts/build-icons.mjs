// Generates platform icon formats (.icns, .ico, .png) from build/icon.svg.
// Requires: rsvg-convert, iconutil (macOS), Python with Pillow.
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const buildDir = resolve(here, "..", "build");
const svgPath = resolve(buildDir, "icon.svg");
const iconsDir = resolve(buildDir, "icons");

if (!existsSync(svgPath)) {
  throw new Error(`Missing SVG source: ${svgPath}`);
}

rmSync(iconsDir, { recursive: true, force: true });
mkdirSync(iconsDir, { recursive: true });

const rsvg = (size, outPath) =>
  execFileSync("rsvg-convert", ["-w", String(size), "-h", String(size), svgPath, "-o", outPath]);

// --- macOS .icns ---
const iconsetDir = resolve(buildDir, "icon.iconset");
rmSync(iconsetDir, { recursive: true, force: true });
mkdirSync(iconsetDir, { recursive: true });

const icnsSpec = [
  [16, "icon_16x16.png"],
  [32, "icon_16x16@2x.png"],
  [32, "icon_32x32.png"],
  [64, "icon_32x32@2x.png"],
  [128, "icon_128x128.png"],
  [256, "icon_128x128@2x.png"],
  [256, "icon_256x256.png"],
  [512, "icon_256x256@2x.png"],
  [512, "icon_512x512.png"],
  [1024, "icon_512x512@2x.png"],
];

for (const [px, name] of icnsSpec) {
  rsvg(px, resolve(iconsetDir, name));
}

const icnsOut = resolve(iconsDir, "icon.icns");
execFileSync("iconutil", ["-c", "icns", iconsetDir, "-o", icnsOut]);
rmSync(iconsetDir, { recursive: true, force: true });
console.log("✓ icon.icns");

// --- PNGs (Linux + general use) ---
for (const px of [256, 512]) {
  rsvg(px, resolve(iconsDir, `icon-${px}.png`));
}
copyFileSync(resolve(iconsDir, "icon-512.png"), resolve(iconsDir, "icon.png"));
console.log("✓ icon.png");

// --- Windows .ico ---
const icoSizes = [16, 32, 48, 64, 128, 256];
for (const px of icoSizes) {
  rsvg(px, resolve(iconsDir, `_ico-${px}.png`));
}

// Build multi-res ICO via Pillow
const pyCode = [
  "from PIL import Image",
  "import os",
  `base = r"${iconsDir.replace(/\\/g, "\\\\")}"`,
  "sizes = [16, 32, 48, 64, 128, 256]",
  "imgs = [Image.open(os.path.join(base, f'_ico-{s}.png')) for s in sizes]",
  "imgs[0].save(os.path.join(base, 'icon.ico'), format='ICO', sizes=[(s, s) for s in sizes], append_images=imgs[1:])",
].join("\n");
execFileSync("python3", ["-c", pyCode]);
for (const px of icoSizes) {
  rmSync(resolve(iconsDir, `_ico-${px}.png`), { force: true });
}
console.log("✓ icon.ico");

console.log("Icons generated in", iconsDir);
console.log("Files:", readdirSync(iconsDir).join(", "));
