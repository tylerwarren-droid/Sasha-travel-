// Cross-runtime check: AD's lib/agapi/portable/canonical.js against the Python-generated canonical.json vectors.
// Usage (from vectors/): node reference/check_canonical_js.mjs <path to canonical.js> canonical.json
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const [canonPath, vecPath] = process.argv.slice(2);
const { canonicalJson } = await import(pathToFileURL(canonPath).href);
const KEY = /^[a-z0-9_]+$/;
function strict(v) { // the Part 1 §4.1 refusals that AD's canonical.js does not (yet) apply
  if (typeof v === "number") { if (!Number.isInteger(v)) throw new Error("float"); if (Math.abs(v) > 9007199254740991) throw new Error("integer out of range"); }
  else if (typeof v === "string") { if (/[\uD800-\uDFFF]/.test(v.replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g, ""))) throw new Error("lone surrogate"); }
  else if (Array.isArray(v)) v.forEach(strict);
  else if (v && typeof v === "object") for (const [k, x] of Object.entries(v)) { if (!KEY.test(k)) throw new Error("key charset"); strict(x); }
}
const cases = JSON.parse(readFileSync(vecPath, "utf8")).cases;
let pass = 0, fail = 0;
for (const c of cases) {
  if (c.expect === "refused") {
    const v = JSON.parse(c.input_json);
    let adRefused = true; try { canonicalJson(v); adRefused = false; } catch {}
    let strictRefused = true; try { strict(v); strictRefused = false; } catch {}
    console.log(`${c.id}: AD canonical.js ${adRefused ? "refuses" : "ACCEPTS (gap)"} · with §4.1 checks ${strictRefused ? "refuses ✓" : "ACCEPTS ✗"}`);
    strictRefused ? pass++ : fail++;
    continue;
  }
  strict(c.input);
  const out = canonicalJson(c.input);
  const sha = "sha256:" + createHash("sha256").update(out, "utf8").digest("hex");
  const ok = out === c.canonical && sha === c.sha256;
  console.log(`${c.id}: ${ok ? "identical bytes ✓" : "DIFFERENT ✗\n  js: " + out + "\n  py: " + c.canonical}`);
  ok ? pass++ : fail++;
}
console.log(`\n${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
