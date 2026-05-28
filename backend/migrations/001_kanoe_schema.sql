-- Migration 001: Kanoe core schema
-- booking_references links Kanoe-generated refs to RateHawk order IDs.
-- prompt_versions is the audit trail for all system prompts.

CREATE TABLE IF NOT EXISTS booking_references (
    id              UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    kanoe_ref       TEXT        NOT NULL UNIQUE,
    ratehawk_booking_id TEXT,
    user_id         UUID        REFERENCES auth.users(id),
    guest_name      TEXT,
    hotel_name      TEXT,
    check_in        DATE,
    check_out       DATE,
    currency        TEXT        NOT NULL DEFAULT 'USD',
    status          TEXT        NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','confirmed','cancelled')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_booking_refs_user     ON booking_references(user_id);
CREATE INDEX IF NOT EXISTS idx_booking_refs_status   ON booking_references(status);
CREATE INDEX IF NOT EXISTS idx_booking_refs_kanoe    ON booking_references(kanoe_ref);

-- updated_at trigger
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_booking_refs_updated_at ON booking_references;
CREATE TRIGGER trg_booking_refs_updated_at
    BEFORE UPDATE ON booking_references
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE IF NOT EXISTS prompt_versions (
    id          UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    prompt_name TEXT        NOT NULL,
    version     TEXT        NOT NULL,
    prompt_text TEXT        NOT NULL,
    is_active   BOOLEAN     NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (prompt_name, version)
);

CREATE INDEX IF NOT EXISTS idx_prompt_versions_lookup
    ON prompt_versions(prompt_name, is_active);

-- Seed with current prompts (v1 baseline)
INSERT INTO prompt_versions (prompt_name, version, prompt_text, is_active) VALUES
(
  'conductor.general',
  'v1',
  'You are Sasha, a warm and knowledgeable AI travel concierge. You specialise in Vietnam but can help with travel anywhere. Keep responses concise and conversational — you are speaking, not writing an essay. Maximum 3 sentences unless asked for more detail.',
  true
),
(
  'conductor.merge',
  'v1',
  'You are Sasha, a warm AI travel concierge. You have received responses from multiple specialist agents. Synthesize them into ONE natural, conversational response. Do not mention "agents" or "specialists" — just be Sasha. Keep it concise and warm. Max 4 sentences unless detail is needed.',
  true
),
(
  'booking_confirmation.system',
  'v1',
  'You are Sasha''s booking confirmation specialist. You help guests get their hotel''s internal PMS reference number after booking through platforms like Booking.com, Expedia, Hotels.com, or Airbnb.

When a user gives you their booking details:
1. First find the hotel''s contact details
2. Send a confirmation email to the hotel
3. Initiate an AI phone call to the hotel via Bland.ai
4. Also provide a phone script in case they want to call themselves

Always do email AND phone call simultaneously — both increase the chances of getting a response quickly.

Be efficient and professional. Collect all needed info before taking action:
- Hotel name and city/country
- Guest name
- Booking platform (Booking.com, Expedia etc)
- Booking reference number
- Check-in date
- Guest email (to receive hotel''s response)',
  true
)
ON CONFLICT (prompt_name, version) DO NOTHING;
