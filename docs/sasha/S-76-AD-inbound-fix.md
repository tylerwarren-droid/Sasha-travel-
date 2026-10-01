# S-76 — for the US tab: AD's inbound webhook must ignore Sasha's mail (booking.kanoe.ai)

*Sasha tab, 1 Oct 2026. Read-only reading of the Applied Diligence repo at its working tree. **Nothing in AD's repo was
changed**: git there is the US tab's.*

## Why

- Resend's webhooks are **account-wide**. Sasha (`booking.kanoe.ai`) and AD share one Resend account, so every email
  Sasha receives is also POSTed to AD's `https://applieddiligence.com/api/inbound-email`.
- **What AD does with it today**, in `app/api/inbound-email/route.ts`:
  - `:412–421` **fetches the full body** of every received email, Sasha's venue replies included;
  - `:424` runs AD's act branch. `ACT_ADDRESS` (`lib/agapi/austen/inbound.ts:45`) matches `act-<uuid>@` **on any
    domain**, and that is exactly Sasha's reply-address shape (`act-<uuid>@booking.kanoe.ai`). So each Sasha reply
    enters AD's act branch;
  - finding no AD act for that id, `matchInbound` returns `unknown_act` with *"⚠⚠⚠ SURFACE IT … A person reads this
    one."*, and the reply's from/to/subject go into **AD's audit trail** as unmatched inbound.
- So AD reads a hotel or restaurant's reply to Sasha, and raises a false alarm about it.

## The fix (one guard, before anything is fetched or logged)

In **`app/api/inbound-email/route.ts`**, immediately after **line 407** (`const { to, from, subject, attachments,
email_id } = data;`) and **before line 409** (the body-fetch comment):

```ts
    // Sasha (booking.kanoe.ai) shares this Resend account, and Resend's webhooks are account-wide, so her venue replies
    // arrive here too. They are not Applied Diligence mail: never fetched, matched, logged or stored. (Sasha has her own
    // webhook, which handles them.)
    const recipients = (Array.isArray(to) ? to : [to]).map((a) => String(a ?? "").toLowerCase());
    if (recipients.length > 0 && recipients.every((a) => a.includes("@booking.kanoe.ai"))) {
      return NextResponse.json({ message: "Ignored: not Applied Diligence mail (booking.kanoe.ai)" });
    }
```

- `every`, not `some`: a mail that copies an AD address as well still reaches AD.
- It returns **200**, so Resend doesn't retry.

**A test for it**, in the route's existing test file, or a new one if none exists:
- a signed `email.received` with `to: ["act-00000000-0000-4000-8000-000000000000@booking.kanoe.ai"]` answers 200
  "Ignored…";
- `fetch` to `api.resend.com/emails/…` is **never** called;
- **no** audit or `unmatched_inbound` row is written.

## Optional hardening (AD's call)

- `ACT_ADDRESS` (`lib/agapi/austen/inbound.ts:45`) could be bound to AD's own act domain rather than `@` on any domain.
  AD's act domain isn't fixed in code that I could find, so I don't suggest a value.
- `app/api/inbound-email/poll/route.ts:38` lists only the account's **latest 20** received emails. Once Sasha receives
  mail on the same account, her messages count toward those 20 and could push an AD case email out of the window.
  Paginate, or filter by recipient domain server-side if Resend allows it.
