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

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const ROOT = fileURLToPath(new URL("..", import.meta.url));

/** Pages where a person acts and must learn what happened. Add a page here when it becomes one. */
export const OUTCOME_SURFACES = ["app/booking-helper/page.tsx", "app/booking-helper/PhoneCall.tsx", "app/booking-helper/Ladder.tsx", "app/booking-helper/FounderGate.tsx", "app/components/workspace/SashaReservations.tsx", "app/components/ChatBooking.tsx", "app/components/ChatBookingCall.tsx", "app/booking-helper/FormSend.tsx", "app/components/ChatBookingLink.tsx", "app/components/ChatCancel.tsx"];
// CR 1 · CampusMe and relocation pages (their own line, so the Sasha tab's list above never conflicts)
OUTCOME_SURFACES.push("app/campus-handover/[id]/page.tsx", "app/campus-handover/[id]/CopyAnswer.tsx", "app/relocation-file/[id]/page.tsx", "app/health-handover/[id]/page.tsx");
/** The one component allowed to set `disabled=` — because it derives it from rendered needs. */
export const GATED_BUTTON = "app/booking-helper/GatedButton.tsx";

const strip = (src) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
const lineOf = (src, i) => src.slice(0, i).split("\n").length;

/** @returns {Array<{ rule: string; line: number; why: string }>} */
export function findSilences(src) {
  const code = strip(src);
  const out = [];
  for (const m of code.matchAll(/\bdisabled\s*=\s*\{/g)) {
    out.push({ rule: "S1", line: lineOf(code, m.index), why: "a raw `disabled=` — use GatedButton, which renders what it is waiting for" });
  }
  for (const m of code.matchAll(/(^|[\s;{(])void\s+[A-Za-z_$][\w$.]*\s*\(/gm)) {
    out.push({ rule: "S2", line: lineOf(code, m.index), why: "a promise launched with `void` — its failure would write nothing" });
  }
  for (const m of code.matchAll(/\.then\(/g)) {
    // the rest of this expression: up to the next statement end at the same nesting
    const rest = code.slice(m.index, m.index + 600);
    let depth = 0, end = rest.length;
    for (let i = 0; i < rest.length; i++) {
      const c = rest[i];
      if (c === "(" || c === "{" || c === "[") depth++;
      else if (c === ")" || c === "}" || c === "]") { depth--; if (depth < 0) { end = i; break; } }
      else if ((c === ";" || c === "\n") && depth === 0) { end = i; break; }
    }
    if (!rest.slice(0, end).includes(".catch(")) out.push({ rule: "S2", line: lineOf(code, m.index), why: "a `.then(` with no `.catch(` — a rejection would write nothing" });
  }
  for (const m of code.matchAll(/\.length\s*===\s*0\s*\?[^:]{0,120}?Nothing[^:]{0,40}?yet/g)) {
    out.push({ rule: "S3", line: lineOf(code, m.index), why: "\"Nothing … yet\" rendered from an empty list — say it from an explicit not-yet-started state" });
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
  { name: "a .then with no .catch", src: `call('/x').then((r) => setHealth(r))\n`, want: ["S2"] },
  { name: "Nothing yet from an empty list", src: `{log.length === 0 ? <p className="x">Nothing yet.</p> : null}`, want: ["S3"] },
  { name: "the clean forms pass", src: `<GatedButton label="Pair" needs={[!connected && 'Connect, first']} onClick={pair} />\nrelayReport(m).catch((e) => note(String(e), 'stop'))\ncall('/x').then((r) => set(r)).catch(() => set({ unreachable: true }))\n{!started ? <p>Nothing attempted yet.</p> : null}\ntype F = (m: Msg) => void`, want: [] },
];

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
  const problems = [];
  for (const rel of OUTCOME_SURFACES) {
    for (const p of findSilences(readFileSync(join(ROOT, rel), "utf8"))) problems.push(`${rel}:${p.line}  ${p.rule}  ${p.why}`);
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
  console.log(`check-outcome-surfaces: ${FIXTURES.length} fixtures caught as expected; ${OUTCOME_SURFACES.length} outcome surface(s) clean; onboarding save is signed-in only and Go Live is honest.`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main();
