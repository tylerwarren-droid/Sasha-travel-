'use client'

import { useState, type ChangeEvent } from 'react'
import { OnboardingData } from '../types'

interface Step3Props {
  data: OnboardingData
  onChange: (partial: Partial<OnboardingData>) => void
}

const inputClass =
  'border border-gray-200 rounded-lg px-3 py-2.5 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-teal/30 focus:border-teal w-full bg-white'
const labelClass = 'text-xs font-medium text-muted uppercase tracking-wide mb-1 block'

const ALL_LANGUAGES = [
  'English',
  'French',
  'Spanish',
  'German',
  'Mandarin',
  'Japanese',
  'Arabic',
  'Portuguese',
  'Italian',
  'Russian',
]

const TONE_OPTIONS = [
  { value: 'warm_friendly', label: 'Warm & Friendly' },
  { value: 'professional', label: 'Professional' },
  { value: 'luxurious', label: 'Luxurious' },
  { value: 'adventurous', label: 'Adventurous' },
  { value: 'cultural', label: 'Cultural' },
]

export default function Step3Prompt({ data, onChange }: Step3Props) {
  const [generatingWelcome, setGeneratingWelcome] = useState(false)

  const toggleLanguage = (lang: string) => {
    const current = data.languages
    if (current.includes(lang)) {
      onChange({ languages: current.filter((l) => l !== lang) })
    } else {
      onChange({ languages: [...current, lang] })
    }
  }

  const updateSellingPoint = (idx: number, value: string) => {
    const updated: [string, string, string] = [...data.selling_points] as [string, string, string]
    updated[idx] = value
    onChange({ selling_points: updated })
  }

  const handleGenerateWelcome = async () => {
    setGeneratingWelcome(true)
    try {
      const res = await fetch('/api/onboarding/generate-welcome', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          business_name: data.business_name,
          persona_name: data.persona_name,
          destinations: data.destinations,
          description: data.destination_description,
        }),
      })
      if (res.ok) {
        const json = (await res.json()) as { welcome_message: string }
        onChange({ welcome_message: json.welcome_message })
      }
    } finally {
      setGeneratingWelcome(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2
          style={{
            fontFamily: 'var(--font-dm-serif), serif',
            fontSize: '1.75rem',
            color: '#1A1A1A',
            fontWeight: 400,
            marginBottom: '0.25rem',
          }}
        >
          Design your AI persona
        </h2>
        <p style={{ fontSize: '0.9rem', color: '#6B6B6B' }}>
          Customise how Sasha speaks, what she knows, and how she presents herself.
        </p>
      </div>

      {/* Persona name + tone */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>What should your AI concierge be called?</label>
          <input
            type="text"
            className={inputClass}
            placeholder="Sasha"
            value={data.persona_name}
            onChange={(e: ChangeEvent<HTMLInputElement>) => onChange({ persona_name: e.target.value })}
          />
        </div>
        <div>
          <label className={labelClass}>Tone</label>
          <select
            className={inputClass}
            value={data.tone}
            onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange({ tone: e.target.value })}
          >
            <option value="">Select tone…</option>
            {TONE_OPTIONS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Languages */}
      <div>
        <label className={labelClass}>Languages</label>
        <div className="flex flex-wrap gap-2 mt-1">
          {ALL_LANGUAGES.map((lang) => {
            const checked = data.languages.includes(lang)
            return (
              <button
                key={lang}
                type="button"
                onClick={() => toggleLanguage(lang)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm transition-all duration-150"
                style={{
                  borderColor: checked ? '#0F6E56' : '#E5E7EB',
                  background: checked ? '#E1F5EE' : '#ffffff',
                  color: checked ? '#0F6E56' : '#6B6B6B',
                  fontFamily: 'var(--font-dm-sans), sans-serif',
                }}
              >
                {checked && (
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path
                      d="M2 5L4 7L8 3"
                      stroke="#0F6E56"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
                {lang}
              </button>
            )
          })}
        </div>
      </div>

      {/* Destination description */}
      <div>
        <label className={labelClass}>Describe your destinations or properties</label>
        <textarea
          className={inputClass}
          rows={3}
          placeholder="Describe your destinations or properties in 2–3 sentences…"
          value={data.destination_description}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) =>
            onChange({ destination_description: e.target.value })
          }
          style={{ resize: 'vertical' }}
        />
      </div>

      {/* Selling points */}
      <div className="space-y-3">
        <label className={labelClass}>Top Selling Points</label>
        {([0, 1, 2] as const).map((idx) => (
          <div key={idx}>
            <input
              type="text"
              className={inputClass}
              placeholder={`Top selling point ${idx + 1}`}
              value={data.selling_points[idx]}
              onChange={(e: ChangeEvent<HTMLInputElement>) => updateSellingPoint(idx, e.target.value)}
            />
          </div>
        ))}
      </div>

      {/* Best time to visit */}
      <div>
        <label className={labelClass}>Best Time to Visit</label>
        <input
          type="text"
          className={inputClass}
          placeholder="e.g. November to April (dry season)"
          value={data.best_time_to_visit}
          onChange={(e: ChangeEvent<HTMLInputElement>) =>
            onChange({ best_time_to_visit: e.target.value })
          }
        />
      </div>

      {/* Never discuss */}
      <div>
        <label className={labelClass}>Never Discuss</label>
        <textarea
          className={inputClass}
          rows={2}
          placeholder="e.g. competitor brands, pricing of other properties"
          value={data.never_discuss}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => onChange({ never_discuss: e.target.value })}
          style={{ resize: 'vertical' }}
        />
      </div>

      {/* Welcome message */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className={labelClass} style={{ marginBottom: 0 }}>
            Welcome Message
          </label>
          <button
            type="button"
            onClick={handleGenerateWelcome}
            disabled={generatingWelcome}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150"
            style={{
              background: generatingWelcome ? '#E5E7EB' : '#0F6E56',
              color: generatingWelcome ? '#6B6B6B' : '#ffffff',
              fontFamily: 'var(--font-dm-sans), sans-serif',
              cursor: generatingWelcome ? 'not-allowed' : 'pointer',
            }}
          >
            {generatingWelcome ? (
              <>
                <svg
                  className="animate-spin"
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                >
                  <circle
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                    strokeDasharray="31.416"
                    strokeDashoffset="10"
                  />
                </svg>
                Generating…
              </>
            ) : (
              <>✨ Generate with AI</>
            )}
          </button>
        </div>
        <textarea
          className={inputClass}
          rows={4}
          placeholder="Write a warm welcome message, or use AI to generate one…"
          value={data.welcome_message}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) =>
            onChange({ welcome_message: e.target.value })
          }
          style={{ resize: 'vertical' }}
        />
      </div>
    </div>
  )
}
