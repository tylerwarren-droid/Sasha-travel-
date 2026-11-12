# CR 196 · AgAPI's half of Sasha 381: the person's INSTRUCTION is the approval of a venue booking

Tyler's decisions (KANOE_DECISIONS.md, 12 Nov 2026):
- **20:11:** for a venue booking, the person's instruction IS the approval. There is no separate yes card.
- **20:20:** a term the person didn't give is asked, and only that term.

Sasha 381 is built on branch `sasha/381`. It merges in the joint window with CR 194 + CR 195 + CR 196.

## What Sasha sends (built)

Every venue act goes through this one sequence, in the same turn:

1. `venue.prepare_booking`.
2. `venue.submit_booking` with no approval. AgAPI answers `approval_required` with `read_back_id` and `read_back_sha256`. Sasha keeps these on the act and never shows them as a card.
3. The approval:
   - **In the app:** ONE `approvals.in_app_tap`, as specified below.
   - **On WhatsApp:** unchanged. The instruction's own signed message is the session (CR 99 §4d, kind `whatsapp`), and AgAPI uses its message id once.

### The in-app approval

```
approvals.in_app_tap {
  read_back_id, read_back_sha256,
  session: {kind: "in_app", t, nonce, instruction_id, session_id, signature}
}
```

```
signature = hex HMAC-SHA256(SASHA_AGAPI_TAP_SECRET,
            "<t>.<nonce>.in_app.<instruction_id>.<who>.<read_back_id>.<read_back_sha256>")
```

- `instruction_id`: the turn (or tap) the instruction was given in. This is Sasha 372's id, the same one CR 187's mandate proof is keyed by.
- `who`: the person's Sasha account. AgAPI resolves it with `access.person_of`, from the end user's external_ref `sasha:<account>`.
- `session_id`: the conversation. It is context only and is not signed.

Sasha signs only on a turn whose request carried the person's verified session. Sasha's vector is in `backend/tests/test_s381_instruction_is_the_approval.py`, `TheProof.test_the_vector`.

## AgAPI's half (CR 196)

1. **Accept the kind.** `approvals.in_app_tap` accepts `session.kind = "in_app"` with the fields above. It is first-party only (product `sasha`, like CR 190's card tap).
   - Verify `t` within the same window as today's taps.
   - Verify the signature over the exact string above, with the same secret as CR 187's mandate proof.
   - `who` must be the read-back's person (`access.person_of` of its end user).
   - Anything else → `approval_untrusted_origin`.
2. **Once per instruction and read-back.** The once-key is `"instruction:" + sha256(instruction_id + "." + read_back_id)`.
   - The same instruction and read-back again → `approval_consumed`.
   - A second booking in one instruction (another read-back) is its own approval.
   - Store the nonce once, as CR 187 does.
3. **The approval records the instruction.** It is recorded as `{kind: "in_app", id: instruction_id}`, with session_id kept as context. This goes through THE ONE `_answer`, so the act, presentation and checks are the same as a tap.
4. **Spec and contract.**
   - `approvals_in_app_tap_in.session` gains kind `in_app`, plus `instruction_id` (string, 1–200) and `session_id` (string, ≤ 200).
   - `additionalProperties` stays false.
   - Add a vector in `spec/ext/vectors/` (instruction_tap.json) and a note in operations.ext.json.
   - kanoe-contract minor bump.
5. **Unchanged.**
   - The `supabase` session kind stays, for taps on cards that remain (cancel, group cards, the health product's call).
   - The `whatsapp` kind is unchanged.
   - The read-back, R10, booking rules and test-person gate are unchanged. A test person never reaches a real venue.

## Ratchet (AgAPI side, suggested)
- (a) The vector.
- (b) An in_app session for another person → refused.
- (c) The same instruction twice on one read-back → the second is `approval_consumed`.
- (d) Two read-backs, one instruction → both approved.
- (e) A tampered read_back_sha256 → refused.
- (f) A non-first-party key → forbidden.
