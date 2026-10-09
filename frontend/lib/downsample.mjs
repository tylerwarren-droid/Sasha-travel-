// Sasha 215 (d) · THE MIC AT 16 kHz — Deepgram's speech models work at 16 kHz; the browser captures at 44.1/48 kHz. Sending
// 48 kHz linear16 was ~0.77 Mbps up (~58 MB per 10 minutes); at 16 kHz it's a third (~19 MB). A streaming box-filter
// decimator: each output sample is the mean of the input samples it covers (a simple low-pass against aliasing), with the
// fractional position carried between the worklet's 128-sample frames so nothing is dropped or doubled at the joins.
export const TARGET_RATE = 16000

export function makeDownsampler(inRate, outRate = TARGET_RATE) {
  if (!inRate || inRate <= outRate) return (x) => x
  const ratio = inRate / outRate
  let carry = new Float32Array(0)
  let pos = 0
  return (input) => {
    const buf = new Float32Array(carry.length + input.length)
    buf.set(carry)
    buf.set(input, carry.length)
    const out = []
    while (pos + ratio <= buf.length) {
      const a = Math.floor(pos), b = Math.max(a + 1, Math.floor(pos + ratio))
      let s = 0
      for (let i = a; i < b; i++) s += buf[i]
      out.push(s / (b - a))
      pos += ratio
    }
    const keep = Math.floor(pos)
    carry = buf.slice(keep)
    pos -= keep
    return Float32Array.from(out)
  }
}

/** The rate Deepgram is told: 16 kHz when the capture is faster, else the capture's own. */
export const sendRate = (captureRate) => (captureRate > TARGET_RATE ? TARGET_RATE : captureRate)
