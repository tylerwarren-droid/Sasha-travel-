'use client'

import { useState } from 'react'
import { OnboardingData } from '../types'

interface Step6Props {
  data: OnboardingData
  onGoLive: () => Promise<void>
}

const CHECKLIST_ITEMS = [
  'Inventory uploaded and reviewed',
  'Welcome message tested',
  'Persona name confirmed',
  'Commission model agreed',
  'Team briefed on handoff process',
  'Test conversation completed',
]

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // fallback
    }
  }
  return (
    <button
      type="button"
      onClick={handleCopy}
      className="text-xs px-2.5 py-1 rounded-lg transition-all duration-150 font-medium flex-shrink-0"
      style={{
        background: copied ? '#E1F5EE' : '#F4F3EF',
        color: copied ? '#0F6E56' : '#6B6B6B',
        fontFamily: 'var(--font-dm-sans), sans-serif',
      }}
    >
      {copied ? 'Copied!' : 'Copy'}
    </button>
  )
}

export default function Step6Deploy({ data, onGoLive }: Step6Props) {
  const [checklist, setChecklist] = useState<boolean[]>(
    new Array(CHECKLIST_ITEMS.length).fill(false)
  )
  const [isGoingLive, setIsGoingLive] = useState(false)
  const [isLive, setIsLive] = useState(false)

  const slug = data.slug || data.business_name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

  const sashaUrl = `https://sasha.kanoe.ai/${slug}`
  const embedCode = `<script src="https://cdn.kanoe.ai/sasha.js" data-client="${slug}" async></script>`
  const apiEndpoint = `https://api.kanoe.ai/${slug}`

  const allChecked = checklist.every(Boolean)

  const toggleCheck = (idx: number) => {
    setChecklist((prev: boolean[]) => prev.map((v: boolean, i: number) => (i === idx ? !v : v)))
  }

  const handleGoLive = async () => {
    if (!allChecked || isGoingLive) return
    setIsGoingLive(true)
    try {
      await onGoLive()
      setIsLive(true)
    } finally {
      setIsGoingLive(false)
    }
  }

  if (isLive) {
    return (
      <div className="space-y-6">
        <div
          className="rounded-2xl p-8 text-center"
          style={{
            background: 'linear-gradient(135deg, #0F6E56 0%, #1D9E75 100%)',
          }}
        >
          <div className="text-4xl mb-3">🎉</div>
          <h2
            style={{
              fontFamily: 'var(--font-dm-serif), serif',
              fontSize: '2rem',
              color: '#ffffff',
              fontWeight: 400,
              marginBottom: '0.5rem',
            }}
          >
            Sasha is live!
          </h2>
          <p style={{ color: '#E1F5EE', fontSize: '0.9rem', marginBottom: '1rem' }}>
            Your AI concierge is now active and ready to delight guests.
          </p>
          <div
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl"
            style={{ background: 'rgba(255,255,255,0.2)' }}
          >
            <span style={{ color: '#ffffff', fontSize: '0.875rem' }}>{sashaUrl}</span>
            <CopyButton text={sashaUrl} />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Hero banner */}
      <div
        className="rounded-2xl p-7"
        style={{
          background: 'linear-gradient(135deg, #0F6E56 0%, #1D9E75 100%)',
        }}
      >
        <div className="text-3xl mb-2">🎉</div>
        <h2
          style={{
            fontFamily: 'var(--font-dm-serif), serif',
            fontSize: '1.875rem',
            color: '#ffffff',
            fontWeight: 400,
            marginBottom: '0.25rem',
          }}
        >
          You&apos;re almost live!
        </h2>
        <p style={{ color: '#E1F5EE', fontSize: '0.875rem' }}>
          Complete the checklist below and click Go Live to activate Sasha for your guests.
        </p>
      </div>

      {/* Info cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Card 1: Sasha URL */}
        <div
          className="rounded-xl border p-4 space-y-2"
          style={{ borderColor: '#E5E7EB', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}
        >
          <div className="text-xs font-medium uppercase tracking-wide" style={{ color: '#6B6B6B' }}>
            Your Sasha URL
          </div>
          <div
            className="text-sm break-all"
            style={{ color: '#1A1A1A', fontFamily: 'monospace' }}
          >
            {sashaUrl}
          </div>
          <CopyButton text={sashaUrl} />
        </div>

        {/* Card 2: Embed code */}
        <div
          className="rounded-xl border p-4 space-y-2"
          style={{ borderColor: '#E5E7EB', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}
        >
          <div className="text-xs font-medium uppercase tracking-wide" style={{ color: '#6B6B6B' }}>
            Embed Code
          </div>
          <div
            className="text-xs break-all rounded p-2"
            style={{
              color: '#0F6E56',
              background: '#F4F3EF',
              fontFamily: 'monospace',
              fontSize: '0.7rem',
            }}
          >
            {embedCode}
          </div>
          <CopyButton text={embedCode} />
        </div>

        {/* Card 3: API endpoint */}
        <div
          className="rounded-xl border p-4 space-y-2"
          style={{ borderColor: '#E5E7EB', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}
        >
          <div className="text-xs font-medium uppercase tracking-wide" style={{ color: '#6B6B6B' }}>
            API Endpoint
          </div>
          <div
            className="text-sm break-all"
            style={{ color: '#1A1A1A', fontFamily: 'monospace' }}
          >
            {apiEndpoint}
          </div>
          <CopyButton text={apiEndpoint} />
        </div>
      </div>

      {/* Go-live checklist */}
      <div
        className="rounded-xl border p-5"
        style={{ borderColor: '#E5E7EB', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}
      >
        <h3
          className="font-semibold mb-4"
          style={{
            color: '#1A1A1A',
            fontSize: '0.9375rem',
            fontFamily: 'var(--font-dm-sans), sans-serif',
          }}
        >
          Go-live checklist
        </h3>
        <div className="space-y-3">
          {CHECKLIST_ITEMS.map((item, idx) => (
            <label
              key={idx}
              className="flex items-center gap-3 cursor-pointer group"
            >
              <div
                className="w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 transition-all duration-150"
                style={{
                  borderColor: checklist[idx] ? '#0F6E56' : '#D1D5DB',
                  background: checklist[idx] ? '#0F6E56' : 'transparent',
                }}
                onClick={() => toggleCheck(idx)}
              >
                {checklist[idx] && (
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
              <input
                type="checkbox"
                checked={checklist[idx]}
                onChange={() => toggleCheck(idx)}
                className="sr-only"
              />
              <span
                className="text-sm transition-colors duration-150"
                style={{ color: checklist[idx] ? '#6B6B6B' : '#1A1A1A' }}
              >
                {item}
              </span>
            </label>
          ))}
        </div>

        {/* Progress */}
        <div className="mt-4 flex items-center gap-3">
          <div className="flex-1 h-1.5 rounded-full" style={{ background: '#E5E7EB' }}>
            <div
              className="h-1.5 rounded-full transition-all duration-300"
              style={{
                background: '#0F6E56',
                width: `${(checklist.filter(Boolean).length / CHECKLIST_ITEMS.length) * 100}%`,
              }}
            />
          </div>
          <span className="text-xs" style={{ color: '#6B6B6B' }}>
            {checklist.filter(Boolean).length}/{CHECKLIST_ITEMS.length} complete
          </span>
        </div>
      </div>

      {/* Go Live button */}
      <div className="flex justify-center pt-2">
        <button
          type="button"
          onClick={handleGoLive}
          disabled={!allChecked || isGoingLive}
          className="flex items-center gap-2 px-8 py-3.5 rounded-xl text-base font-semibold transition-all duration-150"
          style={{
            background: allChecked ? '#0F6E56' : '#D1D5DB',
            color: allChecked ? '#ffffff' : '#9CA3AF',
            cursor: allChecked && !isGoingLive ? 'pointer' : 'not-allowed',
            fontFamily: 'var(--font-dm-sans), sans-serif',
            boxShadow: allChecked ? '0 4px 14px rgba(15,110,86,0.3)' : 'none',
          }}
        >
          {isGoingLive ? (
            <>
              <svg className="animate-spin" width="18" height="18" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" strokeDasharray="31.416" strokeDashoffset="10" />
              </svg>
              Going live…
            </>
          ) : (
            <>🚀 Go Live</>
          )}
        </button>
      </div>

      {!allChecked && (
        <p className="text-center text-xs" style={{ color: '#9CA3AF' }}>
          Complete all checklist items to enable Go Live
        </p>
      )}
    </div>
  )
}
