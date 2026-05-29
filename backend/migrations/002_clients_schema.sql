-- Migration 002: Multi-tenant clients schema
-- clients holds per-tenant branding/config; client_api_keys holds hashed keys
-- for server-to-server callers that can't supply a Host header.

CREATE TABLE IF NOT EXISTS clients (
    id              UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    slug            TEXT        NOT NULL UNIQUE,
    display_name    TEXT        NOT NULL,
    -- list of bare hostnames this tenant owns (no scheme, no port)
    -- e.g. '{kanoe.travel,app.kanoe.travel}'
    allowed_domains TEXT[]      NOT NULL DEFAULT '{}',
    -- persona, feature flags, prompt overrides, branding
    config          JSONB       NOT NULL DEFAULT '{}',
    is_active       BOOLEAN     NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_clients_domains
    ON clients USING GIN(allowed_domains);

CREATE INDEX IF NOT EXISTS idx_clients_slug
    ON clients(slug) WHERE is_active;

-- Ensure set_updated_at exists (defined in 001; repeated here for safety)
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_clients_updated_at ON clients;
CREATE TRIGGER trg_clients_updated_at
    BEFORE UPDATE ON clients
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- Separate table so keys can be rotated without touching the client row.
-- key_hash is SHA-256(raw_key) hex-encoded — the raw key is never stored.
CREATE TABLE IF NOT EXISTS client_api_keys (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    client_id    UUID        NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    key_hash     TEXT        NOT NULL UNIQUE,
    label        TEXT,
    is_active    BOOLEAN     NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash
    ON client_api_keys(key_hash) WHERE is_active;


-- Seed: Kanoe (the primary product)
INSERT INTO clients (slug, display_name, allowed_domains, config) VALUES (
  'kanoe',
  'Kanoe Travel',
  ARRAY[
    'kanoe.travel',
    'app.kanoe.travel',
    'kanoe-travel.vercel.app',
    'localhost',
    '127.0.0.1'
  ],
  '{
    "persona_name": "Sasha",
    "persona_tagline": "Your AI travel concierge",
    "primary_color": "#2563eb",
    "allowed_currencies": ["USD"],
    "feature_flags": {
      "voice": true,
      "heygen": true,
      "golf": true,
      "booking_confirmation": true
    }
  }'
) ON CONFLICT (slug) DO NOTHING;

-- Seed: Discover Vietnam white-label
INSERT INTO clients (slug, display_name, allowed_domains, config) VALUES (
  'discover-vietnam',
  'Discover Vietnam',
  ARRAY[
    'discover-vietnam.vercel.app',
    'discovervietnam.travel'
  ],
  '{
    "persona_name": "Sasha",
    "persona_tagline": "Your Vietnam travel expert",
    "primary_color": "#dc2626",
    "allowed_currencies": ["USD"],
    "feature_flags": {
      "voice": true,
      "heygen": true,
      "golf": false,
      "booking_confirmation": true
    }
  }'
) ON CONFLICT (slug) DO NOTHING;
