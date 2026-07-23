'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

// TDM deck: 14 slides ported from the original portal. The carousel was DOM-driven
// (a tdmIdx global plus tdmRender() rewriting classNames and rebuilding the dots); it is
// React state here, keeping the same wrap-around paging, dots and touch-swipe behaviour.
const TOTAL = 14

export default function Tdm() {
  const [idx, setIdx] = useState(0)
  const startX = useRef(0)

  const nav = useCallback((dir: number) => setIdx(i => (i + dir + TOTAL) % TOTAL), [])
  const slideClass = (i: number) => `tdm-slide${i === idx ? ' active' : ''}`

  const handleTouchEnd = (e: React.TouchEvent) => {
    const diff = startX.current - e.changedTouches[0].clientX
    if (Math.abs(diff) > 50) nav(diff > 0 ? 1 : -1)
  }

  // A 14-slide deck is unusable from the keyboard without this: the original supported only
  // clicks and touch swipes, so presenting from a clicker or arrow keys did nothing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement
      if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return
      if (e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); nav(1) }
      else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); nav(-1) }
      else if (e.key === 'Home') { e.preventDefault(); setIdx(0) }
      else if (e.key === 'End') { e.preventDefault(); setIdx(TOTAL - 1) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [nav])

  return (
    <div
          className="panel active"
          id="panel-tdm"
          onTouchStart={e => { startX.current = e.touches[0].clientX }}
          onTouchEnd={handleTouchEnd}
        >
  

      {/* Slide 1: Title */}
      <div className={slideClass(0)} id="tdm-s1">
        <div className="s-wrap" style={{ display: "flex", flexDirection: "column", justifyContent: "center", minHeight: "calc(100vh - 66px)" }}>
          <div style={{ textAlign: "center", maxWidth: "700px", margin: "0 auto" }}>
            <div style={{ marginBottom: "32px" }}>
              <span style={{ fontFamily: "DM Sans,sans-serif", fontSize: "32px", fontWeight: "800", color: "#00E5C0", letterSpacing: "-1px" }}>KANOE</span><span style={{ fontFamily: "DM Sans,sans-serif", fontSize: "32px", fontWeight: "300", color: "#fff" }}>.ai</span>
            </div>
            <div style={{ width: "60px", height: "2px", background: "#00E5C0", margin: "0 auto 32px" }}></div>
            <h1 style={{ fontFamily: "DM Serif Display,serif", fontSize: "48px", color: "#fff", margin: "0 0 20px", lineHeight: "1.1" }}>The Operating System<br /><em style={{ color: "#00E5C0" }}>for Travel</em></h1>
            <div style={{ display: "flex", justifyContent: "center", gap: "24px", marginTop: "32px" }}>
              <span className="s-pill">Technical Overview</span>
              <span className="s-pill">Agentic AI Platform</span>
              <span className="s-pill">Seed Stage</span>
            </div>
          </div>
        </div>
      </div>

      {/* Slide 2: What is Kanoe */}
      <div className={slideClass(1)} id="tdm-s2">
        <div className="s-wrap">
          <div className="s-eyebrow">Platform Overview</div>
          <h1 className="s-h1">What is <em>Kanoe.ai?</em></h1>
          <div className="s-highlight">The Operating System for Travel — an AI-first, crypto-native unified infrastructure layer for OTAs, ITAs, and DMCs.</div>
          <div className="s-grid4">
            <div className="s-card">
              <div className="s-card-icon">🧠</div>
              <div className="s-card-title">AI Orchestrator</div>
              <div className="s-card-body">Agentic AI agents (Sasha, Juan, Tyler, Anna) handle pricing, recommendations, and ops in real time.</div>
            </div>
            <div className="s-card">
              <div className="s-card-icon">🔗</div>
              <div className="s-card-title">Unified Travel API</div>
              <div className="s-card-body">Single integration hub aggregating Amadeus, Duffel, Viator, HotelsPro, and more inventory sources.</div>
            </div>
            <div className="s-card">
              <div className="s-card-icon">₿</div>
              <div className="s-card-title">Crypto-Native Rails</div>
              <div className="s-card-body">One settlement layer for B2B and B2C. Every counterparty. Any payment method, including crypto.</div>
            </div>
            <div className="s-card">
              <div className="s-card-icon">📈</div>
              <div className="s-card-title">Post-Booking Engine</div>
              <div className="s-card-body">Continuous optimisation after booking. Alerts, re-pricing, vault storage, and journey memory.</div>
            </div>
          </div>
        </div>
      </div>

      {/* Slide 3: Agentic AI */}
      <div className={slideClass(2)} id="tdm-s3">
        <div className="s-wrap">
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "16px" }}><span className="s-tag">Core USP</span></div>
          <h1 className="s-h1">Agentic AI — <em>The Intelligence Core</em></h1>
          <p className="s-sub">Four specialised AI agents coordinate across every platform role, autonomously and in real time.</p>
          <div className="s-grid4">
            <div className="s-card" style={{ borderTop: "3px solid #00E5C0" }}>
              <div className="s-card-title">OTA Agent</div>
              <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#00E5C0", marginBottom: "10px", letterSpacing: "0.08em" }}>OTA</div>
              <div className="s-card-body">End-to-end OTA ops: search, quote, book, notify and account management. LLM-driven with realtime voice & avatar interface.</div>
            </div>
            <div className="s-card" style={{ borderTop: "3px solid #378ADD" }}>
              <div className="s-card-title">ITA Advisor</div>
              <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#378ADD", marginBottom: "10px", letterSpacing: "0.08em" }}>ITA</div>
              <div className="s-card-body">Personal travel advisor mode. Constraint-aware, preference-learning, bespoke itinerary builder.</div>
            </div>
            <div className="s-card" style={{ borderTop: "3px solid #7F77DD" }}>
              <div className="s-card-title">DMC Ops</div>
              <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#7F77DD", marginBottom: "10px", letterSpacing: "0.08em" }}>DMC</div>
              <div className="s-card-body">Ground operations: logistics SPs, supplier comms, group management and multi-stop coordination.</div>
            </div>
            <div className="s-card" style={{ borderTop: "3px solid #EF9F27" }}>
              <div className="s-card-title">Platform Admin</div>
              <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#EF9F27", marginBottom: "10px", letterSpacing: "0.08em" }}>Admin</div>
              <div className="s-card-body">System-wide oversight: analytics, white-label config, tenant branding, compliance & reporting.</div>
            </div>
          </div>
          <div className="s-box">
            <div className="s-box-body" style={{ textAlign: "center" }}>LLM Backbone: OpenAI GPT-4o · Anthropic Claude · Google Gemini · Perplexity · D-ID Avatar · UNITH</div>
          </div>
        </div>
      </div>

      {/* Slide 4: Platform Architecture */}
      <div className={slideClass(3)} id="tdm-s4">
        <div className="s-wrap">
          <div className="s-eyebrow">Architecture</div>
          <h1 className="s-h1">Platform <em>Architecture</em></h1>
          <div className="s-box" style={{ borderLeft: "3px solid #00E5C0", marginBottom: "12px" }}>
            <div className="s-box-title">Interface Layer</div>
            <div className="s-box-body">LLM Chat · Voice Avatar · Admin UI · White-Label B2B Dashboard · Branding Config Manager</div>
          </div>
          <div className="s-box" style={{ borderLeft: "3px solid #378ADD", marginBottom: "12px" }}>
            <div className="s-box-title">Intelligence & Orchestration</div>
            <div className="s-box-body">Rules Engine · Scoring Engine · Prompt Engine · Session Memory · Constraint Manager</div>
          </div>
          <div className="s-box" style={{ borderLeft: "3px solid #7F77DD", marginBottom: "12px" }}>
            <div className="s-box-title">Commerce & Content</div>
            <div className="s-box-body">Booking Engine · Payment Gateway · Order/Offer Manager · Journey Manager · Preview Generator</div>
          </div>
          <div className="s-box" style={{ borderLeft: "3px solid #EF9F27", marginBottom: "12px" }}>
            <div className="s-box-title">Integration & API Layer</div>
            <div className="s-box-body">Amadeus · Duffel · Viator · HotelsPro · Trainline · Expedia · Rover · REST OpenAPIs</div>
          </div>
          <div className="s-box" style={{ borderLeft: "3px solid #1D9E75" }}>
            <div className="s-box-title">Data & Analytics</div>
            <div className="s-box-body">PostHog · Metabase · AWS S3 · Cloudflare R2 · Analytics Engine · Report Generator · Vault (Dry Bag)</div>
          </div>
        </div>
      </div>

      {/* Slide 5: Technology Stack */}
      <div className={slideClass(4)} id="tdm-s5">
        <div className="s-wrap">
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "16px" }}><span className="s-tag">Built to Scale</span></div>
          <h1 className="s-h1">Technology <em>Stack</em></h1>
          <div className="s-grid2">
            <div className="s-card">
              <div className="s-card-title">Frontend</div>
              <div className="s-card-body">Flutter (iOS/Android/Web) · React / Next.js</div>
            </div>
            <div className="s-card">
              <div className="s-card-title">AI / LLM</div>
              <div className="s-card-body">OpenAI GPT-4o · Anthropic Claude · Gemini · Perplexity</div>
            </div>
            <div className="s-card">
              <div className="s-card-title">Backend</div>
              <div className="s-card-body">Python FastAPI · Redis · PostgreSQL · CI/CD</div>
            </div>
            <div className="s-card">
              <div className="s-card-title">Messaging</div>
              <div className="s-card-body">Twilio · Email Webhooks · Notification Engine</div>
            </div>
            <div className="s-card">
              <div className="s-card-title">Payments</div>
              <div className="s-card-body">Stripe · Coinbase Commerce · Redsys · PayPal</div>
            </div>
            <div className="s-card">
              <div className="s-card-title">Hosting</div>
              <div className="s-card-body">AWS · Cloudflare · EU-hosted GDPR-compliant infra</div>
            </div>
            <div className="s-card">
              <div className="s-card-title">Docs / Vault</div>
              <div className="s-card-body">AWS S3 · Cloudflare R2 · Session Vault (Dry Bag)</div>
            </div>
            <div className="s-card">
              <div className="s-card-title">Analytics</div>
              <div className="s-card-body">PostHog · Metabase · Custom Reporting Engine</div>
            </div>
          </div>
          <p style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#4a6070", fontStyle: "italic" }}>EU-hosted, GDPR-compliant alternatives preferred across the stack to support regulatory alignment and future grant eligibility.</p>
        </div>
      </div>

      {/* Slide 6: Partner Ecosystem */}
      <div className={slideClass(5)} id="tdm-s6">
        <div className="s-wrap">
          <div className="s-eyebrow">Integrations</div>
          <h1 className="s-h1">Partner Ecosystem <em>& Integrations</em></h1>
          <div className="s-grid2">
            <div className="s-box">
              <div className="s-box-title">Travel Providers</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "12px" }}>
                <span className="s-pill">Amadeus</span><span className="s-pill">Duffel</span><span className="s-pill">HotelsPro</span><span className="s-pill">Viator</span><span className="s-pill">Trainline</span><span className="s-pill">Expedia</span><span className="s-pill">Booknbook</span><span className="s-pill">Ratehawk</span>
              </div>
            </div>
            <div className="s-box">
              <div className="s-box-title">AI Engines</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "12px" }}>
                <span className="s-pill">OpenAI GPT-4o</span><span className="s-pill">Anthropic Claude</span><span className="s-pill">Google Gemini</span><span className="s-pill">Perplexity</span><span className="s-pill">D-ID Avatar</span><span className="s-pill">UNITH</span>
              </div>
            </div>
            <div className="s-box">
              <div className="s-box-title">Data & Analytics</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "12px" }}>
                <span className="s-pill">AWS S3 / Glue</span><span className="s-pill">PostHog</span><span className="s-pill">Metabase</span><span className="s-pill">RateGain</span><span className="s-pill">Cloudflare R2</span><span className="s-pill">Tableau</span>
              </div>
            </div>
            <div className="s-box">
              <div className="s-box-title">Commerce & Payments</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "12px" }}>
                <span className="s-pill">Stripe</span><span className="s-pill">Coinbase Commerce</span><span className="s-pill">PayPal</span><span className="s-pill">Redsys</span><span className="s-pill">Twilio</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Slide 7: User Journey */}
      <div className={slideClass(6)} id="tdm-s7">
        <div className="s-wrap">
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "16px" }}><span className="s-tag">Sasha — OTA Agent</span></div>
          <div className="s-eyebrow">User Journey</div>
          <h1 className="s-h1">The Solo <em>Explorer</em></h1>
          <p className="s-sub">AI-guided end-to-end — from first intent to post-trip memory. All steps orchestrated by Sasha with live memory, messaging & vault.</p>
          <div className="s-grid3">
            <div className="s-card">
              <div className="s-card-title">01 — Intent Capture</div>
              <div className="s-card-body" style={{ marginBottom: "12px" }}><strong style={{ color: "#7ab8c8" }}>User:</strong> "I want a long weekend in Lisbon, mid-June, under €800"</div>
              <div className="s-card-body"><strong style={{ color: "#00E5C0" }}>Kanoe:</strong> Sasha activates, parses constraints, opens session memory</div>
            </div>
            <div className="s-card">
              <div className="s-card-title">02 — AI Itinerary Build</div>
              <div className="s-card-body" style={{ marginBottom: "12px" }}><strong style={{ color: "#7ab8c8" }}>User:</strong> Receives curated 3-day itinerary with flights, hotel & activities</div>
              <div className="s-card-body"><strong style={{ color: "#00E5C0" }}>Kanoe:</strong> Scoring engine ranks options; content composer renders preview</div>
            </div>
            <div className="s-card">
              <div className="s-card-title">03 — Live Pricing Check</div>
              <div className="s-card-body" style={{ marginBottom: "12px" }}><strong style={{ color: "#7ab8c8" }}>User:</strong> Sees real-time prices with availability indicators</div>
              <div className="s-card-body"><strong style={{ color: "#00E5C0" }}>Kanoe:</strong> API layer hits Amadeus, Duffel, HotelsPro; availability sync</div>
            </div>
            <div className="s-card">
              <div className="s-card-title">04 — One-Click Booking</div>
              <div className="s-card-body" style={{ marginBottom: "12px" }}><strong style={{ color: "#7ab8c8" }}>User:</strong> Confirms booking — pays by card, PayPal or crypto in one flow</div>
              <div className="s-card-body"><strong style={{ color: "#00E5C0" }}>Kanoe:</strong> Booking engine orchestrates calls; payment gateway handles transaction</div>
            </div>
            <div className="s-card">
              <div className="s-card-title">05 — Post-Booking Ops</div>
              <div className="s-card-body" style={{ marginBottom: "12px" }}><strong style={{ color: "#7ab8c8" }}>User:</strong> Receives confirmation, boarding pass & hotel voucher</div>
              <div className="s-card-body"><strong style={{ color: "#00E5C0" }}>Kanoe:</strong> Vault stores all docs; notification engine sends multi-channel alerts</div>
            </div>
            <div className="s-card">
              <div className="s-card-title">06 — Memory & Return</div>
              <div className="s-card-body" style={{ marginBottom: "12px" }}><strong style={{ color: "#7ab8c8" }}>User:</strong> "You went to Lisbon in June — fancy Porto next?"</div>
              <div className="s-card-body"><strong style={{ color: "#00E5C0" }}>Kanoe:</strong> Session memory recalls preferences; post-booking engine flags re-pricing</div>
            </div>
          </div>
          <div className="s-box" style={{ textAlign: "center" }}>
            <div className="s-box-body">Always on: Session Memory · Messaging Engine · Vault (Dry Bag) · Notification Engine · Analytics · Human-in-Loop escalation</div>
          </div>
        </div>
      </div>

      {/* Slide 8: Roadmap */}
      <div className={slideClass(7)} id="tdm-s8">
        <div className="s-wrap">
          <div className="s-eyebrow">Roadmap Horizon</div>
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "16px" }}><span className="s-tag">Product Roadmap v1.0</span></div>
          <h1 className="s-h1" style={{ fontSize: "56px" }}>Now, next,<br /><em>later.</em></h1>
          <div className="s-grid3" style={{ marginTop: "32px" }}>
            <div className="s-roadmap-col">
              <div className="s-roadmap-title">Now</div>
              <div className="s-roadmap-sub">May–Jun 2026</div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">01</div><div className="s-roadmap-text">Multi-currency & API layer <span className="s-badge s-badge-live">Live</span></div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">02</div><div className="s-roadmap-text">Agentic agent framework <span className="s-badge s-badge-flight">In Flight</span></div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">03</div><div className="s-roadmap-text">Booking engine & webhooks <span className="s-badge s-badge-flight">In Flight</span></div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">04</div><div className="s-roadmap-text">B2B white-label dashboard <span className="s-badge s-badge-qa">In QA</span></div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">05</div><div className="s-roadmap-text">Stripe + crypto payment rails <span className="s-badge s-badge-soon">Coming</span></div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">06</div><div className="s-roadmap-text">Notifications & vault <span className="s-badge s-badge-qa">Ready for QA</span></div></div>
            </div>
            <div className="s-roadmap-col">
              <div className="s-roadmap-title">Next</div>
              <div className="s-roadmap-sub">Jul–Sep 2026</div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">01</div><div className="s-roadmap-text">API Hub connectors — Amadeus, Duffel, Viator, and 52 others</div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">02</div><div className="s-roadmap-text">Production environment & GCP hardening</div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">03</div><div className="s-roadmap-text">Admin dashboard & KYC onboarding</div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">04</div><div className="s-roadmap-text">Dispute resolution & partial refunds</div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">05</div><div className="s-roadmap-text">Group & niche traveller journey flows</div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">06</div><div className="s-roadmap-text">2–4 paid pilot client launches</div></div>
            </div>
            <div className="s-roadmap-col">
              <div className="s-roadmap-title">Later</div>
              <div className="s-roadmap-sub">Q4 '26 → Q3 '27</div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">01</div><div className="s-roadmap-text">Added banking partner finalisations</div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">02</div><div className="s-roadmap-text">Crypto settlement corridor scale</div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">03</div><div className="s-roadmap-text">FX optimisation & AI routing</div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">04</div><div className="s-roadmap-text">Accounting connectors (NetSuite)</div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">05</div><div className="s-roadmap-text">International expansion: UAE - SEA</div></div>
              <div className="s-roadmap-item"><div className="s-roadmap-num">06</div><div className="s-roadmap-text">Tokenised credit & receivables</div></div>
            </div>
          </div>
        </div>
      </div>

      {/* Slide 9: Unfair Advantages */}
      <div className={slideClass(8)} id="tdm-s9">
        <div className="s-wrap">
          <div className="s-eyebrow">Why Kanoe.ai Wins</div>
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "16px" }}><span className="s-tag">Why Kanoe.ai Wins</span></div>
          <h1 className="s-h1">Unfair <em>Advantages</em></h1>
          <div className="s-grid3">
            <div className="s-card">
              <div className="s-card-icon">🧠</div>
              <div className="s-card-title">Agentic AI-First</div>
              <div className="s-card-body">Not a chatbot. Four specialist agents autonomously execute end-to-end travel workflows. Search, book, notify, optimise.</div>
            </div>
            <div className="s-card">
              <div className="s-card-icon">🔗</div>
              <div className="s-card-title">Unified API Infrastructure</div>
              <div className="s-card-body">Single integration replacing 10+ point solutions. One contract, one SDK, all major inventory sources.</div>
            </div>
            <div className="s-card">
              <div className="s-card-icon">₿</div>
              <div className="s-card-title">Crypto-Native Settlement</div>
              <div className="s-card-body">Only travel OS with native crypto payment rails. B2B + B2C settlement, a massive unserved market.</div>
            </div>
            <div className="s-card">
              <div className="s-card-icon">📈</div>
              <div className="s-card-title">Post-Booking Optimisation</div>
              <div className="s-card-body">AI continues working after confirmation: re-pricing, alerts, memory recall, vault. Revenue beyond the booking.</div>
            </div>
            <div className="s-card">
              <div className="s-card-icon">🏷️</div>
              <div className="s-card-title">White-Label B2B</div>
              <div className="s-card-body">OTAs, ITAs, DMCs deploy under their own brand. Multi-tenant, branding config, and analytics built in from day one.</div>
            </div>
            <div className="s-card">
              <div className="s-card-icon">🚀</div>
              <div className="s-card-title">Speed to Market</div>
              <div className="s-card-body">MVP validated on Base44. v3 UI complete. First pilots scoped. Seed capital funds direct product-market fit acceleration.</div>
            </div>
          </div>
        </div>
      </div>

      {/* Slide 10: CTA */}
      <div className={slideClass(9)} id="tdm-s10">
        <div className="s-wrap">
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "16px" }}><span className="s-tag">Engineering</span></div>
          <h1 className="s-h1">Agent <em>Architecture</em></h1>
          <p className="tdm-sub">One Conductor. Hundreds of Specialist Agents. Zero inter-agent confusion.</p>
          <div className="s-grid2" style={{ alignItems: "start", gap: "32px" }}>
            <div>
              <div style={{ fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase", color: "#00E5C0", fontWeight: "700", marginBottom: "14px" }}>How It Works</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                <div style={{ padding: "10px 14px", borderRadius: "8px", background: "#00E5C0", color: "#040D1A", fontSize: "12px", fontWeight: "700", textAlign: "center" }}>Sasha — AI Concierge Interface</div>
                <div style={{ textAlign: "center", fontSize: "16px", color: "#7ab8c8" }}>↓</div>
                <div style={{ padding: "10px 14px", borderRadius: "8px", background: "rgba(0,229,192,0.12)", border: "1px solid #00E5C0", color: "#00E5C0", fontSize: "12px", fontWeight: "700", textAlign: "center" }}>The Conductor — Intent Router</div>
                <div style={{ textAlign: "center", fontSize: "13px", color: "#7ab8c8" }}>↓ routes in parallel ↓</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "6px" }}>
                  <div style={{ padding: "8px", borderRadius: "7px", background: "rgba(255,255,255,.05)", border: "1px solid rgba(255,255,255,.1)", fontSize: "10px", color: "#7ab8c8", textAlign: "center" }}>⛳ Golf<br />Agent</div>
                  <div style={{ padding: "8px", borderRadius: "7px", background: "rgba(255,255,255,.05)", border: "1px solid rgba(255,255,255,.1)", fontSize: "10px", color: "#7ab8c8", textAlign: "center" }}>💆 Beauty<br />Agent</div>
                  <div style={{ padding: "8px", borderRadius: "7px", background: "rgba(255,255,255,.05)", border: "1px solid rgba(255,255,255,.1)", fontSize: "10px", color: "#7ab8c8", textAlign: "center" }}>📸 Foto<br />Agent</div>
                  <div style={{ padding: "8px", borderRadius: "7px", background: "rgba(255,255,255,.05)", border: "1px solid rgba(255,255,255,.1)", fontSize: "10px", color: "#7ab8c8", textAlign: "center" }}>🍽 Restaurant<br />Agent</div>
                  <div style={{ padding: "8px", borderRadius: "7px", background: "rgba(255,255,255,.05)", border: "1px solid rgba(255,255,255,.1)", fontSize: "10px", color: "#7ab8c8", textAlign: "center" }}>🏥 Health<br />Agent</div>
                  <div style={{ padding: "8px", borderRadius: "7px", background: "rgba(255,255,255,.03)", border: "1px dashed rgba(255,255,255,.15)", fontSize: "10px", color: "#4a6070", textAlign: "center" }}>+ 100s<br />more</div>
                </div>
                <div style={{ textAlign: "center", fontSize: "13px", color: "#7ab8c8" }}>↓ merged response ↓</div>
                <div style={{ padding: "10px 14px", borderRadius: "8px", background: "rgba(0,229,192,0.06)", border: "1px solid rgba(0,229,192,.2)", fontSize: "12px", color: "#fff", textAlign: "center" }}>One seamless Sasha reply</div>
              </div>
            </div>
            <div>
              <div style={{ fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase", color: "#00E5C0", fontWeight: "700", marginBottom: "14px" }}>Design Principles</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                <div style={{ background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.1)", borderRadius: "10px", padding: "12px 14px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#fff", marginBottom: "4px" }}>Specialists, Not Generalists</div>
                  <div style={{ fontSize: "12px", color: "#7ab8c8", lineHeight: "1.5" }}>Each agent has one job. It knows its domain, its data sources, and nothing else — no confusion, no hallucination drift.</div>
                </div>
                <div style={{ background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.1)", borderRadius: "10px", padding: "12px 14px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#fff", marginBottom: "4px" }}>Agents Never Talk to Each Other</div>
                  <div style={{ fontSize: "12px", color: "#7ab8c8", lineHeight: "1.5" }}>All communication flows through The Conductor. Keeps context clean and prevents compounding errors.</div>
                </div>
                <div style={{ background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.1)", borderRadius: "10px", padding: "12px 14px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#fff", marginBottom: "4px" }}>Parallel Execution</div>
                  <div style={{ fontSize: "12px", color: "#7ab8c8", lineHeight: "1.5" }}>Multiple agents fire simultaneously via asyncio. Golf + spa query = both answers in one response, not two turns.</div>
                </div>
                <div style={{ background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.1)", borderRadius: "10px", padding: "12px 14px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#fff", marginBottom: "4px" }}>No APIs Required</div>
                  <div style={{ fontSize: "12px", color: "#7ab8c8", lineHeight: "1.5" }}>Agents use web scraping, email agents, and WhatsApp bots — plugging into the real world without vendor API access.</div>
                </div>
              </div>
            </div>
          </div>
          <div style={{ background: "rgba(0,229,192,0.05)", border: "1px solid rgba(0,229,192,.2)", borderRadius: "10px", padding: "12px 16px", fontSize: "12px", color: "#00E5C0", fontStyle: "italic", marginTop: "16px" }}>Adding a new capability = one new agent file + one line in the registry. No changes to The Conductor, no changes to Sasha.</div>
        </div>
      </div>
      <div className={slideClass(10)} id="tdm-s11">
        <div className="s-wrap">
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "16px" }}><span className="s-tag">Engineering</span></div>
          <h1 className="s-h1">Token Cost <em>Optimisation</em></h1>
          <p className="tdm-sub">Three-level architecture targets $0.02–$0.05 per full conversation end-to-end</p>
          <div className="s-grid2" style={{ alignItems: "start", gap: "32px" }}>
            <div>
              <div style={{ fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase", color: "#00E5C0", fontWeight: "700", marginBottom: "14px" }}>LLM Routing by Task</div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid rgba(255,255,255,.1)" }}>
                    <th style={{ textAlign: "left", padding: "6px 8px", color: "#7ab8c8", fontWeight: "600" }}>Task</th>
                    <th style={{ textAlign: "left", padding: "6px 8px", color: "#7ab8c8", fontWeight: "600" }}>Model</th>
                    <th style={{ textAlign: "right", padding: "6px 8px", color: "#7ab8c8", fontWeight: "600" }}>Est. Cost</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style={{ borderBottom: "1px solid rgba(255,255,255,.06)" }}><td style={{ padding: "7px 8px", color: "#fff" }}>Intent classification</td><td style={{ padding: "7px 8px", color: "#00E5C0" }}>Haiku</td><td style={{ padding: "7px 8px", textAlign: "right", color: "#7ab8c8" }}>$0.0001</td></tr>
                  <tr style={{ borderBottom: "1px solid rgba(255,255,255,.06)" }}><td style={{ padding: "7px 8px", color: "#fff" }}>Web search / contact lookup</td><td style={{ padding: "7px 8px", color: "#00E5C0" }}>Haiku</td><td style={{ padding: "7px 8px", textAlign: "right", color: "#7ab8c8" }}>$0.0008</td></tr>
                  <tr style={{ borderBottom: "1px solid rgba(255,255,255,.06)" }}><td style={{ padding: "7px 8px", color: "#fff" }}>RAG retrieval</td><td style={{ padding: "7px 8px", color: "#00E5C0" }}>Haiku</td><td style={{ padding: "7px 8px", textAlign: "right", color: "#7ab8c8" }}>$0.0002</td></tr>
                  <tr style={{ borderBottom: "1px solid rgba(255,255,255,.06)" }}><td style={{ padding: "7px 8px", color: "#fff" }}>Agent tool use loop</td><td style={{ padding: "7px 8px", color: "#ffc800" }}>Sonnet</td><td style={{ padding: "7px 8px", textAlign: "right", color: "#7ab8c8" }}>$0.008</td></tr>
                  <tr style={{ borderBottom: "1px solid rgba(255,255,255,.06)" }}><td style={{ padding: "7px 8px", color: "#fff" }}>Response synthesis</td><td style={{ padding: "7px 8px", color: "#ffc800" }}>Sonnet</td><td style={{ padding: "7px 8px", textAlign: "right", color: "#7ab8c8" }}>$0.004</td></tr>
                  <tr style={{ background: "rgba(0,229,192,.08)", borderRadius: "6px" }}><td style={{ padding: "8px", color: "#fff", fontWeight: "700" }}>Full conversation (blended)</td><td style={{ padding: "8px", color: "#7ab8c8" }}>Mixed</td><td style={{ padding: "8px", textAlign: "right", color: "#00E5C0", fontWeight: "700" }}>$0.02–$0.05</td></tr>
                </tbody>
              </table>
              <div style={{ marginTop: "10px", fontSize: "11px", color: "#4a6070", fontStyle: "italic" }}>Move to AWS Bedrock when first enterprise B2B client lands — enabling compliance docs + volume pricing.</div>
            </div>
            <div>
              <div style={{ fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase", color: "#00E5C0", fontWeight: "700", marginBottom: "14px" }}>Three Levels of Intelligence</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                <div style={{ padding: "14px", borderRadius: "8px", background: "#00E5C0", color: "#040D1A" }}>
                  <div style={{ fontSize: "11px", fontWeight: "700", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "4px" }}>Level 1 — Prompt Engineering</div>
                  <div style={{ fontSize: "11px" }}>System prompts scope each agent to client inventory. Fast, flexible, already live. No retraining.</div>
                </div>
                <div style={{ padding: "14px", borderRadius: "8px", background: "rgba(0,229,192,0.12)", border: "1px solid rgba(0,229,192,.35)" }}>
                  <div style={{ fontSize: "11px", fontWeight: "700", letterSpacing: "0.1em", textTransform: "uppercase", color: "#00E5C0", marginBottom: "4px" }}>Level 2 — RAG / pgvector (Next)</div>
                  <div style={{ fontSize: "11px", color: "#7ab8c8" }}>Client inventory in Supabase vector DB. Retrieval injects only relevant context — scales to thousands of locations without bloating prompts.</div>
                </div>
                <div style={{ padding: "14px", borderRadius: "8px", background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.1)" }}>
                  <div style={{ fontSize: "11px", fontWeight: "700", letterSpacing: "0.1em", textTransform: "uppercase", color: "#4a6070", marginBottom: "4px" }}>Level 3 — Fine-Tuning (Future)</div>
                  <div style={{ fontSize: "11px", color: "#4a6070" }}>Model trained on client-specific data. Reserved for enterprise tier. Levels 1+2 deliver 90% of value for most OTA deployments.</div>
                </div>
              </div>
              <div style={{ background: "rgba(0,229,192,0.05)", border: "1px solid rgba(0,229,192,.2)", borderRadius: "10px", padding: "12px 14px", fontSize: "12px", color: "#00E5C0", fontStyle: "italic", marginTop: "12px" }}>Cheap tasks run on Haiku. Complex synthesis on Sonnet. Prompt caching further reduces cost on repeat queries.</div>
            </div>
          </div>
        </div>
      </div>

      {/* Slide 13: Smart Sasha */}
      <div className={slideClass(11)} id="tdm-s12">
        <div className="s-wrap">
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "16px" }}><span className="s-tag">Product</span></div>
          <h1 className="s-h1">Smart <em>Sasha</em></h1>
          <p style={{ fontFamily: "DM Sans,sans-serif", fontSize: "14px", color: "#7ab8c8", margin: "0 0 24px", lineHeight: "1.6" }}>Fuzzy inputs. Instant parallel search. Progressive refinement. No interrogation.</p>
          <div className="s-grid2" style={{ alignItems: "start", gap: "32px" }}>
            <div>
              <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "13px", fontWeight: "700", color: "#00E5C0", letterSpacing: ".08em", textTransform: "uppercase", marginBottom: "14px" }}>How It Works</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <div style={{ background: "rgba(0,229,192,.08)", border: "1px solid rgba(0,229,192,.25)", borderRadius: "10px", padding: "12px 14px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#00E5C0", marginBottom: "4px" }}>1 — Extract</div>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#7ab8c8", lineHeight: "1.5" }}>"Western Europe, this summer, business class, cheapest" — origin, cabin, goal extracted. Duration and destination flagged as fuzzy.</div>
                </div>
                <div style={{ background: "rgba(0,229,192,.08)", border: "1px solid rgba(0,229,192,.25)", borderRadius: "10px", padding: "12px 14px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#00E5C0", marginBottom: "4px" }}>2 — Assume and Search</div>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#7ab8c8", lineHeight: "1.5" }}>Smart defaults applied. 12 parallel searches fire instantly: ORD to LHR, CDG, AMS, FRA across 3 date windows.</div>
                </div>
                <div style={{ background: "rgba(0,229,192,.08)", border: "1px solid rgba(0,229,192,.25)", borderRadius: "10px", padding: "12px 14px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#00E5C0", marginBottom: "4px" }}>3 — Ask One Question</div>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#7ab8c8", lineHeight: "1.5" }}>While searches run: "How long are you thinking?" Highest-impact unknown only. Never an interrogation.</div>
                </div>
                <div style={{ background: "rgba(0,229,192,.08)", border: "1px solid rgba(0,229,192,.25)", borderRadius: "10px", padding: "12px 14px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#00E5C0", marginBottom: "4px" }}>4 — Rank and Refine</div>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#7ab8c8", lineHeight: "1.5" }}>Results scored by price, quality floor, flight duration, points value. Top 3 options surfaced. Refine conversationally.</div>
                </div>
              </div>
            </div>
            <div>
              <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "13px", fontWeight: "700", color: "#00E5C0", letterSpacing: ".08em", textTransform: "uppercase", marginBottom: "14px" }}>Scoring Engine</div>
              <div style={{ background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.1)", borderRadius: "10px", padding: "14px 16px", marginBottom: "14px" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#fff" }}>Total price</span>
                    <span style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#00E5C0" }}>40%</span>
                  </div>
                  <div style={{ background: "rgba(0,229,192,.15)", borderRadius: "4px", height: "4px" }}><div style={{ background: "#00E5C0", height: "4px", borderRadius: "4px", width: "40%" }}></div></div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "4px" }}>
                    <span style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#fff" }}>Quality floor met</span>
                    <span style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#00E5C0" }}>20%</span>
                  </div>
                  <div style={{ background: "rgba(0,229,192,.15)", borderRadius: "4px", height: "4px" }}><div style={{ background: "#00E5C0", height: "4px", borderRadius: "4px", width: "20%" }}></div></div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "4px" }}>
                    <span style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#fff" }}>Flight duration</span>
                    <span style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#00E5C0" }}>15%</span>
                  </div>
                  <div style={{ background: "rgba(0,229,192,.15)", borderRadius: "4px", height: "4px" }}><div style={{ background: "#00E5C0", height: "4px", borderRadius: "4px", width: "15%" }}></div></div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "4px" }}>
                    <span style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#fff" }}>Points value</span>
                    <span style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#00E5C0" }}>15%</span>
                  </div>
                  <div style={{ background: "rgba(0,229,192,.15)", borderRadius: "4px", height: "4px" }}><div style={{ background: "#00E5C0", height: "4px", borderRadius: "4px", width: "15%" }}></div></div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "4px" }}>
                    <span style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#fff" }}>Airline preference</span>
                    <span style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#00E5C0" }}>10%</span>
                  </div>
                  <div style={{ background: "rgba(0,229,192,.15)", borderRadius: "4px", height: "4px" }}><div style={{ background: "#00E5C0", height: "4px", borderRadius: "4px", width: "10%" }}></div></div>
                </div>
              </div>
              <div style={{ background: "rgba(0,229,192,.05)", border: "1px solid rgba(0,229,192,.2)", borderRadius: "10px", padding: "12px 14px" }}>
                <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#00E5C0", fontStyle: "italic", lineHeight: "1.5" }}>No travel platform does this today. Google Flights searches. Kayak compares. Smart Sasha optimizes — conversationally, in real time, for your specific situation.</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Slide 14: Credit Card Intelligence */}
      <div className={slideClass(12)} id="tdm-s13">
        <div className="s-wrap">
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "16px" }}><span className="s-tag">Product</span></div>
          <h1 className="s-h1">Credit Card <em>Intelligence</em></h1>
          <p style={{ fontFamily: "DM Sans,sans-serif", fontSize: "14px", color: "#7ab8c8", margin: "0 0 20px", lineHeight: "1.6" }}>Sasha knows your cards, your points, your benefits — and your rental car coverage. She optimizes every transaction automatically.</p>
          <div className="s-grid2" style={{ alignItems: "start", gap: "28px" }}>

            {/* Left: Three live examples */}
            <div>
              <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "13px", fontWeight: "700", color: "#00E5C0", letterSpacing: ".08em", textTransform: "uppercase", marginBottom: "14px" }}>Live Examples</div>

              {/* Example 1: Flight */}
              <div style={{ background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.1)", borderRadius: "10px", padding: "12px 14px", marginBottom: "10px" }}>
                <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", fontWeight: "700", color: "#7ab8c8", marginBottom: "6px" }}>FLIGHT PURCHASE</div>
                <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#4a6070", marginBottom: "6px", fontStyle: "italic" }}>"Which card for my Lufthansa flight to London?"</div>
                <div style={{ background: "rgba(0,229,192,.08)", border: "1px solid rgba(0,229,192,.2)", borderRadius: "6px", padding: "8px 10px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#00E5C0", fontWeight: "700", marginBottom: "3px" }}>Use Amex Platinum — 5x points</div>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#7ab8c8", lineHeight: "1.5" }}>5,000 MR points worth ~$100. Effective cost $900 not $1,000. Chase Sapphire earns only 3x — $55 less value.</div>
                </div>
              </div>

              {/* Example 2: Car rental */}
              <div style={{ background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.1)", borderRadius: "10px", padding: "12px 14px", marginBottom: "10px" }}>
                <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", fontWeight: "700", color: "#7ab8c8", marginBottom: "6px" }}>RENTAL CAR INSURANCE</div>
                <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#4a6070", marginBottom: "6px", fontStyle: "italic" }}>"Renting in Italy 5 days — should I take the insurance?"</div>
                <div style={{ background: "rgba(0,229,192,.08)", border: "1px solid rgba(0,229,192,.2)", borderRadius: "6px", padding: "8px 10px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#00E5C0", fontWeight: "700", marginBottom: "3px" }}>Decline CDW — Chase Sapphire Reserve covers you</div>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#7ab8c8", lineHeight: "1.5" }}>PRIMARY coverage in Italy. Save EUR 100-150. Add supplemental liability only — card does not cover third-party damage.</div>
                </div>
              </div>

              {/* Example 3: Full trip */}
              <div style={{ background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.1)", borderRadius: "10px", padding: "12px 14px" }}>
                <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", fontWeight: "700", color: "#7ab8c8", marginBottom: "6px" }}>FULL TRIP STRATEGY</div>
                <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#4a6070", marginBottom: "6px", fontStyle: "italic" }}>"Paris trip — flight $2k, hotel $1.5k, dining $400, transport $150"</div>
                <div style={{ background: "rgba(0,229,192,.08)", border: "1px solid rgba(0,229,192,.2)", borderRadius: "6px", padding: "8px 10px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#00E5C0", fontWeight: "700", marginBottom: "3px" }}>$292 in points value identified automatically</div>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#7ab8c8", lineHeight: "1.5" }}>Amex Platinum for flight (5x). Chase Sapphire Reserve for hotel, dining, transport (3x + $300 travel credit).</div>
                </div>
              </div>
            </div>

            {/* Right: Capabilities + integration */}
            <div>
              <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "13px", fontWeight: "700", color: "#00E5C0", letterSpacing: ".08em", textTransform: "uppercase", marginBottom: "14px" }}>What Sasha Optimizes</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginBottom: "14px" }}>
                <div style={{ background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.1)", borderRadius: "8px", padding: "10px 12px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#fff", marginBottom: "3px" }}>Points earn rate per transaction</div>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#7ab8c8", lineHeight: "1.5" }}>Highest-earning card per category — flights, hotels, dining, transport, rent.</div>
                </div>
                <div style={{ background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.1)", borderRadius: "8px", padding: "10px 12px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#fff", marginBottom: "3px" }}>Annual credits before expiry</div>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#7ab8c8", lineHeight: "1.5" }}>Tracks unused $200 airline, $300 travel, hotel credits — routes spending to use them.</div>
                </div>
                <div style={{ background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.1)", borderRadius: "8px", padding: "10px 12px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#fff", marginBottom: "3px" }}>Transfer partner optimization</div>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#7ab8c8", lineHeight: "1.5" }}>14 airline + hotel partners per card. Finds highest-value redemption path automatically.</div>
                </div>
                <div style={{ background: "rgba(255,255,255,.04)", border: "1px solid rgba(0,229,192,.2)", borderRadius: "8px", padding: "10px 12px", borderLeft: "3px solid #00E5C0" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", fontWeight: "700", color: "#00E5C0", marginBottom: "3px" }}>Rental car insurance coverage</div>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#7ab8c8", lineHeight: "1.5" }}>Knows exactly what each card covers by country, vehicle type, and rental days. Tells you what to decline at the counter.</div>
                </div>
              </div>

              {/* Pull quote */}
              <div style={{ background: "rgba(0,229,192,.06)", border: "1px solid rgba(0,229,192,.25)", borderRadius: "10px", padding: "14px 16px", marginBottom: "12px" }}>
                <div style={{ fontFamily: "DM Serif Display,serif", fontSize: "15px", color: "#00E5C0", lineHeight: "1.5", marginBottom: "6px" }}>"On a $4,050 Paris trip Sasha identified $292 in points value across three cards — automatically."</div>
                <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", color: "#4a6070" }}>Real result from live system test, June 2026</div>
              </div>

              {/* Integration badges */}
              <div style={{ background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.1)", borderRadius: "8px", padding: "10px 12px" }}>
                <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "11px", fontWeight: "700", color: "#7ab8c8", letterSpacing: ".06em", textTransform: "uppercase", marginBottom: "8px" }}>Integration</div>
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                  <span style={{ background: "rgba(0,229,192,.1)", border: "1px solid rgba(0,229,192,.25)", borderRadius: "6px", fontFamily: "DM Sans,sans-serif", fontSize: "10px", color: "#00E5C0", padding: "3px 8px" }}>Plaid (optional)</span>
                  <span style={{ background: "rgba(0,229,192,.1)", border: "1px solid rgba(0,229,192,.25)", borderRadius: "6px", fontFamily: "DM Sans,sans-serif", fontSize: "10px", color: "#00E5C0", padding: "3px 8px" }}>10-card benefits DB</span>
                  <span style={{ background: "rgba(0,229,192,.1)", border: "1px solid rgba(0,229,192,.25)", borderRadius: "6px", fontFamily: "DM Sans,sans-serif", fontSize: "10px", color: "#00E5C0", padding: "3px 8px" }}>Points valuation engine</span>
                  <span style={{ background: "rgba(0,229,192,.1)", border: "1px solid rgba(0,229,192,.25)", borderRadius: "6px", fontFamily: "DM Sans,sans-serif", fontSize: "10px", color: "#00E5C0", padding: "3px 8px" }}>Rental coverage DB</span>
                  <span style={{ background: "rgba(0,229,192,.1)", border: "1px solid rgba(0,229,192,.25)", borderRadius: "6px", fontFamily: "DM Sans,sans-serif", fontSize: "10px", color: "#00E5C0", padding: "3px 8px" }}>Transfer partner map</span>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>

      <div className={slideClass(13)} id="tdm-s14">
        <div className="s-wrap" style={{ display: "flex", flexDirection: "column", justifyContent: "center", minHeight: "calc(100vh - 66px)" }}>
          <div style={{ textAlign: "center", maxWidth: "700px", margin: "0 auto" }}>
            <div style={{ marginBottom: "32px" }}>
              <span style={{ fontFamily: "DM Sans,sans-serif", fontSize: "32px", fontWeight: "800", color: "#00E5C0", letterSpacing: "-1px" }}>KANOE</span><span style={{ fontFamily: "DM Sans,sans-serif", fontSize: "32px", fontWeight: "300", color: "#fff" }}>.ai</span>
            </div>
            <h1 style={{ fontFamily: "DM Serif Display,serif", fontSize: "36px", color: "#fff", margin: "0 0 12px", lineHeight: "1.2" }}>Kanoe.ai is building the<br />operating system for travel.</h1>
            <div style={{ display: "flex", justifyContent: "center", gap: "16px", margin: "24px 0 40px", flexWrap: "wrap" }}>
              <span className="s-pill">AI-first</span><span className="s-pill">Crypto-native</span><span className="s-pill">B2B infrastructure</span><span className="s-pill">Agentic</span>
            </div>
            <div className="s-grid3" style={{ maxWidth: "600px", margin: "0 auto 40px" }}>
              <div className="s-card" style={{ textAlign: "center" }}>
                <div style={{ fontFamily: "DM Serif Display,serif", fontSize: "28px", color: "#00E5C0" }}>Open</div>
                <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#7ab8c8", marginTop: "4px" }}>Seed Round</div>
              </div>
              <div className="s-card" style={{ textAlign: "center" }}>
                <div style={{ fontFamily: "DM Serif Display,serif", fontSize: "28px", color: "#00E5C0" }}>MVP v3</div>
                <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#7ab8c8", marginTop: "4px" }}>Platform — Demo ready</div>
              </div>
              <div className="s-card" style={{ textAlign: "center" }}>
                <div style={{ fontFamily: "DM Serif Display,serif", fontSize: "28px", color: "#00E5C0" }}>2–4</div>
                <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#7ab8c8", marginTop: "4px" }}>Pilots in scope</div>
              </div>
            </div>
            <a href="mailto:jon@kanoe.ai" style={{ display: "inline-block", background: "#00E5C0", color: "#040D1A", fontFamily: "DM Sans,sans-serif", fontSize: "15px", fontWeight: "700", padding: "14px 36px", borderRadius: "8px", textDecoration: "none" }}>Contact — jon@kanoe.ai</a>
          </div>
        </div>
      </div>


      {/* Nav */}
      
      {/* Carousel controls. The original tracked the index in a module-level var and rebuilt
          the dots by hand on every render; the index is state here and the dots fall out of it. */}
      <div className="tdm-nav">
        <button onClick={() => nav(-1)} aria-label="Previous slide">← Prev</button>
        <div id="tdm-dots" style={{ display: 'flex', gap: 8 }}>
          {Array.from({ length: TOTAL }, (_, i) => (
            <button
              key={i}
              className={`tdm-dot${i === idx ? ' active' : ''}`}
              onClick={() => setIdx(i)}
              aria-label={`Go to slide ${i + 1}`}
              aria-current={i === idx ? 'true' : undefined}
            />
          ))}
        </div>
        <span className="tdm-count" id="tdm-count">{idx + 1} / {TOTAL}</span>
        <button onClick={() => nav(1)} aria-label="Next slide">Next →</button>
      </div>
    </div>
  )
}
