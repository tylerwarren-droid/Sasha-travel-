// Teaser panel of the investor portal, ported from the original standalone document.
// Static content: no client-side behaviour, so this stays a server component.

export default function Teaser() {
  return (
      <div className="panel active" id="panel-teaser">
        <div className="t-hero">
          <div>
            <h1 className="t-h1">The <em>Operating System</em> for Travel</h1>
            <p className="t-sub">Kanoe.ai is an AI-first, crypto-native infrastructure layer for the B2B and D2C travel market — consolidating booking, itinerary management, operations, payments, and analytics into a single deployable platform. Operators go live in days, not months.</p>
          </div>
          <div className="t-vis">
            <div className="stat-grid">
              <div className="stat"><div className="stat-n">$11.4T</div><div className="stat-l">Global Travel TAM 2028</div></div>
              <div className="stat"><div className="stat-n">$780B</div><div className="stat-l">B2B Travel Tech TAM</div></div>
              <div className="stat"><div className="stat-n">62%</div><div className="stat-l">Agents use 3+ tools</div></div>
            </div>
          </div>
        </div>
        <div className="t-sec">
          <div className="sec-h">Five Defensible Differentiators</div>
          <div className="pillars">
            <div className="pillar"><div className="p-num">01</div><div className="p-t">Avatar LLM Interface</div><div className="p-d">Coded-parameter AI concierge personas with operator-scoped guardrails</div></div>
            <div className="pillar"><div className="p-num">02</div><div className="p-t">Booking Engine</div><div className="p-d">End-to-end dynamic booking from Amadeus, HotelsPro, Travolutionary in one prompt</div></div>
            <div className="pillar"><div className="p-num">03</div><div className="p-t">Crypto-Native</div><div className="p-d">Stablecoin settlement baked in — eliminates 30–60 day settlement lag</div></div>
            <div className="pillar"><div className="p-num">04</div><div className="p-t">Alt Data Analytics</div><div className="p-d">Behavioural dataset becomes licensable alternative data — a second revenue stream</div></div>
            <div className="pillar"><div className="p-num">05</div><div className="p-t">Agentic Ops</div><div className="p-d">Autonomous post-booking: amendments, supplier comms, care escalations</div></div>
          </div>
          <div className="sec-h">Revenue Model</div>
          <div className="rev-grid">
            <div className="rc"><div className="rc-pct">40%</div><div><h4>PaaS Subscriptions</h4><p>Monthly/annual platform fees tiered by volume. Gross margin 68–72%.</p></div></div>
            <div className="rc"><div className="rc-pct">35%</div><div><h4>Transaction Commission</h4><p>Per-booking margin on hotel, flight, and activity inventory (0.5–3%).</p></div></div>
            <div className="rc"><div className="rc-pct">15%</div><div><h4>API Access Fees</h4><p>Usage-based pricing for DMC and white-label partners.</p></div></div>
            <div className="rc"><div className="rc-pct">10%</div><div><h4>Premium AI & Alt Data</h4><p>Price monitoring, AI advisor, dynamic pricing, and data licensing.</p></div></div>
          </div>
          <div className="ask-box">
            <div className="ask-row">
              <div className="ask-item"><div className="ap">45%</div><div className="al">Engineering</div></div>
              <div className="ask-item"><div className="ap">30%</div><div className="al">Sales & GTM</div></div>
              <div className="ask-item"><div className="ap">15%</div><div className="al">Infrastructure</div></div>
              <div className="ask-item"><div className="ap">10%</div><div className="al">Operations</div></div>
            </div>
          </div>
        </div>
      </div>
  )
}
