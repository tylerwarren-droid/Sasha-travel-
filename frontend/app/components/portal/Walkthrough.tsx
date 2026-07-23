'use client'

import { useState } from 'react'

// B2B onboarding walkthrough. Every behaviour here was a global function mutating classNames
// (showOb / selComm / selPathway / selInvTab / toggleCustom / regenWelcome / goLive); each is
// now a piece of React state driving the same class names, so the CSS is untouched.

const WELCOMES = [
  "Welcome to Bob's Beaches! I'm Sasha, your personal Thailand travel concierge. Whether you're dreaming of a honeymoon in Koh Samui, a family adventure in Phuket, or learning to dive in Krabi — I can plan it all. Where shall we start?",
  "Hi there! I'm Sasha, your insider guide to Thailand's most beautiful beaches. I know every hidden cove, the best dive spots, and the finest restaurants across Phuket, Koh Samui and Krabi. Tell me your dream holiday.",
  "Sawasdee! I'm Sasha — think of me as your personal Thailand expert. From romantic sunset dinners to early morning dives, I'll book everything. What brings you to Thailand?",
]

const ADDON_PRICE = 99

// Displayed verbatim in the Deploy step as copy-paste sample code.
const EMBED_SNIPPET = `<script src="https://sasha.kanoe.ai/embed.js"
  data-client="bobsbeaches"
  data-pathway="A"
  data-position="bottom-right">
</script>`

