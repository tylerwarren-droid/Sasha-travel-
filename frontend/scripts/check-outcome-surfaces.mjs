#!/usr/bin/env node
// ── P807mt · OUTCOME SURFACES MAY NOT GO SILENT ─────────────────────────────────────────────────────────
//
//   node scripts/check-outcome-surfaces.mjs          (also runs as `prebuild`, so every `npm run build` —
//                                                     Stage C locally and Vercel's build — runs it first)
//
// An OUTCOME SURFACE is a page where a person acts and must learn what happened. On one, every action ends in
// a visible state, and "nothing happened" may only be said when nothing was attempted. The booking page broke
// that four ways in its first day (docs/P807mt-silent-surfaces.md, in the Applied Diligence repository), while
// a comment on the same page stated the rule. A rule that lives in a comment is applied where its author is
// looking; this file is the rule applied everywhere it is declared.
//
// Each check is a RELATION, never a banned token (a token is present in correct and incorrect code alike):
//   S1  disabled AND unexplained — a raw `disabled=` on a surface. Buttons are GatedButton, which cannot be
//       disabled without rendering what it waits for, and which has no `disabled` prop to misuse.
//   S2  rejected AND unobserved — a promise launched with `void f(…)`, or a `.then(` with no `.catch(`.
//   S3  empty AND "never attempted" — a "Nothing … yet" rendered from `.length === 0` rather than from an
//       explicit not-yet-started state.
//
// ⚠ The checks run on FIXTURES first, every time: each defect must be caught and the clean form must pass.
// A guard that has only ever been seen passing has not been shown to check anything.

