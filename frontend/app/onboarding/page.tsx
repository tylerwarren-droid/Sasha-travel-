'use client'

import { useState, useEffect, useCallback } from 'react'
import { OnboardingData, defaultOnboardingData } from './types'
import ProgressBar from './components/ProgressBar'
import Step1Account from './components/Step1Account'
import Step2Pathway from './components/Step2Pathway'
import Step3Prompt from './components/Step3Prompt'
import Step4Inventory from './components/Step4Inventory'
import Step5Agents from './components/Step5Agents'
import Step6Deploy from './components/Step6Deploy'

const DRAFT_KEY = 'kanoe_onboarding_draft'

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}

export default function OnboardingPage() {
  const [step, setStep] = useState(1)
  const [formData, setFormData] = useState<OnboardingData>(defaultOnboardingData)
  const [isSaving, setIsSaving] = useState(false)
  const [mounted, setMounted] = useState(false)

  // Load draft on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem(DRAFT_KEY)
      if (raw) {
        const parsed = JSON.parse(raw) as OnboardingData
        setFormData(parsed)
      }
    } catch {
      // ignore parse errors
    }
    setMounted(true)
  }, [])

  // Save draft on every formData change (after mount)
  useEffect(() => {
    if (!mounted) return
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(formData))
    } catch {
      // ignore storage errors
    }
  }, [formData, mounted])

  const handleChange = useCallback((partial: Partial<OnboardingData>) => {
    setFormData((prev: OnboardingData) => ({ ...prev, ...partial }))
  }, [])

  const saveDraft = async (data: OnboardingData) => {
    try {
      await fetch('/api/onboarding/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ formData: data }),
      })
    } catch {
      // non-blocking
    }
  }

  const handleNext = async () => {
    if (step >= 6) return
    setIsSaving(true)
    // Mark step as completed
    const updatedData: OnboardingData = {
      ...formData,
      slug: formData.slug || slugify(formData.business_name),
      completed_steps: Array.from(new Set([...formData.completed_steps, step])),
    }
    setFormData(updatedData)
    await saveDraft(updatedData)
    setIsSaving(false)
    setStep((prev: number) => prev + 1)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleBack = () => {
    if (step <= 1) return
    setStep((prev: number) => prev - 1)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleGoLive = async () => {
    const updatedData: OnboardingData = {
      ...formData,
      slug: formData.slug || slugify(formData.business_name),
      completed_steps: Array.from(new Set([...formData.completed_steps, 6])),
    }
    setFormData(updatedData)
    await fetch('/api/onboarding/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ formData: updatedData, goLive: true }),
    })
    // Clear draft
    try {
      localStorage.removeItem(DRAFT_KEY)
    } catch {
      // ignore
    }
  }

  if (!mounted) {
    // Avoid hydration mismatch
    return (
      <div style={{ minHeight: '100vh', background: '#ffffff' }}>
        <div style={{ height: '52px' }} />
      </div>
    )
  }

  const STEP_LABELS = ['Account', 'Pathway', 'Persona', 'Inventory', 'Agents', 'Deploy']

  return (
    <div style={{ minHeight: '100vh', background: '#ffffff' }}>
      <ProgressBar step={step} />

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        {step === 1 && <Step1Account data={formData} onChange={handleChange} />}
        {step === 2 && <Step2Pathway data={formData} onChange={handleChange} />}
        {step === 3 && <Step3Prompt data={formData} onChange={handleChange} />}
        {step === 4 && <Step4Inventory data={formData} onChange={handleChange} />}
        {step === 5 && <Step5Agents data={formData} onChange={handleChange} />}
        {step === 6 && <Step6Deploy data={formData} onGoLive={handleGoLive} />}

        {/* Bottom navigation */}
        {step < 6 && (
          <div
            className="flex items-center justify-between mt-10 pt-6 border-t"
            style={{ borderColor: '#E5E7EB' }}
          >
            <button
              type="button"
              onClick={handleBack}
              disabled={step === 1}
              className="px-5 py-2.5 rounded-xl text-sm font-medium border transition-all duration-150"
              style={{
                borderColor: step === 1 ? '#E5E7EB' : '#D1D5DB',
                color: step === 1 ? '#D1D5DB' : '#6B6B6B',
                background: '#ffffff',
                cursor: step === 1 ? 'not-allowed' : 'pointer',
                fontFamily: 'var(--font-dm-sans), sans-serif',
              }}
            >
              ← Back
            </button>

            <div className="flex items-center gap-3">
              <span className="text-xs" style={{ color: '#9CA3AF' }}>
                Step {step} of 5 — {STEP_LABELS[step - 1]}
              </span>
              <button
                type="button"
                onClick={handleNext}
                disabled={isSaving}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-150"
                style={{
                  background: isSaving ? '#D1D5DB' : '#0F6E56',
                  color: '#ffffff',
                  cursor: isSaving ? 'not-allowed' : 'pointer',
                  fontFamily: 'var(--font-dm-sans), sans-serif',
                  boxShadow: isSaving ? 'none' : '0 2px 8px rgba(15,110,86,0.25)',
                }}
              >
                {isSaving ? (
                  <>
                    <svg
                      className="animate-spin"
                      width="14"
                      height="14"
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
                    Saving…
                  </>
                ) : step === 5 ? (
                  'Save & Continue →'
                ) : (
                  'Next →'
                )}
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
