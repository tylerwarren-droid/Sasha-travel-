'use client'

import type { ChangeEvent } from 'react'
import { OnboardingData } from '../types'

interface Step1Props {
  data: OnboardingData
  onChange: (partial: Partial<OnboardingData>) => void
}

const inputClass =
  'border border-gray-200 rounded-lg px-3 py-2.5 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-teal/30 focus:border-teal w-full bg-white'
const labelClass = 'text-xs font-medium text-muted uppercase tracking-wide mb-1 block'

const COMMISSION_MODELS = [
  {
    id: 'commission_only',
    icon: '💸',
    label: 'Commission Only',
    description: 'We earn when you earn',
  },
  {
    id: 'flat_commission',
    icon: '📊',
    label: 'Flat + Commission',
    description: 'Fixed monthly + per-booking',
  },
  {
    id: 'flat_only',
    icon: '📅',
    label: 'Flat Only',
    description: 'Predictable monthly cost',
  },
]

export default function Step1Account({ data, onChange }: Step1Props) {
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
          Set up your account
        </h2>
        <p style={{ fontSize: '0.9rem', color: '#6B6B6B' }}>
          Tell us about your business so we can personalise your Sasha experience.
        </p>
      </div>

      {/* Row 1: business_name + website_url */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Business Name</label>
          <input
            type="text"
            className={inputClass}
            placeholder="e.g. Kanoe Travel"
            value={data.business_name}
            onChange={(e: ChangeEvent<HTMLInputElement>) => onChange({ business_name: e.target.value })}
          />
        </div>
        <div>
          <label className={labelClass}>Website URL</label>
          <input
            type="url"
            className={inputClass}
            placeholder="https://yourwebsite.com"
            value={data.website_url}
            onChange={(e: ChangeEvent<HTMLInputElement>) => onChange({ website_url: e.target.value })}
          />
        </div>
      </div>

      {/* Row 2: destinations textarea */}
      <div>
        <label className={labelClass}>Destinations</label>
        <textarea
          className={inputClass}
          rows={3}
          placeholder="e.g. Vietnam, Thailand, Bali"
          value={data.destinations}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => onChange({ destinations: e.target.value })}
          style={{ resize: 'vertical' }}
        />
      </div>

      {/* Row 3: business_type + currency */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Business Type</label>
          <select
            className={inputClass}
            value={data.business_type}
            onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange({ business_type: e.target.value })}
          >
            <option value="">Select type…</option>
            <option value="OTA">OTA</option>
            <option value="Hotel">Hotel</option>
            <option value="Tour Operator">Tour Operator</option>
            <option value="DMC">DMC</option>
          </select>
        </div>
        <div>
          <label className={labelClass}>Currency</label>
          <select
            className={inputClass}
            value={data.currency}
            onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange({ currency: e.target.value })}
          >
            <option value="USD">USD</option>
            <option value="EUR">EUR</option>
            <option value="GBP">GBP</option>
            <option value="AUD">AUD</option>
            <option value="SGD">SGD</option>
            <option value="THB">THB</option>
          </select>
        </div>
      </div>

      {/* Row 4: contact info */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <label className={labelClass}>Contact Name</label>
          <input
            type="text"
            className={inputClass}
            placeholder="Jane Smith"
            value={data.contact_name}
            onChange={(e: ChangeEvent<HTMLInputElement>) => onChange({ contact_name: e.target.value })}
          />
        </div>
        <div>
          <label className={labelClass}>Contact Email</label>
          <input
            type="email"
            className={inputClass}
            placeholder="jane@yourcompany.com"
            value={data.contact_email}
            onChange={(e: ChangeEvent<HTMLInputElement>) => onChange({ contact_email: e.target.value })}
          />
        </div>
        <div>
          <label className={labelClass}>Contact Phone</label>
          <input
            type="tel"
            className={inputClass}
            placeholder="+1 555 000 0000"
            value={data.contact_phone}
            onChange={(e: ChangeEvent<HTMLInputElement>) => onChange({ contact_phone: e.target.value })}
          />
        </div>
      </div>

      {/* Commission model */}
      <div>
        <label className={labelClass}>Commission Model</label>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-2">
          {COMMISSION_MODELS.map((model) => {
            const isSelected = data.commission_model === model.id
            return (
              <button
                key={model.id}
                type="button"
                onClick={() => onChange({ commission_model: model.id })}
                className="text-left p-4 rounded-xl border-2 transition-all duration-150"
                style={{
                  borderColor: isSelected ? '#0F6E56' : '#E5E7EB',
                  background: isSelected ? '#E1F5EE' : '#ffffff',
                }}
              >
                <div className="text-xl mb-2">{model.icon}</div>
                <div
                  className="font-medium text-sm mb-0.5"
                  style={{ color: isSelected ? '#0F6E56' : '#1A1A1A' }}
                >
                  {model.label}
                </div>
                <div className="text-xs" style={{ color: '#6B6B6B' }}>
                  {model.description}
                </div>
                {isSelected && (
                  <div
                    className="mt-2 w-4 h-4 rounded-full flex items-center justify-center ml-auto"
                    style={{ background: '#0F6E56' }}
                  >
                    <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                      <path
                        d="M1 4L3 6L7 2"
                        stroke="white"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </div>
                )}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
