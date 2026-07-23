// Data strategy panel of the investor portal, ported from the original standalone document.
// Static content: no client-side behaviour, so this stays a server component.

export default function DataStrategy() {
  return (
      <div className="panel active" id="panel-data">
        <div className="t-hero" style={{ maxWidth: "960px", margin: "0 auto", padding: "80px 40px 40px" }}>
          <div className="t-eyebrow">Proprietary Data · Alternative Assets · Recurring Revenue</div>
          <h1 className="t-h1">The Kanoe <em>Data Strategy</em></h1>
          <p className="t-sub" style={{ maxWidth: "680px" }}>Every booking, search, and pricing event flows into a proprietary MOR corpus — enriched by AI, fed by RateGain, and monetised through quant hedge fund licensing and B2B client intelligence reports.</p>
        </div>
        <div className="t-sec" style={{ maxWidth: "960px", margin: "0 auto", padding: "0 40px 60px" }}>
          <svg viewBox="0 0 880 480" width="100%" style={{ display: "block", margin: "0 auto 48px" }}>
            <defs>
              <marker id="da" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></marker>
            </defs>
            <rect x="20" y="60" width="164" height="60" rx="8" fill="#071828" stroke="#00E5C0" strokeWidth="0.5" />
            <text x="102" y="85" textAnchor="middle" fill="#00E5C0" fontFamily="DM Sans,sans-serif" fontSize="13" fontWeight="600">B2B MOR Data</text>
            <text x="102" y="104" textAnchor="middle" fill="#7ab8c8" fontFamily="DM Sans,sans-serif" fontSize="11">Market occupancy rates</text>
            <rect x="20" y="156" width="164" height="60" rx="8" fill="#071828" stroke="#00E5C0" strokeWidth="0.5" />
            <text x="102" y="181" textAnchor="middle" fill="#00E5C0" fontFamily="DM Sans,sans-serif" fontSize="13" fontWeight="600">B2C MOR Data</text>
            <text x="102" y="200" textAnchor="middle" fill="#7ab8c8" fontFamily="DM Sans,sans-serif" fontSize="11">Consumer booking signals</text>
            <line x1="184" y1="90" x2="314" y2="178" stroke="#00E5C0" strokeWidth="1.5" strokeOpacity="0.6" markerEnd="url(#da)" />
            <line x1="184" y1="186" x2="314" y2="204" stroke="#00E5C0" strokeWidth="1.5" strokeOpacity="0.6" markerEnd="url(#da)" />
            <rect x="318" y="152" width="184" height="72" rx="8" fill="#0a0d2e" stroke="#7F77DD" strokeWidth="0.8" />
            <text x="410" y="180" textAnchor="middle" fill="#c4b8ff" fontFamily="DM Sans,sans-serif" fontSize="14" fontWeight="700">Kanoe Analytics Engine</text>
            <text x="410" y="202" textAnchor="middle" fill="#8880b0" fontFamily="DM Sans,sans-serif" fontSize="11">AI enrichment + scoring</text>
            <rect x="380" y="40" width="148" height="56" rx="8" fill="#1a1200" stroke="#EF9F27" strokeWidth="0.5" />
            <text x="454" y="63" textAnchor="middle" fill="#EF9F27" fontFamily="DM Sans,sans-serif" fontSize="13" fontWeight="600">RateGain</text>
            <text x="454" y="82" textAnchor="middle" fill="#a07820" fontFamily="DM Sans,sans-serif" fontSize="11">Competitive rate feeds</text>
            <line x1="454" y1="96" x2="454" y2="150" stroke="#EF9F27" strokeWidth="1.5" strokeOpacity="0.8" markerEnd="url(#da)" />
            <line x1="502" y1="192" x2="612" y2="220" stroke="#7F77DD" strokeWidth="1.5" strokeOpacity="0.7" markerEnd="url(#da)" />
            <rect x="616" y="196" width="172" height="60" rx="8" fill="#040D1A" stroke="#378ADD" strokeWidth="0.8" />
            <text x="702" y="221" textAnchor="middle" fill="#85B7EB" fontFamily="DM Sans,sans-serif" fontSize="14" fontWeight="700">Augmented Datasets</text>
            <text x="702" y="240" textAnchor="middle" fill="#5a90c0" fontFamily="DM Sans,sans-serif" fontSize="11">AI-enriched MOR corpus</text>
            <path d="M702 256 L702 296 L578 296 L578 324" fill="none" stroke="#378ADD" strokeWidth="1.5" strokeOpacity="0.8" markerEnd="url(#da)" />
            <path d="M702 256 L702 296 L820 296 L820 324" fill="none" stroke="#378ADD" strokeWidth="1.5" strokeOpacity="0.8" markerEnd="url(#da)" />
            <rect x="478" y="324" width="196" height="68" rx="8" fill="#1a0800" stroke="#D85A30" strokeWidth="0.5" />
            <text x="576" y="350" textAnchor="middle" fill="#F0997B" fontFamily="DM Sans,sans-serif" fontSize="13" fontWeight="700">Quant HF Licensing</text>
            <text x="576" y="368" textAnchor="middle" fill="#994030" fontFamily="DM Sans,sans-serif" fontSize="11">Hedge fund data sales</text>
            <text x="576" y="384" textAnchor="middle" fill="#994030" fontFamily="DM Sans,sans-serif" fontSize="11">Recurring licensing rev.</text>
            <rect x="720" y="324" width="160" height="68" rx="8" fill="#041008" stroke="#1D9E75" strokeWidth="0.5" />
            <text x="800" y="350" textAnchor="middle" fill="#5DCAA5" fontFamily="DM Sans,sans-serif" fontSize="13" fontWeight="700">B2B Client Reports</text>
            <text x="800" y="368" textAnchor="middle" fill="#0F6E56" fontFamily="DM Sans,sans-serif" fontSize="11">OTA / ITA / DMC intel</text>
            <text x="800" y="384" textAnchor="middle" fill="#0F6E56" fontFamily="DM Sans,sans-serif" fontSize="11">White-label analytics</text>
            <rect x="20" y="432" width="840" height="36" rx="6" fill="#071828" stroke="#00E5C0" strokeWidth="0.3" strokeOpacity="0.3" />
            <text x="440" y="447" textAnchor="middle" fill="#00E5C0" fontFamily="DM Sans,sans-serif" fontSize="11" opacity="0.8">Data flywheel: every booking enriches the corpus — stronger datasets — higher licensing value</text>
            <text x="440" y="461" textAnchor="middle" fill="#7ab8c8" fontFamily="DM Sans,sans-serif" fontSize="10" opacity="0.6">Proprietary MOR corpus = durable competitive moat</text>
          </svg>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "24px" }}>
            <div className="pillar">
              <div className="pillar-num">01</div>
              <h3 className="pillar-h">MOR Corpus</h3>
              <p className="pillar-p">Proprietary market occupancy rate data collected across B2B and B2C channels — unavailable anywhere else at this granularity.</p>
            </div>
            <div className="pillar">
              <div className="pillar-num">02</div>
              <h3 className="pillar-h">Quant Licensing</h3>
              <p className="pillar-p">Augmented datasets licensed directly to quantitative hedge funds as an alternative data product — high-margin, recurring revenue stream.</p>
            </div>
            <div className="pillar">
              <div className="pillar-num">03</div>
              <h3 className="pillar-h">B2B Intelligence</h3>
              <p className="pillar-p">White-label analytics reports delivered to OTAs, ITAs, and DMCs — turning Kanoe's data advantage into a client retention tool.</p>
            </div>
          </div>
        </div>
      </div>
  )
}
