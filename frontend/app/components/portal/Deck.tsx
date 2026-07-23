// Investor deck panel of the investor portal, ported from the original standalone document.
// Static content: no client-side behaviour, so this stays a server component.

export default function Deck() {
  return (
      <div className="panel active" id="panel-deck">
        <div className="deck-hdr"><h2>Investor Presentation · 2026</h2><p>Confidential — for partner and investor review only · 15 slides</p></div>
        <div className="slides">
          <div className="slide"><div className="si" style={{ background: "linear-gradient(135deg,var(--navy2),var(--navy4))", textAlign: "center", padding: "60px 40px" }}>
            <img src="/portal/logo.jpg" alt="Kanoe.ai" style={{ height: "56px", marginBottom: "20px" }} />
            <div style={{ fontSize: "12px", letterSpacing: "0.22em", textTransform: "uppercase", color: "var(--teal)", marginBottom: "14px" }}>The Operating System for Travel</div>
            <div style={{ fontSize: "14px", color: "var(--muted)" }}>Powering OTAs · Travel Agents · DMCs with AI and Crypto-native infrastructure</div>
            <div style={{ marginTop: "18px", fontSize: "11px", color: "rgba(123,173,160,0.35)", letterSpacing: "0.1em" }}>INVESTOR PRESENTATION · 2026</div>
          </div></div>
          <div className="slide"><div className="si"><div className="sn">02 / 15</div><div className="st">The Problem</div><div className="ss">The travel industry, seemingly stuck in the early 2000s, runs on fragmented, disparate legacy infrastructure</div>
            <div className="g3"><div className="card"><div className="card-i">⟨⟩</div><div className="card-t">Fragmented APIs</div><div className="card-d">OTAs and agents juggle 10+ disconnected GDS, hotel, and airline APIs with no unified layer, impacting margins and burning engineering budget</div></div>
            <div className="card"><div className="card-i">⚙️</div><div className="card-t">No Intelligence Layer</div><div className="card-d">Manual booking workflows lack AI-driven recommendations, dynamic itinerary creation, blockchain-enabled payments, and post-booking optimization</div></div>
            <div className="card"><div className="card-i">👤</div><div className="card-t">Underserved B2B Market</div><div className="card-d">Travel Agents and DMCs are forced onto consumer platforms — no enterprise-grade B2B tool built specifically for them</div></div></div>
          </div></div>
          <div className="slide"><div className="si"><div className="sn">03 / 15</div><div className="st">The Solution</div><div className="ss">One Platform. All Travel Businesses. Powered by AI.</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 185px", gap: "13px" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}><div className="card" style={{ textAlign: "left" }}><div className="card-t">📊 Unified API Layer</div><div className="card-d">One integration, all inventory — Amadeus, HotelsPro, Travolutionary and more</div></div><div className="card" style={{ textAlign: "left" }}><div className="card-t">🤖 AI Co-pilot</div><div className="card-d">Intelligent pricing & recommendations, with optional real-time avatar interface</div></div></div>
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}><div className="card" style={{ textAlign: "left" }}><div className="card-t">📈 Smart Dashboard</div><div className="card-d">Real-time analytics engine & booking management in one responsive interface</div></div><div className="card" style={{ textAlign: "left" }}><div className="card-t">⚡ Post-Booking Optimizer</div><div className="card-d">Dynamic pricing engine, auto-rebook when prices drop</div></div></div>
              <div className="lay-s"><div className="lay a">Client Dashboard</div><div className="lay m">AI Intelligence</div><div className="lay m">Unified API</div><div className="lay b">Inventory Sources</div><div className="lay b">Payments + Crypto</div></div>
            </div>
          </div></div>
          <div className="slide"><div className="si"><div className="sn">04 / 15</div><div className="st">Market Opportunity</div>
            <div className="g3" style={{ marginBottom: "16px" }}><div className="metric"><div className="metric-n">$11.4T</div><div className="metric-l">Global Travel TAM 2028</div><div className="metric-s">Post-pandemic high surpassed</div></div><div className="metric"><div className="metric-n">$780B</div><div className="metric-l">B2B Travel Technology TAM</div><div className="metric-s">Growing at 12.4% CAGR</div></div><div className="metric"><div className="metric-n">62%</div><div className="metric-l">Agents use 3+ tools</div><div className="metric-s">Prime for consolidation</div></div></div>
            <div className="g3"><div className="card"><div className="card-i">🔀</div><div className="card-t">OTAs</div><div className="card-d">Online Travel Agents seeking API aggregation, AI tooling, and B2B dashboards</div></div><div className="card"><div className="card-i">👤</div><div className="card-t">ITAs</div><div className="card-d">Independent Travel Agents needing professional enterprise-grade platform access</div></div><div className="card"><div className="card-i">🏢</div><div className="card-t">DMCs</div><div className="card-d">Destination Management Companies handling complex multi-product bookings</div></div></div>
          </div></div>
          <div className="slide"><div className="si"><div className="sn">06 / 15</div><div className="st">Competitive Landscape</div><div className="ss">Kanoe.ai is the only AI-native, full-stack B2B travel platform</div>
            <table className="ctbl"><thead><tr><th>Platform</th><th>B2B Focus</th><th>AI Layer</th><th>Crypto Pay</th><th>Post-Book Opt.</th><th>White Label</th></tr></thead>
            <tbody><tr><td>Expedia / Booking.com</td><td className="partial">Partial</td><td className="partial">Limited</td><td className="no">No</td><td className="no">No</td><td className="no">No</td></tr>
            <tr><td>RateHawk / Beroni</td><td className="yes">Yes</td><td className="partial">Basic</td><td className="no">No</td><td className="no">No</td><td className="partial">Partial</td></tr>
            <tr><td>Amadeus GDS</td><td className="yes">Yes</td><td className="partial">Legacy</td><td className="no">No</td><td className="no">No</td><td className="no">No</td></tr>
            <tr><td>Pruvo (standalone)</td><td className="partial">Partial</td><td className="partial">Pricing only</td><td className="no">No</td><td className="yes">Yes</td><td className="no">No</td></tr>
            <tr className="hl"><td>Kanoe.ai</td><td className="yes">Yes</td><td className="yes">Full Stack</td><td className="yes">Yes</td><td className="yes">Yes</td><td className="yes">Yes</td></tr></tbody></table>
            <div style={{ marginTop: "14px", padding: "10px 14px", background: "rgba(0,229,192,0.05)", border: "1px solid var(--teal3)", borderRadius: "8px", fontSize: "12px", color: "var(--teal)", fontStyle: "italic" }}>Kanoe.ai is the only platform combining B2B focus, full-stack AI, dynamic itineraries, post-booking optimization, and crypto-native payments.</div>
          </div></div>

          <div className="slide"><div className="si"><div className="sn">13 / 15</div><div className="st">Financial Projections</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", alignItems: "start" }}>
              <div className="bars"><div style={{ fontSize: "12px", color: "var(--muted)", marginBottom: "10px" }}>Annual Recurring Revenue ($M)</div>
                <div className="br"><span className="by">2026E</span><div className="bt"><div className="bf" style={{ width: "4%" }}>$400K</div></div></div>
                <div className="br"><span className="by">2027E</span><div className="bt"><div className="bf" style={{ width: "29%" }}>$2.8M</div></div></div>
                <div className="br"><span className="by">2028E</span><div className="bt"><div className="bf" style={{ width: "100%" }}>$9.5M</div></div></div>
              </div>
              <div><table className="ptbl"><thead><tr><th>Metric</th><th>2026E</th><th>2027E</th><th>2028E</th></tr></thead>
                <tbody><tr><td>ARR</td><td>$400K</td><td>$2.8M</td><td className="hl">$9.5M</td></tr>
                <tr><td>Clients</td><td>12</td><td>85</td><td className="hl">290</td></tr>
                <tr><td>Gross Margin</td><td>58%</td><td>66%</td><td className="hl">72%</td></tr>
                <tr><td>EBITDA</td><td>-45%</td><td>-12%</td><td className="hl">18%</td></tr>
                <tr><td>Headcount</td><td>8</td><td>22</td><td className="hl">55</td></tr></tbody></table>
                <div style={{ marginTop: "8px", fontSize: "11px", color: "var(--muted)", fontStyle: "italic" }}>Conservative projections based on comparable B2B travel SaaS benchmarks.</div>
              </div>
            </div>
          </div></div>
          <div className="slide"><div className="si"><div className="sn">14–15 / 15</div><div className="st">Team & Vision</div>
            <div className="team-g">
              <div className="tc"><div className="tav">JP</div><div className="tn">Jon Peters</div><div className="tr2">Founder & CFO/COO</div><div className="tb">Fintech and Deeptech entrepreneur, 30+ years at Natwest, SMBC, IDT, Cisco, TMX</div></div>
              <div className="tc"><div className="tav">TW</div><div className="tn">Tyler Warren</div><div className="tr2">Co-Founder & CEO</div><div className="tb">Former US Diplomat, 25+ years enterprise data systems for U.S. Government, Pragma Capital, LunaJet</div></div>
              <div className="tc"><div className="tav">JR</div><div className="tn">Josh Rosenthal</div><div className="tr2">CTO & GTM</div><div className="tb">Co-Founder of Aqua, Cloudsploit, Synosys — multiple exits, 20+ years cloud architecture</div></div>
              <div className="tc"><div className="tav">GT</div><div className="tn">Gaston Tchicourel</div><div className="tr2">CPO & CDAO</div><div className="tb">20+ years product/data at World Bank, ConnectAmericas, IADB</div></div>
            </div>
            <div className="g2">
              <div className="card" style={{ textAlign: "left" }}><div className="card-t">🤖 AI-First</div><div className="card-d">Intelligence built into every feature, not bolted on, with true Agentic capabilities</div></div>
              <div className="card" style={{ textAlign: "left" }}><div className="card-t">🛡️ Trust by Design</div><div className="card-d">Security, reliability, and transparency embedded in the platform foundation</div></div>
              <div className="card" style={{ textAlign: "left" }}><div className="card-t">🌍 Global Scale</div><div className="card-d">Multi-currency, multi-language, built for international expansion from day one</div></div>
              <div className="card" style={{ textAlign: "left" }}><div className="card-t">🤝 Partner-Centric</div><div className="card-d">Our success is defined by our clients' growth, not just our own metrics</div></div>
            </div>
          </div></div>
          <div className="slide"><div className="si final" style={{ background: "linear-gradient(135deg,var(--navy2),var(--navy4))" }}>
            <img src="/portal/logo.jpg" alt="Kanoe.ai" style={{ height: "48px", marginBottom: "20px" }} />
            <div style={{ fontSize: "15px", color: "var(--muted)", marginBottom: "28px" }}>Let's Build the Future of TravelTech</div>
            <div style={{ fontSize: "18px", fontWeight: "500", marginBottom: "6px" }}>kanoe.ai</div>
            <div style={{ fontSize: "14px", color: "var(--muted)", marginBottom: "24px" }}>info@kanoe.ai</div>
          </div></div>
        </div>
      </div>
  )
}
