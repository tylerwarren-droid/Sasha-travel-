/**
 * Sasha 259 · A CALM PHONE SCREEN (Tyler, row 884): nothing on the S2 shell overlaps anything — not her face on the send button, not
 * the moon on "Voice off". The ONE rule, pure (tested in scripts/calm-shell-257.test.mjs) and used by scripts/phone-overlap.mjs,
 * which measures the real page at 390×844.
 * @param {{ name: string, x: number, y: number, w: number, h: number }[]} boxes  every visible control / text on screen
 * @param {number} [slack]  px of touching allowed (borders, rounding)
 * @returns {[string, string][]} each pair that overlaps
 */
export function overlaps(boxes, slack = 1) {
  const out = []
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j]
      const ix = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
      const iy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
      if (ix > slack && iy > slack) out.push([a.name, b.name])
    }
  }
  return out
}
