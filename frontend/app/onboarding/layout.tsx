import type { ReactNode } from 'react'
import { DM_Sans, DM_Serif_Display } from 'next/font/google'

const dmSans = DM_Sans({
  subsets: ['latin'],
  variable: '--font-dm-sans',
  display: 'swap',
})

const dmSerifDisplay = DM_Serif_Display({
  weight: ['400'],
  subsets: ['latin'],
  variable: '--font-dm-serif',
  display: 'swap',
})

export default function OnboardingLayout({
  children,
}: {
  children: ReactNode
}) {
  return (
    <div
      className={`${dmSans.variable} ${dmSerifDisplay.variable}`}
      style={{ fontFamily: 'var(--font-dm-sans), system-ui, sans-serif' }}
    >
      <style>{`
        .onboarding-root {
          background: #ffffff !important;
          color: #1A1A1A !important;
          min-height: 100vh;
        }
      `}</style>
      <div className="onboarding-root">
        {/* Nav bar */}
        <nav className="border-b border-gray-200 bg-white sticky top-0 z-50">
          <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
            <span
              style={{
                fontFamily: 'var(--font-dm-serif), serif',
                color: '#0F6E56',
                fontSize: '1.375rem',
                fontWeight: 400,
                letterSpacing: '-0.01em',
              }}
            >
              Kanoe
            </span>
            <span
              style={{
                fontFamily: 'var(--font-dm-sans), sans-serif',
                fontSize: '0.8125rem',
                color: '#6B6B6B',
              }}
            >
              Need help?{' '}
              <a
                href="mailto:hello@kanoe.ai"
                style={{ color: '#0F6E56', textDecoration: 'none' }}
              >
                hello@kanoe.ai
              </a>
            </span>
          </div>
        </nav>
        {children}
      </div>
    </div>
  )
}
