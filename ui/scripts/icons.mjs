// Renders the PWA icons from public/favicon.svg. Run after changing the logo: npm run icons
import sharp from "sharp";

const SOURCE = "public/favicon.svg";
const BACKGROUND = "#0b0d14";

const icon = (size) => sharp(SOURCE, { density: 1200 }).resize(size, size);

// Maskable and Apple icons get a solid background and padding, since platforms crop them.
async function padded(size, scale, file) {
  const inner = Math.round(size * scale);
  const logo = await icon(inner).png().toBuffer();
  await sharp({ create: { width: size, height: size, channels: 4, background: BACKGROUND } })
    .composite([{ input: logo, gravity: "center" }])
    .png()
    .toFile(file);
}

await icon(192).png().toFile("public/pwa-192x192.png");
await icon(512).png().toFile("public/pwa-512x512.png");
await padded(512, 0.7, "public/maskable-icon-512x512.png");
await padded(180, 0.8, "public/apple-touch-icon.png");
console.log("icons written to public/");
