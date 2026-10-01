"""Stage B · S-62 onboarding honesty (Sasha 67) — re-applied after every CTO drop. Run from the repo root:

    python3 frontend/scripts/stage_b_onboarding_honesty.py

The CTO's onboarding page ignored the save's answer: a refused save (401 sign_in_required, S-62 step 0) or a failed
one reached "Sasha is live!". This makes page.tsx throw the server's own reason and Step6Deploy show it next to Go Live,
never the success screen. Idempotent; REFUSES, loudly, if an anchor moved. The prebuild fails while it is missing.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MARK = "S-62 onboarding honesty"


def patch(rel, edits):
    p = ROOT / rel
    s = p.read_text()
    if MARK in s:
        print(f"{rel}: already present")
        return
    for old, new in edits:
        if s.count(old) != 1:
            sys.exit(f"⛔ STOP: {rel}'s anchor changed in this CTO drop — onboarding honesty was NOT re-applied. Place it by hand.\n  anchor: {old[:80]!r}")
        s = s.replace(old, new)
    p.write_text(s)
    print(f"{rel}: re-applied")


SAVE = """    await fetch('/api/onboarding/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ formData: updatedData, goLive: true }),
    })
"""
patch("app/onboarding/page.tsx", [(SAVE, """    // S-62 onboarding honesty (Stage B): a refused or failed save never reaches "Sasha is live!" — the server's own
    // reason is thrown to Step6Deploy, which shows it. The draft is kept until the save is accepted.
    const res = await fetch('/api/onboarding/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ formData: updatedData, goLive: true }),
    })
    if (!res.ok) {
      let why = `the server answered HTTP ${res.status}`
      try {
        const j = await res.json() as { error?: string; message?: string }
        why = j.error ?? j.message ?? why
      } catch { /* not JSON: the status says it */ }
      throw new Error(why)
    }
""")])

patch("app/onboarding/components/Step6Deploy.tsx", [
    ("""  const [isLive, setIsLive] = useState(false)
""", """  const [isLive, setIsLive] = useState(false)
  const [goLiveError, setGoLiveError] = useState<string | null>(null)  // S-62 onboarding honesty (Stage B)
"""),
    ("""      await onGoLive()
      setIsLive(true)
    } finally {""", """      setGoLiveError(null)
      await onGoLive()
      setIsLive(true)
    } catch (e) {  // S-62 onboarding honesty: not live — say why, in the server's words
      setGoLiveError(e instanceof Error && e.message ? e.message : 'the save did not go through')
    } finally {"""),
    ("""      {!allChecked && (
        <p className="text-center text-xs" style={{ color: '#9CA3AF' }}>""", """      {goLiveError && (  /* S-62 onboarding honesty */
        <p role="alert" className="text-center text-sm" style={{ color: '#9A1C1C' }}>
          Not live — nothing was published: {goLiveError}
        </p>
      )}

      {!allChecked && (
        <p className="text-center text-xs" style={{ color: '#9CA3AF' }}>"""),
])
