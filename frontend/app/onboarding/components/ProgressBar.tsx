'use client'

interface ProgressBarProps {
  step: number
}

const STEPS = [
  { num: 1, label: 'Account' },
  { num: 2, label: 'Pathway' },
  { num: 3, label: 'Persona' },
  { num: 4, label: 'Inventory' },
  { num: 5, label: 'Agents' },
  { num: 6, label: 'Deploy' },
]

export default function ProgressBar({ step }: ProgressBarProps) {
  return (
    <div className="bg-white border-b border-gray-200 py-4">
      <div className="max-w-5xl mx-auto px-6">
        <div className="flex items-center justify-between">
          {STEPS.map((s, idx) => {
            const isCompleted = step > s.num
            const isCurrent = step === s.num
            const isLast = idx === STEPS.length - 1

            return (
              <div key={s.num} className="flex items-center flex-1 last:flex-none">
                {/* Step circle + label */}
                <div className="flex flex-col items-center gap-1 flex-shrink-0">
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-all duration-200"
                    style={{
                      background: isCompleted
                        ? '#0F6E56'
                        : 'transparent',
                      border: isCompleted
                        ? 'none'
                        : isCurrent
                        ? '2px solid #0F6E56'
                        : '2px solid #D1D5DB',
                      color: isCompleted
                        ? '#ffffff'
                        : isCurrent
                        ? '#0F6E56'
                        : '#9CA3AF',
                    }}
                  >
                    {isCompleted ? (
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path
                          d="M2 7L5.5 10.5L12 3.5"
                          stroke="white"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    ) : (
                      s.num
                    )}
                  </div>
                  <span
                    style={{
                      fontSize: '11px',
                      fontFamily: 'var(--font-dm-sans), sans-serif',
                      color: isCurrent ? '#0F6E56' : isCompleted ? '#0F6E56' : '#9CA3AF',
                      fontWeight: isCurrent ? 600 : 400,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {s.label}
                  </span>
                </div>

                {/* Connector line */}
                {!isLast && (
                  <div
                    className="h-0.5 flex-1 mx-2 mt-[-18px]"
                    style={{
                      background: step > s.num ? '#0F6E56' : '#E5E7EB',
                    }}
                  />
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
