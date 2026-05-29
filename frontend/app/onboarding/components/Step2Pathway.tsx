'use client'

import { OnboardingData } from '../types'

interface Step2Props {
  data: OnboardingData
  onChange: (partial: Partial<OnboardingData>) => void
}

const PATHWAYS = [
  {
    id: 'heygen',
    name: 'Pathway A — HeyGen Avatar',
    price: '$299/mo',
    accent: '#0F6E56',
    accentLight: '#E1F5EE',
    badge: 'Most Popular',
    badgeColor: '#0F6E56',
    features: [
      'Lifelike AI avatar',
      'Real-time lip sync',
      'Video call experience',
      'Best for luxury & premium',
    ],
  },
  {
    id: 'voice',
    name: 'Pathway B — Voice + Chat',
    price: '$149/mo',
    accent: '#BA7517',
    accentLight: '#FAEEDA',
    badge: null,
    badgeColor: null,
    features: [
      'Natural voice AI',
      'Text chat fallback',
      'Lightweight integration',
      'Best for high volume',
    ],
  },
]

export default function Step2Pathway({ data, onChange }: Step2Props) {
  const toggle = (id: string) => {
    const current = data.pathways
    if (current.includes(id)) {
      onChange({ pathways: current.filter((p) => p !== id) })
    } else {
      onChange({ pathways: [...current, id] })
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
          Choose your pathway
        </h2>
        <p style={{ fontSize: '0.9rem', color: '#6B6B6B' }}>
          Select how Sasha will engage with your guests.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        {PATHWAYS.map((pathway) => {
          const isSelected = data.pathways.includes(pathway.id)
          return (
            <button
              key={pathway.id}
              type="button"
              onClick={() => toggle(pathway.id)}
              className="text-left rounded-xl border-2 p-6 transition-all duration-150 relative"
              style={{
                borderColor: isSelected ? pathway.accent : '#E5E7EB',
                background: isSelected ? pathway.accentLight : '#ffffff',
                boxShadow: isSelected
                  ? `0 0 0 1px ${pathway.accent}22`
                  : '0 1px 3px rgba(0,0,0,0.06)',
              }}
            >
              {/* Badge */}
              {pathway.badge && (
                <span
                  className="absolute top-4 right-4 text-xs font-semibold px-2 py-0.5 rounded-full"
                  style={{
                    background: pathway.accent,
                    color: '#ffffff',
                    fontFamily: 'var(--font-dm-sans), sans-serif',
                  }}
                >
                  {pathway.badge}
                </span>
              )}

              {/* Selected checkbox */}
              <div
                className="absolute top-4 left-4 w-5 h-5 rounded flex items-center justify-center transition-all duration-150"
                style={{
                  background: isSelected ? pathway.accent : 'transparent',
                  border: `2px solid ${isSelected ? pathway.accent : '#D1D5DB'}`,
                }}
              >
                {isSelected && (
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path
                      d="M2 5L4 7L8 3"
                      stroke="white"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </div>

              <div className="mt-6">
                <div
                  className="font-semibold text-base mb-1"
                  style={{
                    color: isSelected ? pathway.accent : '#1A1A1A',
                    fontFamily: 'var(--font-dm-sans), sans-serif',
                  }}
                >
                  {pathway.name}
                </div>
                <div
                  className="text-xl font-bold mb-4"
                  style={{
                    color: pathway.accent,
                    fontFamily: 'var(--font-dm-serif), serif',
                    fontWeight: 400,
                  }}
                >
                  {pathway.price}
                </div>
                <ul className="space-y-2">
                  {pathway.features.map((feature) => (
                    <li
                      key={feature}
                      className="flex items-center gap-2 text-sm"
                      style={{ color: '#1A1A1A' }}
                    >
                      <span
                        className="w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0"
                        style={{ background: pathway.accentLight }}
                      >
                        <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                          <path
                            d="M1.5 4L3 5.5L6.5 2"
                            stroke={pathway.accent}
                            strokeWidth="1.25"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </span>
                      {feature}
                    </li>
                  ))}
                </ul>
              </div>
            </button>
          )
        })}
      </div>

      {/* Bundle nudge */}
      <p
        className="text-center text-sm py-2 px-4 rounded-lg"
        style={{
          color: '#0F6E56',
          background: '#E1F5EE',
          fontFamily: 'var(--font-dm-sans), sans-serif',
        }}
      >
        Select both for the full Sasha experience — <strong>20% bundle discount applied</strong>
      </p>
    </div>
  )
}
