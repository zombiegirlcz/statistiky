/* gen_icons.js — vygeneruje icon-192.png a icon-512.png bez externích závislostí.
 * Kreslí: tmavé pozadí (zaoblený čtverec), tyrkysový prstenec, uvnitř "6" ze
 * segmentů (sedmisegmentovka). Čistý PNG encoder přes zlib (built-in).
 */
const fs = require('fs');
const zlib = require('zlib');

/* ---- CRC32 ---- */
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(buf) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length, 0);
  const t = Buffer.from(type, 'ascii');
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(Buffer.concat([t, data])), 0);
  return Buffer.concat([len, t, data, crc]);
}
function encodePNG(w, h, rgba) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  const stride = w * 4;
  const raw = Buffer.alloc((stride + 1) * h);
  for (let y = 0; y < h; y++) {
    raw[y * (stride + 1)] = 0; // filter none
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, y * stride + stride);
  }
  const idat = zlib.deflateSync(raw, { level: 9 });
  return Buffer.concat([sig, chunk('IHDR', ihdr), chunk('IDAT', idat), chunk('IEND', Buffer.alloc(0))]);
}

/* ---- kreslení ---- */
function draw(size) {
  const px = Buffer.alloc(size * size * 4);
  const cx = size / 2, cy = size / 2;
  const R = size * 0.50;      // poloměr pozadí (zaoblení)
  const rOut = size * 0.315;  // vnější prstenec
  const rIn = size * 0.235;   // vnitřní (díra)

  const bg1 = [0x0b, 0x12, 0x20];       // tmavá
  const bg2 = [0x16, 0x23, 0x3f];       // světlejší střed
  const cy1 = [0x22, 0xd3, 0xee];       // tyrkys
  const fg = [0xe8, 0xee, 0xfc];        // text

  // segmenty "6" v obdélníkové mřížce (7-seg)
  // souřadnice v poměru k size
  const s = size;
  const segs = [
    // [x, y, w, h]  (relativně k velikosti, levý horní roh)
    [0.435, 0.335, 0.130, 0.028], // top
    [0.418, 0.345, 0.026, 0.115], // upper-left
    [0.418, 0.470, 0.026, 0.115], // lower-left
    [0.435, 0.578, 0.130, 0.028], // bottom
    [0.556, 0.470, 0.026, 0.115], // lower-right
    [0.435, 0.462, 0.130, 0.028], // middle
  ].map(([x, y, w, h]) => [x * s, y * s, w * s, h * s]);

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dx = x + 0.5 - cx, dy = y + 0.5 - cy;
      const d = Math.sqrt(dx * dx + dy * dy);
      // zaoblený čtverec: maska dle Chebyshev + rohy
      const half = size / 2 - size * 0.02;
      const cornerR = size * 0.22;
      let inside = true;
      const ax = Math.abs(dx), ay = Math.abs(dy);
      if (ax > half || ay > half) inside = false;
      else {
        const qx = ax - (half - cornerR), qy = ay - (half - cornerR);
        if (qx > 0 && qy > 0) {
          if (Math.sqrt(qx * qx + qy * qy) > cornerR) inside = false;
        }
      }
      let r = 0, g = 0, b = 0, a = 0;
      if (inside) {
        // pozadí s jemným gradientem ke středu
        const t = Math.min(1, d / half);
        r = Math.round(bg1[0] + (bg2[0] - bg1[0]) * (1 - t));
        g = Math.round(bg1[1] + (bg2[1] - bg1[1]) * (1 - t));
        b = Math.round(bg1[2] + (bg2[2] - bg1[2]) * (1 - t));
        a = 255;
        // prstenec
        if (d <= rOut && d >= rIn) { r = cy1[0]; g = cy1[1]; b = cy1[2]; }
        // "6" ze segmentů
        for (const [sx, sy, sw, sh] of segs) {
          if (x >= sx && x < sx + sw && y >= sy && y < sy + sh) { r = fg[0]; g = fg[1]; b = fg[2]; break; }
        }
      }
      const o = (y * size + x) * 4;
      px[o] = r; px[o + 1] = g; px[o + 2] = b; px[o + 3] = a;
    }
  }
  return px;
}

for (const size of [192, 512]) {
  const png = encodePNG(size, size, draw(size));
  fs.writeFileSync(`icon-${size}.png`, png);
  console.log(`icon-${size}.png: ${png.length} B`);
}
console.log('hotovo');