import { readFileSync, readdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import ts from "typescript";
import { sourceFiles, directRequests } from "./one-client.mjs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const ROOT = fileURLToPath(new URL("..", import.meta.url));

/** Pages where a person acts and must learn what happened. Add a page here when it becomes one. */
export const OUTCOME_SURFACES = ["app/booking-helper/page.tsx", "app/booking-helper/PhoneCall.tsx", "app/booking-helper/Ladder.tsx", "app/booking-helper/FounderGate.tsx", "app/components/workspace/SashaReservations.tsx", "app/components/ChatBooking.tsx", "app/components/ChatBookingCall.tsx", "app/booking-helper/FormSend.tsx", "app/components/ChatBookingLink.tsx", "app/components/ChatCancel.tsx"];
// CR 1 · CampusMe and relocation pages (their own line, so the Sasha tab's list above never conflicts)
OUTCOME_SURFACES.push("app/campus-handover/[id]/page.tsx", "app/campus-handover/[id]/CopyAnswer.tsx", "app/relocation-file/[id]/page.tsx", "app/health-handover/[id]/page.tsx", "app/officer/[id]/page.tsx", "app/officer/[id]/ReturnButton.tsx");
// CR 63 · the Keep (its own line, so the Sasha tab's list above never conflicts)
OUTCOME_SURFACES.push("app/keep/page.tsx");
// Sasha 346 · the group pages (/group: Tyler's Swap and Book all were greyed and said nothing, 5 Nov) — and EVERY page that acts through
// bookingReq is an outcome surface whether or not someone remembered to list it (actingPages() below finds them; an unlisted one fails)
OUTCOME_SURFACES.push("app/group/page.tsx", "app/vault/page.tsx");
// Sasha 358 · THE GROUP VIEW: one component over the group engine (/group now; S2's and /next's group tab next)
OUTCOME_SURFACES.push("app/components/group/GroupView.tsx");
/** The one component allowed to set `disabled=` — because it derives it from rendered needs. */
export const GATED_BUTTON = "app/booking-helper/GatedButton.tsx";

// Sasha 347 · comments found by TypeScript's own parser, never a regex: a regex took the "/*" inside accept="image/*" for a comment's start
// and erased real code up to the next "*/" — S2's 📎 button (`disabled={busy || working}`) was invisible to this check. Each comment is
// blanked to spaces (newlines kept), so a finding's line is the file's own line.
export const strip = (src) => {
  const sf = ts.createSourceFile("surface.tsx", src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const out = src.split("");
  const seen = new Set();
  const visit = (n) => {
    if (n.kind !== ts.SyntaxKind.JsxText) {
      for (const r of ts.getLeadingCommentRanges(src, n.pos) || []) {
        if (seen.has(r.pos)) continue;
        seen.add(r.pos);
        for (let i = r.pos; i < r.end; i++) if (out[i] !== "\n") out[i] = " ";
      }
    }
    for (const c of n.getChildren(sf)) visit(c);
  };
  visit(sf);
  return out.join("");
};
const lineOf = (src, i) => src.slice(0, i).split("\n").length;

/** @returns {Array<{ rule: string; line: number; why: string }>}
 *  Sasha 347 · S1 and S2 are read from TypeScript's syntax tree (a regex window of 600 characters both missed a short chain and flagged a
 *  long one that DID end in .catch): S1 — a `disabled` JSX attribute, with or without a value; S2 — `void <call>`, or a `.then(` chain that
 *  ends without a `.catch(` (or a second, rejection argument) and isn't awaited. */
export function findSilences(src) {
  const out = [];
  const sf = ts.createSourceFile("surface.tsx", src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const at = (n) => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
  const visit = (n) => {
    if (ts.isJsxAttribute(n) && n.name.getText(sf) === "disabled") {
      out.push({ rule: "S1", line: at(n), why: "a raw `disabled=` — use GatedButton, which renders what it is waiting for" });
    }
    if (ts.isVoidExpression(n) && ts.isCallExpression(n.expression)) {
      out.push({ rule: "S2", line: at(n), why: "a promise launched with `void` — its failure would write nothing" });
    }
    // (Sasha 348) a `.then(` chain left without a `.catch(` is the type pass's floating-promise rule below — it knows a promise that is
    // stored or returned (its consumer observes it) from one that is dropped; a syntax-only rule could not
    // S4 (Sasha 348) · a catch that tells nobody: `catch {}` / `catch { /* … */ }`, `.catch(() => {})`, `.then(ok, () => {})` — the failure
    // is swallowed. It must tell someone (lib/outcome: observe, failed → the person, or toConsole for a step that isn't theirs) or handle it.
    const empty = (f) => f && (ts.isArrowFunction(f) || ts.isFunctionExpression(f)) && ts.isBlock(f.body) && f.body.statements.length === 0;
    if (ts.isCatchClause(n) && n.block.statements.length === 0) {
      out.push({ rule: "S4", line: at(n), why: "a catch that tells nobody — tell the failure (lib/outcome) or handle it" });
    }
    if (ts.isCallExpression(n) && ts.isPropertyAccessExpression(n.expression) &&
        ((n.expression.name.text === "catch" && empty(n.arguments[0])) || (n.expression.name.text === "then" && empty(n.arguments[1])))) {
      out.push({ rule: "S4", line: at(n.arguments[n.expression.name.text === "then" ? 1 : 0]), why: "a .catch(() => {}) that tells nobody — tell the failure (lib/outcome) or handle it" });
    }
    // S5 (Sasha 348) · a PRESS told only to the console: inside a JSX event handler (on…), observe(…, toConsole) or noted(…) — the person
    // pressed; the failure is theirs to hear (announce, or the page's own line)
    if (inHandler(n) && ts.isCallExpression(n) && ts.isIdentifier(n.expression) &&
        ((n.expression.text === "observe" && n.arguments[2] && n.arguments[2].getText(sf) === "toConsole") || n.expression.text === "noted")) {
      out.push({ rule: "S5", line: at(n), why: "a press whose failure is told only to the console — tell the person (announce, or the page's own line)" });
    }
    ts.forEachChild(n, visit);
  };
  // a handler is an on… attribute's own code, or a function of this file named there (onClick={begin}) or called from there
  const handlers = new Set();
  const named = (x) => {
    if (ts.isJsxAttribute(x) && /^on[A-Z]/.test(x.name.getText(sf)) && x.initializer && ts.isJsxExpression(x.initializer) && x.initializer.expression) {
      const e = x.initializer.expression;
      if (ts.isIdentifier(e)) handlers.add(e.text);
      const calls = (c) => { if (ts.isCallExpression(c) && ts.isIdentifier(c.expression)) handlers.add(c.expression.text); ts.forEachChild(c, calls); };
      if (ts.isArrowFunction(e) || ts.isFunctionExpression(e)) calls(e.body);
    }
    ts.forEachChild(x, named);
  };
  named(sf);
  const declaredHandler = (u) => (ts.isFunctionDeclaration(u) && u.name && handlers.has(u.name.text)) ||
    ((ts.isArrowFunction(u) || ts.isFunctionExpression(u)) && ts.isVariableDeclaration(u.parent) && ts.isIdentifier(u.parent.name) && handlers.has(u.parent.name.text));
  const inHandler = (n) => {
    for (let u = n.parent; u; u = u.parent) {
      if (ts.isJsxAttribute(u)) return /^on[A-Z]/.test(u.name.getText(sf));
      if (declaredHandler(u)) return true;
    }
    return false;
  };
  visit(sf);
  const code = strip(src);
  for (const m of code.matchAll(/\.length\s*===\s*0\s*\?[^:]{0,120}?Nothing[^:]{0,40}?yet/g)) {
    out.push({ rule: "S3", line: lineOf(code, m.index), why: "\"Nothing … yet\" rendered from an empty list — say it from an explicit not-yet-started state" });
  }
  return out;
}

/** Sasha 347 · S2, the half a syntax tree can't see: a promise left FLOATING — `prepare()` as a statement, `onClick={() => send(t)}` —
 *  found with TypeScript's type checker (the expression's type has a `then`). Observed = awaited, `void`ed (S2 above names that), or a
 *  chain ending in `.catch(` / `.then(ok, failed)`; anything else is a failure nobody would hear. @returns {Map<string, Array<{rule, line, why}>>} */
export function floatingPromises(files, options = null) {
  let opts = options;
  if (!opts) {
    const cfg = ts.getParsedCommandLineOfConfigFile(join(ROOT, "tsconfig.json"), {}, { ...ts.sys, onUnRecoverableConfigFileDiagnostic: () => {} });
    opts = cfg.options;
  }
  const prog = ts.createProgram(files.map((f) => (f.startsWith("/") ? f : join(ROOT, f))), { ...opts, noEmit: true });
  const tc = prog.getTypeChecker();
  const isPromise = (n) => {
    const t = tc.getTypeAtLocation(n);
    return !!t && !(t.flags & (ts.TypeFlags.Any | ts.TypeFlags.Unknown)) && !!tc.getPropertyOfType(tc.getApparentType(t), "then");
  };
  const observed = (e) => {   // from the outside in: a .catch (or .then(ok, failed)) before any one-armed .then; .finally passes through
    for (;;) {
      while (ts.isParenthesizedExpression(e)) e = e.expression;
      if (!(ts.isCallExpression(e) && ts.isPropertyAccessExpression(e.expression))) return false;
      const name = e.expression.name.text;
      if (name === "catch" || (name === "then" && e.arguments.length >= 2)) return true;
      if (name !== "finally") return false;
      e = e.expression.expression;
    }
  };
  const returnsPromise = (n) => {
    const sigs = tc.getTypeAtLocation(n).getCallSignatures();
    return sigs.length > 0 && sigs.every((g) => { const r = g.getReturnType(); return !(r.flags & (ts.TypeFlags.Any | ts.TypeFlags.Unknown)) && !!tc.getPropertyOfType(tc.getApparentType(r), "then"); });
  };
  const voidSlot = (n) => {
    const p = n.parent;
    const inSlot = (ts.isJsxExpression(p) && ts.isJsxAttribute(p.parent)) || ((ts.isCallExpression(p) || ts.isNewExpression(p)) && (p.arguments || []).includes(n))
      || (ts.isPropertyAssignment(p) && p.initializer === n) || ts.isShorthandPropertyAssignment(p);
    if (!inSlot) return false;
    const ctx = tc.getContextualType(n);
    if (!ctx) return false;
    const sigs = ctx.getNonNullableType().getCallSignatures();
    return sigs.length > 0 && sigs.every((g) => !!(g.getReturnType().flags & ts.TypeFlags.Void));
  };
  const out = new Map();
  for (const f of files) {
    const sf = prog.getSourceFile(f.startsWith("/") ? f : join(ROOT, f));
    const found = [];
    const visit = (x) => {
      let hit = null;
      if (ts.isExpressionStatement(x) && !ts.isVoidExpression(x.expression) && !ts.isAwaitExpression(x.expression) && !(ts.isBinaryExpression(x.expression) && x.expression.operatorToken.kind === ts.SyntaxKind.EqualsToken) && isPromise(x.expression) && !observed(x.expression)) hit = x.expression;   // `x = p` stores it: its consumer observes it
      if (ts.isArrowFunction(x) && !ts.isBlock(x.body) && ts.isJsxExpression(x.parent) && ts.isJsxAttribute(x.parent.parent) && isPromise(x.body) && !observed(x.body)) hit = x.body;
      if (hit) found.push({ rule: "S2", line: sf.getLineAndCharacterOfPosition(hit.getStart(sf)).line + 1,
        why: `a floating promise (${hit.getText(sf).slice(0, 40).replace(/\s+/g, " ")}…) — observe() it (lib/outcome): its failure is told` });
      // …and a promise-returning function handed where a `void` callback goes (`send={send}` into `send: (t: string) => void`): every
      // call of it there floats, out of sight of the line that makes it
      if ((ts.isIdentifier(x) || ts.isPropertyAccessExpression(x)) && returnsPromise(x) && voidSlot(x)) {   // an arrow's own body is read above
        found.push({ rule: "S2", line: sf.getLineAndCharacterOfPosition(x.getStart(sf)).line + 1,
          why: `a promise-returning function (${x.getText(sf).slice(0, 40).replace(/\s+/g, " ")}…) given where a void callback goes — its failures float` });
      }
      ts.forEachChild(x, visit);
    };
    if (sf) visit(sf);
    out.set(f, found);
  }
  return out;
}

/** GatedButton must not take a `disabled` prop, and must render its needs. */
export function gatedButtonProblems(src) {
  const code = strip(src);
  const out = [];
  const props = code.match(/type Props = \{([\s\S]*?)\n\}/);
  if (!props) out.push("no `type Props` block found");
  else if (/\bdisabled\s*\??\s*:/.test(props[1])) out.push("GatedButton accepts a `disabled` prop — it must derive disabled from `needs` alone");
  if (!/needs/.test(code) || !/\.join\(/.test(code)) out.push("GatedButton does not render its needs");
  return out;
}

// ── the fixtures: each defect must be caught; the clean form must pass ───────────────────────────────
const FIXTURES = [
  { name: "a raw disabled button", src: `<button disabled={busy || !paired} onClick={pair}>Pair</button>`, want: ["S1"] },
  { name: "a void-launched relay", src: `if (m.type === 'REPORT') { void relayReport(m) }`, want: ["S2"] },
  { name: "a \"/*\" inside a string hides no code (Sasha 347)", src: `<input accept="image/*" />\n<button disabled={busy}>x</button>\n{/* a note */}`, want: ["S1"] },
  { name: "a bare disabled (Sasha 347)", src: `<button disabled onClick={go}>Go</button>`, want: ["S1"] },
  { name: "a long chain that ends in .catch passes (Sasha 347)", src: `fetch('/x').then((r) => r.json()).then((j) => {\n${"  set(j);\n".repeat(80)}}).catch(() => setFailed(true))`, want: [] },
  { name: "an awaited .then is its caller's (Sasha 347)", src: `const j = await fetch('/x').then((r) => r.json())`, want: [] },
  { name: "a catch that tells nobody (Sasha 348)", src: `try { go() } catch { /* nothing */ }\np.catch(() => {})\np.then(ok, () => {})`, want: ["S4"] },
  { name: "a catch that tells or handles passes (Sasha 348)", src: `try { go() } catch (e) { toConsole(failed('Go', e)) }\np.catch(() => null).catch((e) => tell(e))\ntry { a() } catch { return false }`, want: [] },
  { name: "a press told only to the console (Sasha 348)", src: `<button onClick={() => observe(save(), 'Saving', toConsole)}>Save</button>\n<a onClick={() => { go().catch(noted('Go')) }}>x</a>`, want: ["S5"] },
  { name: "a press reached by name is a press (Sasha 348)", src: `const begin = () => { observe(start(), 'Starting', toConsole) }\nconst bg = () => { observe(poll(), 'Reading', toConsole) }\nuseEffect(bg, [])\nreturn <button onClick={begin}>Go</button>`, want: ["S5"] },
  { name: "a press told to the person passes (Sasha 348)", src: `<button onClick={() => observe(save(), 'Saving', announce)}>Save</button>\nuseEffect(() => { observe(poll(), 'Reading', toConsole) }, [])`, want: [] },
  { name: "Nothing yet from an empty list", src: `{log.length === 0 ? <p className="x">Nothing yet.</p> : null}`, want: ["S3"] },
  { name: "the clean forms pass", src: `<GatedButton label="Pair" needs={[!connected && 'Connect, first']} onClick={pair} />\nrelayReport(m).catch((e) => note(String(e), 'stop'))\ncall('/x').then((r) => set(r)).catch(() => set({ unreachable: true }))\n{!started ? <p>Nothing attempted yet.</p> : null}\ntype F = (m: Msg) => void`, want: [] },
];

/** Sasha 348 · every file that ACTS — it imports the one request client (lib/request) or the booking client built on it — in app/ and lib/,
 *  but the server's route handlers (app/api/…, which answer a page; the page tells the person). Found, never listed. */
export function actingPages(dir = "app") {
  const out = [];
  for (const e of readdirSync(join(ROOT, dir), { withFileTypes: true })) {
    const rel = `${dir}/${e.name}`;
    if (e.isDirectory()) { if (rel !== "app/api") out.push(...actingPages(rel)); continue; }
    if (!/\.tsx?$/.test(e.name) || /\.d\.ts$/.test(e.name) || /^(route|middleware)\.ts$/.test(e.name)) continue;
    if (/^import (?!type\b)[^\n]*from ['"](@\/lib|\.{1,2}(\/\.\.)*\/lib|\.)\/(request|booking-client)['"]/m.test(readFileSync(join(ROOT, rel), "utf8"))) out.push(rel);
  }
  if (dir === "app") out.push(...actingPages("lib"));
  return out.sort();
}

function main() {
  let failed = 0;
  for (const f of FIXTURES) {
    const got = [...new Set(findSilences(f.src).map((x) => x.rule))].sort();
    const ok = JSON.stringify(got) === JSON.stringify(f.want);
    if (!ok) { failed++; console.error(`  ✗ fixture "${f.name}": caught ${JSON.stringify(got)}, expected ${JSON.stringify(f.want)}`); }
  }
  if (failed) {
    console.error(`\ncheck-outcome-surfaces: the checker itself is broken (${failed} fixture(s)) — refusing to vouch for anything.`);
    process.exit(1);
  }
  {   // Sasha 348 · the direct-request refusal on fixtures: each kind caught, the one client's names pass
    const caught = directRequests("fetch('/a'); window.fetch('/b'); new EventSource('/c'); new WebSocket('wss://d'); navigator.sendBeacon('/e'); new XMLHttpRequest()\nimport axios from 'axios'\n", "f.ts").length;
    const clean = directRequests("reach('/a'); events('/c'); socket('wss://d'); beacon('/e'); request('/f'); obj.fetch2('/g')\n", "g.ts").length;
    if (caught !== 7 || clean !== 0) {
      console.error(`check-outcome-surfaces: the direct-request checker is broken (caught ${caught} of 7, ${clean} false) — refusing to vouch for anything.`);
      process.exit(1);
    }
  }
  {   // Sasha 347 · the floating-promise half runs on fixtures too: caught, and the clean forms pass
    const dir = mkdtempSync(join(tmpdir(), "outcome-"));
    const bad = join(dir, "bad.tsx"), good = join(dir, "good.tsx");
    const head = "declare function go(): Promise<void>\ndeclare function observe(p: Promise<unknown>, n: string, t: (s: string) => void): void\ndeclare const tell: (s: string) => void\n";
    writeFileSync(bad, head + "declare function Kid(p: { act: () => void }): any\nexport function A() { go().then(() => tell('ok')); return <><button onClick={() => go()}>x</button><Kid act={go} /></> }\n");
    writeFileSync(good, head + "let held: Promise<void> | null = null\nexport async function B() { held = go().then(() => tell('ok')); await go(); go().catch(() => tell('no')); go().catch(() => tell('no')).finally(() => tell('done')); observe(go(), 'Go', tell); return <button onClick={() => observe(go(), 'Go', tell)}>x</button> }\n");
    const fl = floatingPromises([bad, good], { jsx: ts.JsxEmit.Preserve, lib: ["lib.es2020.d.ts", "lib.dom.d.ts"], strict: true, skipLibCheck: true });
    if (fl.get(bad).length !== 3 || fl.get(good).length !== 0) {
      console.error(`check-outcome-surfaces: the floating-promise checker is broken (caught ${fl.get(bad).length} of 3, ${fl.get(good).length} false) — refusing to vouch for anything.`);
      process.exit(1);
    }
  }
  const problems = [];
  // Sasha 348 · ONE request client: a direct fetch( / EventSource / WebSocket / sendBeacon / XMLHttpRequest / axios anywhere in the frontend
  // but lib/request.ts is refused — zero exceptions (scripts/one-client.mjs --write moves a file onto it, mechanically)
  for (const rel of sourceFiles()) {
    for (const d of directRequests(readFileSync(join(ROOT, rel), "utf8"), rel)) problems.push(`${rel}:${d.line}  R1  a direct ${d.what} — every request goes through lib/request (node scripts/one-client.mjs --write)`);
  }
  // Sasha 346/347 · a page that ACTS (calls bookingReq) is an outcome surface: every one is checked, with no exceptions
  const surfaces = [...new Set([...OUTCOME_SURFACES, ...actingPages()])];
  const floating = floatingPromises(surfaces);
  for (const rel of surfaces) {
    for (const p of [...findSilences(readFileSync(join(ROOT, rel), "utf8")), ...(floating.get(rel) || [])]) problems.push(`${rel}:${p.line}  ${p.rule}  ${p.why}`);
  }
  for (const p of gatedButtonProblems(readFileSync(join(ROOT, GATED_BUTTON), "utf8"))) problems.push(`${GATED_BUTTON}  S1  ${p}`);
  if (problems.length) {
    console.error(`\ncheck-outcome-surfaces: ${problems.length} silent path(s) on an outcome surface:\n  ${problems.join("\n  ")}\n`);
    process.exit(1);
  }
  // S-45 · Sasha's reservations in the guest's trip view. A CTO drop overwrites YouPanel.tsx; Stage B re-inserts the
  // block. A skipped Stage B must FAIL the build, never ship a trip view that silently lost the reservations.
  // S-66 · booking inside the chat. A CTO drop overwrites SashaChat.tsx; Stage B re-inserts the five lines (CLAUDE.md).
  const chat = readFileSync(join(ROOT, "app/components/SashaChat.tsx"), "utf8");
  if ((chat.match(/S-66 chat booking/g) || []).length < 5 || !chat.includes("<ChatBooking ") || !chat.includes("takeChatText(content)")) {
    console.error("check-outcome-surfaces: SashaChat.tsx lacks the S-66 chat booking lines — run Stage B's chat booking re-apply (CLAUDE.md).");
    process.exit(1);
  }
  // S-62 step 7 · the chat sends a signed-in guest's token and never continues a session that is not theirs
  if ((chat.match(/S-62 step 7/g) || []).length < 5 || !chat.includes("apiHeaders(guestAuth())")) {
    console.error("check-outcome-surfaces: SashaChat.tsx lacks the S-62 step 7 lines (guest token, session adoption) — re-apply them (CLAUDE.md, Stage B).");
    process.exit(1);
  }
  const you = readFileSync(join(ROOT, "app/components/workspace/YouPanel.tsx"), "utf8");
  if (!you.includes("S-45 Sasha reservations") || !you.includes("<SashaReservations />")) {
    console.error("check-outcome-surfaces: YouPanel.tsx lacks the S-45 Sasha reservations block — run Stage B's reservations re-apply (CLAUDE.md).");
    process.exit(1);
  }
  // …and its empty sentence may be said only from a real, answered empty list — never on a failure
  const res = readFileSync(join(ROOT, "app/components/workspace/SashaReservations.tsx"), "utf8");
  const empties = strip(res).split("\n").filter((l) => l.includes("No reservations made through Sasha yet"));   // code, not comments
  if (empties.length !== 1 || !/state\.phase === 'loaded' && state\.items\.length === 0/.test(empties[0])) {
    console.error("check-outcome-surfaces: SashaReservations says \"No reservations made through Sasha yet\" somewhere other than its answered-empty branch.");
    process.exit(1);
  }
  // S-62 step 0 · onboarding writes `clients` with the service-role key: the sign-in check must come before any write.
  // A CTO drop replaces this route; a lost gate must FAIL the build, never ship an open write again.
  const onboard = strip(readFileSync(join(ROOT, "app/api/onboarding/save/route.ts"), "utf8"));
  const gate = onboard.indexOf("if (!(await founderSignedIn()))"), write = onboard.indexOf("rest/v1/clients");
  if (gate < 0 || write < 0 || gate > write || !onboard.includes("import { founderSignedIn } from '@/lib/signed-in'")) {
    console.error("check-outcome-surfaces: app/api/onboarding/save/route.ts writes without the S-62 sign-in gate before it — re-apply it (CLAUDE.md, Stage B).");
    process.exit(1);
  }
  // S-62 · Go Live must never show success for a refused or failed save (Sasha 67): Stage B re-applies it to the CTO's pages
  const page = strip(readFileSync(join(ROOT, "app/onboarding/page.tsx"), "utf8"));
  const step6 = strip(readFileSync(join(ROOT, "app/onboarding/components/Step6Deploy.tsx"), "utf8"));
  if (!/if \(!res\.ok\) \{[\s\S]*?throw new Error\(why\)/.test(page) || !step6.includes("setGoLiveError(") || !step6.includes("{goLiveError && (")) {
    console.error("check-outcome-surfaces: onboarding Go Live can show success for a refused save — run python3 frontend/scripts/stage_b_onboarding_honesty.py (CLAUDE.md, Stage B).");
    process.exit(1);
  }
  console.log(`check-outcome-surfaces: ${FIXTURES.length} fixtures caught as expected; ${surfaces.length} outcome surface(s) clean (every page that acts — no exceptions); onboarding save is signed-in only and Go Live is honest.`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main();
