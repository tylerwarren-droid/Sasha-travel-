"""CR 4 · Spain health on WhatsApp ("salud" / "health"), inside S-77's line (docs/sasha/S-77-…):

  · PRIVATE clinic → booked by phone through Sasha's own call path (read-back, one yes, the call). For the demo a
    "Kanoe Test Clinic" stands in, whose phone is the Sasha TEST LINE (SASHA_TEST_CALL_NUMBER — the founder's own phone).
  · PUBLIC (Madrid SERMAS) → a hand-over: the official appointment page, the identifiers it asks for ready to copy,
    the appointment type, and "you press". ⛔ Never automated, never submitted, never slot-hunted, never a Cl@ve.
  · NEW IN MADRID → padrón → INSS entitlement → tarjeta sanitaria → the family doctor, as a sourced checklist with
    reminders.

Health-data rules (GDPR Art. 9; S-77 §6–7, H-1):
  · a consent sentence before anything; the REASON for seeing a doctor is never asked, never recorded;
  · minimum necessary: the private call needs a name and a time; the hand-over needs the three identifiers SERMAS asks for;
  · a real person's health identifiers are held ONLY in the vault, as a special-category item, with explicit consent —
    which the vault refuses until a DPIA is recorded (SASHA_VAULT_HEALTH_DPIA_REF). Until then nothing of theirs is
    stored: the hand-over says what to have ready, with no values. The demo's patient is FICTIONAL;
  · values shown on a hand-over are purged from it after VALUES_TTL; every case is deleted after 30 days.
"""

from .status import health_status  # noqa: E402,F401  (CR 46 · the platform's 🇪🇸 Health card tab)
