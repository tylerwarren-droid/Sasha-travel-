#!/usr/bin/env node
// ── Sasha 348 · EVERY REQUEST THROUGH THE ONE CLIENT (lib/request.ts) ──────────────────────────────────────────────────────────
//
//   node scripts/one-client.mjs           list every direct request left in the frontend (what the prebuild refuses)
//   node scripts/one-client.mjs --write   move each onto the one client — mechanical, each replacement has the signature of what it
//                                         replaces. Also Stage B after a CTO drop (CLAUDE.md): his files arrive with fetch( / axios.
//
// Read from TypeScript's syntax tree (never a regex):
//   fetch(…) · window.fetch(…) · globalThis.fetch(…) · self.fetch(…)   → reach(…)
//   new EventSource(…)                                                  → events(…)
//   new WebSocket(…)                                                    → socket(…)
//   navigator.sendBeacon(…) / navigator.sendBeacon?.(…)                 → beacon(…)
//   new XMLHttpRequest()                                                → refused: no replacement — use reach / request
//   import axios from 'axios'                                           → import { axios } from '@/lib/request'
import ts from "typescript";
import { readFileSync, readdirSync, writeFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join, relative } from "node:path";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
export const CLIENT = "lib/request.ts";
const SKIP = new Set(["node_modules", ".next", ".vercel", "public", "types"]);

/** every source file of the frontend (app, lib, the middleware, the scripts) — the one client itself aside, as it IS the network */
export function sourceFiles(dir = ROOT) {
  const out = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (SKIP.has(e.name) || e.name.startsWith(".")) continue;
    const p = join(dir, e.name);
    if (e.isDirectory()) out.push(...sourceFiles(p));
    else if (/\.(tsx?|mjs|js)$/.test(e.name) && !/\.d\.ts$/.test(e.name)) {
      const rel = relative(ROOT, p).split("\\").join("/");
      if (rel !== CLIENT) out.push(rel);
    }
  }
  return out.sort();
}

const isNet = (e) => ts.isIdentifier(e) && ["window", "globalThis", "self"].includes(e.text);

/** the direct requests in one file → [{ start, end, text (the replacement, or null when there is none), what, line }] */
export function directRequests(src, file = "x.tsx") {
  const kind = /\.tsx$/.test(file) ? ts.ScriptKind.TSX : /\.(mjs|js)$/.test(file) ? ts.ScriptKind.JS : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, kind);
  const out = [];
  const line = (n) => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
  const visit = (n) => {
    if (ts.isCallExpression(n)) {
      const c = n.expression;
      const args = n.arguments.map((a) => a.getText(sf)).join(", ");
      if (ts.isIdentifier(c) && c.text === "fetch") out.push({ start: c.getStart(sf), end: c.end, text: "reach", need: "reach", what: "fetch(", line: line(n) });
      else if (ts.isPropertyAccessExpression(c) && c.name.text === "fetch" && isNet(c.expression))
        out.push({ start: c.getStart(sf), end: c.end, text: "reach", need: "reach", what: `${c.expression.getText(sf)}.fetch(`, line: line(n) });
      else if (ts.isPropertyAccessExpression(c) && c.name.text === "sendBeacon")
        out.push({ start: n.getStart(sf), end: n.end, text: `beacon(${args})`, need: "beacon", what: "sendBeacon(", line: line(n) });
    }
    if (ts.isNewExpression(n) && ts.isIdentifier(n.expression)) {
      const args = (n.arguments || []).map((a) => a.getText(sf)).join(", ");
      const name = n.expression.text;
      if (name === "EventSource") out.push({ start: n.getStart(sf), end: n.end, text: `events(${args})`, need: "events", what: "new EventSource(", line: line(n) });
      if (name === "WebSocket") out.push({ start: n.getStart(sf), end: n.end, text: `socket(${args})`, need: "socket", what: "new WebSocket(", line: line(n) });
      if (name === "XMLHttpRequest") out.push({ start: n.getStart(sf), end: n.end, text: null, what: "new XMLHttpRequest(", line: line(n) });
    }
    if (ts.isImportDeclaration(n) && ts.isStringLiteral(n.moduleSpecifier) && n.moduleSpecifier.text === "axios")
      out.push({ start: n.getStart(sf), end: n.end, text: "import { axios } from '@/lib/request'   // Sasha 348 · the ONE request client", need: null, what: "axios", line: line(n) });
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return out;
}

/** a file moved onto the one client (and its import added, or merged into the one it has) */
export function moved(src, file) {
  const found = directRequests(src, file);
  if (!found.length) return src;
  if (found.some((f) => f.text === null)) throw new Error(`${file}: an XMLHttpRequest has no mechanical replacement — rewrite it with reach / request`);
  let out = src;
  for (const f of [...found].sort((a, b) => b.start - a.start)) out = out.slice(0, f.start) + f.text + out.slice(f.end);
  const need = [...new Set(found.map((f) => f.need).filter(Boolean))];
  if (!need.length) return out;
  const has = out.match(/^import \{([^}]*)\} from ['"]@\/lib\/request['"].*$/m);
  if (has) {
    const names = [...new Set([...has[1].split(",").map((s) => s.trim()).filter(Boolean), ...need])].sort();
    return out.replace(has[0], `import { ${names.join(", ")} } from '@/lib/request'   // Sasha 348 · the ONE request client`);
  }
  const imps = [...out.matchAll(/^import [\s\S]*?from ['"][^'"]+['"];?[^\n]*\n/gm)];
  const directive = out.match(/^\s*(['"])use (client|server)\1;?[^\n]*\n/);
  const at = imps.length ? imps[imps.length - 1].index + imps[imps.length - 1][0].length : directive ? directive[0].length : 0;
  return out.slice(0, at) + `import { ${need.sort().join(", ")} } from '@/lib/request'   // Sasha 348 · the ONE request client\n` + out.slice(at);
}

function main() {
  const write = process.argv.includes("--write");
  let left = 0, files = 0;
  for (const rel of sourceFiles()) {
    const p = join(ROOT, rel);
    const src = readFileSync(p, "utf8");
    const found = directRequests(src, rel);
    if (!found.length) continue;
    files++;
    if (write) { writeFileSync(p, moved(src, rel)); console.log(`${rel}: ${found.length} moved onto the one client`); }
    else for (const f of found) { left++; console.log(`${rel}:${f.line}  ${f.what}`); }
  }
  console.log(write ? `one-client: ${files} file(s) moved` : `one-client: ${left} direct request(s) in ${files} file(s)`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main();