export default function Walkthrough() {
  const [step, setStep] = useState(0)
  const [comm, setComm] = useState(1)
  const [pathway, setPathway] = useState(0)
  const [invTab, setInvTab] = useState(0)
  const [agents, setAgents] = useState<Set<number>>(() => new Set())
  const [welcomeIdx, setWelcomeIdx] = useState(0)
  const [welcome, setWelcome] = useState(WELCOMES[0])
  const [live, setLive] = useState(false)

  const stepBtnClass = (n: number) => `ob-step-btn${step === n ? ' active' : ''}`
  const obPanelClass = (n: number) => `ob-panel${step === n ? ' active' : ''}`

  const toggleAgent = (n: number) =>
    setAgents(prev => {
      const next = new Set(prev)
      if (next.has(n)) next.delete(n)
      else next.add(n)
      return next
    })

  const regenWelcome = () => {
    const next = (welcomeIdx + 1) % WELCOMES.length
    setWelcomeIdx(next)
    setWelcome(WELCOMES[next])
  }

  const addonCost = agents.size > 0 ? `$${agents.size * ADDON_PRICE}/mo` : '$0'

  const liveStyle = {
    background: 'rgba(0,229,192,0.2)',
    color: 'var(--teal)',
    border: '1px solid var(--teal)',
  } as const

  return (
    <div className="panel active" id="panel-onboarding">
      <div className="ob-wrap">
        <div className="ob-hdr">
          <h2>B2B Onboarding — Interactive Walkthrough</h2>
          <p>Click through each step to see how Bob's Beaches goes from sign-up to live AI concierge in under 20 minutes</p>
        </div>
        <div className="ob-steps">
          <button className={stepBtnClass(0)} onClick={() => setStep(0)}>1. Account</button>
          <button className={stepBtnClass(1)} onClick={() => setStep(1)}>2. Pathway</button>
          <button className={stepBtnClass(2)} onClick={() => setStep(2)}>3. Prompt wizard</button>
          <button className={stepBtnClass(3)} onClick={() => setStep(3)}>4. Inventory</button>
          <button className={stepBtnClass(4)} onClick={() => setStep(4)}>5. Agents</button>
          <button className={stepBtnClass(5)} onClick={() => setStep(5)}>6. Deploy</button>
        </div>

        {/* Step 1 */}
        <div className={obPanelClass(0)} id="ob-0">
          <div className="ob-card">
            <div className="ob-section-title">About your business</div>
            <div className="form-g">
              <div className="fg"><label>Business name</label><input type="text" defaultValue="Bob's Beaches" /></div>
              <div className="fg"><label>Website URL</label><input type="text" defaultValue="bobsbeaches.com" /></div>
              <div className="fg"><label>Primary destination(s)</label><input type="text" defaultValue="Phuket, Koh Samui, Krabi" /></div>
              <div className="fg"><label>Business type</label><select><option>OTA / travel agency</option><option>Hotel group</option><option>Tour operator</option></select></div>
            </div>
            <div className="ob-section-title" style={{ marginTop: "16px" }}>Commission structure</div>
            <div className="comm-grid">
              <div className={`comm-card${comm === 0 ? ' sel' : ''}`} onClick={() => setComm(0)}><h4>Commission only</h4><p>$0/mo · 12% platform cut</p></div>
              <div className={`comm-card${comm === 1 ? ' sel' : ''}`} onClick={() => setComm(1)}><h4>Flat + reduced commission</h4><p>$299/mo · 5% platform cut</p></div>
              <div className={`comm-card${comm === 2 ? ' sel' : ''}`} onClick={() => setComm(2)}><h4>Flat monthly only</h4><p>$499/mo · 0% commission</p></div>
            </div>
          </div>
          <div className="ob-nav"><div></div><button className="ob-next" onClick={() => setStep(1)}>Continue →</button></div>
        </div>

        {/* Step 2 */}
        <div className={obPanelClass(1)} id="ob-1">
          <div className="ob-card">
            <p style={{ fontSize: "14px", color: "var(--muted)", marginBottom: "20px" }}>How would you like Sasha to interact with your customers?</p>
            <div className="pathway-g">
              <div className={`pathway-card${pathway === 0 ? ' sel' : ''}`} onClick={() => setPathway(0)}>
                <div className="pathway-icon">🎭</div>
                <div style={{ fontSize: "10px", letterSpacing: "0.1em", fontWeight: "500", color: "var(--teal)", textTransform: "uppercase", marginBottom: "6px" }}>Most popular</div>
                <div className="pathway-title">Pathway A</div>
                <div className="pathway-sub">Avatar + voice</div>
                <ul className="check-list">
                  <li>Photorealistic AI avatar</li><li>Real-time voice conversation</li><li>Chat fallback included</li><li>Photo strip + itinerary</li>
                  <li className="dim">+$49/mo HeyGen add-on</li>
                </ul>
              </div>
              <div className={`pathway-card${pathway === 1 ? ' sel' : ''}`} onClick={() => setPathway(1)}>
                <div className="pathway-icon">🎙️</div>
                <div style={{ fontSize: "10px", letterSpacing: "0.1em", fontWeight: "500", color: "var(--muted)", textTransform: "uppercase", marginBottom: "6px" }}>Included in base plan</div>
                <div className="pathway-title">Pathway B</div>
                <div className="pathway-sub">Voice + chat only</div>
                <ul className="check-list">
                  <li>Deepgram STT + TTS</li><li>Full chat interface</li><li>Photo strip + itinerary</li><li>Lower bandwidth usage</li><li>No avatar subscription needed</li>
                </ul>
              </div>
            </div>
            <div style={{ background: "var(--navy4)", border: "1px solid var(--border)", borderRadius: "10px", padding: "14px", fontSize: "13px", color: "var(--muted)" }}><strong style={{ color: "var(--text)" }}>Can I use both?</strong> Yes — many clients run Pathway A on their homepage and Pathway B on listing pages.</div>
          </div>
          <div className="ob-nav"><button className="ob-back" onClick={() => setStep(0)}>← Back</button><button className="ob-next" onClick={() => setStep(2)}>Continue →</button></div>
        </div>

        {/* Step 3 */}
        <div className={obPanelClass(2)} id="ob-2">
          <div className="ob-card">
            <div className="ob-section-title">Sasha's identity</div>
            <div className="form-g" style={{ marginBottom: "16px" }}>
              <div className="fg"><label>What should Sasha call herself?</label><input type="text" defaultValue="Sasha" /></div>
              <div className="fg"><label>Tone of voice</label><select><option>Warm and friendly</option><option>Professional and formal</option><option>Luxury and exclusive</option></select></div>
            </div>
            <div className="fg" style={{ marginBottom: "16px" }}><label>Languages</label>
              <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "6px" }}>
                <span className="lang-pill on">English</span>
                <span className="lang-pill on">Thai</span>
                <span className="lang-pill">Chinese</span>
                <span className="lang-pill">German</span>
                <span className="lang-pill">French</span>
                <span className="lang-pill">Arabic</span>
              </div>
            </div>
            <div className="ob-section-title">What Sasha knows</div>
            <div className="fg" style={{ marginBottom: "12px" }}><label>Describe your destination</label><textarea rows={3} defaultValue="Bob's Beaches specialises in luxury beach holidays across Thailand's southern islands \u2014 Phuket, Koh Samui and Krabi. We focus on honeymooners, families and diving enthusiasts." /></div>
            <div className="fg" style={{ marginBottom: "16px" }}><label>Anything Sasha should never discuss?</label><input type="text" placeholder="e.g. Competitor names, political topics" /></div>
            <div className="ob-section-title">Opening message</div>
            <div className="fg"><textarea id="welcome-txt" rows={3} value={welcome} onChange={e => setWelcome(e.target.value)} /></div>
            <button className="btn-g" style={{ marginTop: "8px", fontSize: "12px", padding: "6px 14px" }} onClick={regenWelcome}>✨ Regenerate with AI</button>
          </div>
          <div className="ob-nav"><button className="ob-back" onClick={() => setStep(1)}>← Back</button><button className="ob-next" onClick={() => setStep(3)}>Continue →</button></div>
        </div>

        {/* Step 4 */}
        <div className={obPanelClass(3)} id="ob-3">
          <div className="ob-card">
            <p style={{ fontSize: "14px", color: "var(--muted)", marginBottom: "18px" }}>Upload your curated properties. Sasha always prioritises these first — this is your IP.</p>
            <div className="inv-tabs">
              <button className={`inv-tab${invTab === 0 ? ' active' : ''}`} onClick={() => setInvTab(0)}>🏨 Hotels <span style={{ color: "var(--teal)" }}>50</span></button>
              <button className={`inv-tab${invTab === 1 ? ' active' : ''}`} onClick={() => setInvTab(1)}>🍽️ Restaurants <span style={{ color: "var(--teal)" }}>100</span></button>
              <button className={`inv-tab${invTab === 2 ? ' active' : ''}`} onClick={() => setInvTab(2)}>💆 Spas <span style={{ color: "var(--teal)" }}>25</span></button>
              <button className={`inv-tab${invTab === 3 ? ' active' : ''}`} onClick={() => setInvTab(3)}>✨ Experiences <span style={{ color: "#E0A535" }}>Add some</span></button>
            </div>
            <table className="inv-table">
              <thead><tr><th>Name</th><th>Location</th><th>Commission</th><th>Priority</th></tr></thead>
              <tbody>
                <tr><td style={{ fontWeight: "500" }}>Amanpuri</td><td style={{ color: "var(--muted)" }}>Phuket</td><td style={{ color: "var(--muted)" }}>12%</td><td><span className="pill pill-blue">Platinum</span></td></tr>
                <tr><td style={{ fontWeight: "500" }}>Four Seasons Samui</td><td style={{ color: "var(--muted)" }}>Koh Samui</td><td style={{ color: "var(--muted)" }}>10%</td><td><span className="pill pill-amber">Gold</span></td></tr>
                <tr><td style={{ fontWeight: "500" }}>Rayavadee</td><td style={{ color: "var(--muted)" }}>Krabi</td><td style={{ color: "var(--muted)" }}>15%</td><td><span className="pill pill-blue">Platinum</span></td></tr>
              </tbody>
            </table>
            <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
              <button className="btn-g" style={{ fontSize: "12px", padding: "7px 14px" }}>📥 Download template</button>
              <button className="btn-p" style={{ fontSize: "12px", padding: "7px 14px" }}>📤 Upload CSV</button>
            </div>
            <div style={{ border: "1px dashed rgba(0,229,192,0.2)", borderRadius: "10px", padding: "18px", textAlign: "center", marginBottom: "16px", cursor: "pointer" }}>
              <div style={{ fontSize: "13px", fontWeight: "500", marginBottom: "4px" }}>📎 Connect your API too — use both together</div>
              <div style={{ fontSize: "12px", color: "var(--muted)" }}>Sync your PMS or channel manager alongside your curated list. Your IP stays prioritised — the API fills the gaps with live availability.</div>
            </div>
            <div style={{ background: "var(--navy4)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px" }}>
              <div style={{ fontSize: "13px", fontWeight: "500", marginBottom: "8px" }}>🔗 Curated lists</div>
              <div style={{ fontSize: "12px", color: "var(--muted)", marginBottom: "10px" }}>Paste any URL — a Condé Nast ranking, a TripAdvisor list. Sasha reads and references it.</div>
              <div style={{ display: "flex", gap: "8px" }}><input type="text" placeholder="https://www.cntraveller.com/best-hotels-thailand" style={{ flex: "1", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "8px", fontSize: "12px", fontFamily: "var(--body)", background: "var(--navy3)", color: "var(--text)" }} /><button className="btn-g" style={{ fontSize: "12px", padding: "8px 14px", whiteSpace: "nowrap" }}>Add URL</button></div>
            </div>
          </div>
          <div className="ob-nav"><button className="ob-back" onClick={() => setStep(2)}>← Back</button><button className="ob-next" onClick={() => setStep(4)}>Continue →</button></div>
        </div>

        {/* Step 5 */}
        <div className={obPanelClass(4)} id="ob-4">
          <div className="ob-card">
            <p style={{ fontSize: "14px", color: "var(--muted)", marginBottom: "18px" }}>Core agents are included in your plan. Custom agents are built to order.</p>
            <div style={{ fontSize: "11px", letterSpacing: "0.1em", fontWeight: "500", color: "var(--muted)", textTransform: "uppercase", marginBottom: "12px" }}>Included in your plan</div>
            <div className="agents-grid" style={{ marginBottom: "20px" }}>
              <div className="agent-card on"><div className="agent-check on">✓</div><span className="agent-icon">🍽️</span><div className="agent-name">Restaurant</div><div className="agent-desc">Find, book, email + call</div><span className="agent-badge badge-inc">Included</span></div>
              <div className="agent-card on"><div className="agent-check on">✓</div><span className="agent-icon">🏥</span><div className="agent-name">Health</div><div className="agent-desc">Doctor, clinic, pharmacy</div><span className="agent-badge badge-inc">Included</span></div>
              <div className="agent-card on"><div className="agent-check on">✓</div><span className="agent-icon">💆</span><div className="agent-name">Beauty & spa</div><div className="agent-desc">Massage, nails, facial</div><span className="agent-badge badge-inc">Included</span></div>
              <div className="agent-card on"><div className="agent-check on">✓</div><span className="agent-icon">⛳</span><div className="agent-name">Golf</div><div className="agent-desc">Courses, tee times, booking</div><span className="agent-badge badge-inc">Included</span></div>
              <div className="agent-card on"><div className="agent-check on">✓</div><span className="agent-icon">🐕</span><div className="agent-name">Pet care</div><div className="agent-desc">Dog walker, sitter, vet</div><span className="agent-badge badge-inc">Included</span></div>
              <div className="agent-card on"><div className="agent-check on">✓</div><span className="agent-icon">🏨</span><div className="agent-name">Booking confirm</div><div className="agent-desc">PMS reference, hotel contact</div><span className="agent-badge badge-inc">Included</span></div>
            </div>
            <div style={{ fontSize: "11px", letterSpacing: "0.1em", fontWeight: "500", color: "var(--muted)", textTransform: "uppercase", marginBottom: "12px" }}>Custom agents — add-on</div>
            <div className="agents-grid" id="custom-agents">
              <div className={`agent-card custom${agents.has(0) ? ' on' : ''}`} onClick={() => toggleAgent(0)}><div className={`agent-check ${agents.has(0) ? 'on-c' : 'off'}`}>{agents.has(0) ? '✓' : ''}</div><span className="agent-icon">🤿</span><div className="agent-name">Scuba & diving</div><div className="agent-desc">Equipment, instructors, sites</div><span className="agent-badge badge-add">+$99/mo</span></div>
              <div className={`agent-card custom${agents.has(1) ? ' on' : ''}`} onClick={() => toggleAgent(1)}><div className={`agent-check ${agents.has(1) ? 'on-c' : 'off'}`}>{agents.has(1) ? '✓' : ''}</div><span className="agent-icon">🏄</span><div className="agent-name">Surf & watersports</div><div className="agent-desc">Lessons, boards, conditions</div><span className="agent-badge badge-add">+$99/mo</span></div>
              <div className={`agent-card custom${agents.has(2) ? ' on' : ''}`} onClick={() => toggleAgent(2)}><div className={`agent-check ${agents.has(2) ? 'on-c' : 'off'}`}>{agents.has(2) ? '✓' : ''}</div><span className="agent-icon">🚗</span><div className="agent-name">Transfers & cars</div><div className="agent-desc">Airport, private, rental</div><span className="agent-badge badge-add">+$99/mo</span></div>
            </div>
            <div className="addon-bar" style={{ marginTop: "16px" }}><span>Monthly add-on cost</span><strong id="addon-cost">{addonCost}</strong></div>
          </div>
          <div className="ob-nav"><button className="ob-back" onClick={() => setStep(3)}>← Back</button><button className="ob-next" onClick={() => setStep(5)}>Continue →</button></div>
        </div>

        {/* Step 6 */}
        <div className={obPanelClass(5)} id="ob-5">
          <div className="ob-card">
            <div className="deploy-hero">
              <div className="deploy-icon">🚀</div>
              <div>
                <div style={{ fontSize: "15px", fontWeight: "500", color: "var(--teal)", marginBottom: "2px" }}>Bob's Beaches is ready to go live</div>
                <div style={{ fontSize: "13px", color: "var(--teal)", opacity: "0.7" }}>6 core agents · Pathway A · 175 inventory items · 2 curated lists</div>
              </div>
            </div>
            <div style={{ fontSize: "13px", fontWeight: "500", marginBottom: "10px" }}>Your Sasha URL</div>
            <div className="url-box">
              <div className="url-disp">sasha.kanoe.ai/bobsbeaches</div>
              <button className="btn-g" style={{ fontSize: "12px", padding: "8px 14px" }}>Copy</button>
              <button className="btn-p" style={{ fontSize: "12px", padding: "8px 14px" }}>Preview</button>
            </div>
            <div style={{ fontSize: "13px", fontWeight: "500", marginBottom: "10px" }}>Embed on your website</div>
            {/* The embed snippet an operator copies. It is sample text, not a script to run —
                the source escaped it as &lt;script&gt;, so it must stay a string literal here or
                React treats it as a real element it will never execute. */}
            <div className="code-blk"><pre>{EMBED_SNIPPET}</pre></div>
            <div style={{ fontSize: "13px", fontWeight: "500", marginBottom: "12px" }}>Go-live checklist</div>
            <ul className="checklist">
              <li><div className="chk-dot done">✓</div><span style={{ textDecoration: "line-through", opacity: "0.5" }}>Business details completed</span></li>
              <li><div className="chk-dot done">✓</div><span style={{ textDecoration: "line-through", opacity: "0.5" }}>Pathway A selected</span></li>
              <li><div className="chk-dot done">✓</div><span style={{ textDecoration: "line-through", opacity: "0.5" }}>LLM prompt configured</span></li>
              <li><div className="chk-dot done">✓</div><span style={{ textDecoration: "line-through", opacity: "0.5" }}>Inventory uploaded (175 items)</span></li>
              <li><div className="chk-dot done">✓</div><span style={{ textDecoration: "line-through", opacity: "0.5" }}>Core agents enabled</span></li>
              <li><div className="chk-dot todo"></div><span>Embed code installed on website</span></li>
              <li><div className="chk-dot todo"></div><span>Custom domain connected</span></li>
            </ul>
          </div>
          <div className="ob-nav"><button className="ob-back" onClick={() => setStep(4)}>← Back</button><button className="ob-next" onClick={() => setLive(true)} style={live ? liveStyle : undefined}>{live ? "🎉 You're live!" : '🚀 Go live'}</button></div>
        </div>
      </div>
    </div>
  )
}
