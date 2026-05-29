'use client'

import React from 'react'
import { OnboardingData } from '../types'

interface Step5Props {
  data: OnboardingData
  onChange: (partial: Partial<OnboardingData>) => void
}

interface AgentDef {
  id: string
  icon: string
  name: string
  description: string
  defaultEnabled: boolean
  custom?: boolean
  price?: string
}

const CORE_AGENTS: AgentDef[] = [
  {
    id: 'restaurant',
    icon: '🍽️',
    name: 'Restaurant Concierge',
    description: 'Table reservations & dining recommendations',
    defaultEnabled: true,
  },
  {
    id: 'health',
    icon: '⚕️',
    name: 'Health & Medical',
    description: 'Doctor referrals, pharmacy, clinic info',
    defaultEnabled: true,
  },
  {
    id: 'beauty',
    icon: '💆',
    name: 'Beauty & Wellness',
    description: 'Spa, massage, beauty bookings',
    defaultEnabled: true,
  },
  {
    id: 'golf',
    icon: '⛳',
    name: 'Golf Concierge',
    description: 'Tee times, course recommendations',
    defaultEnabled: true,
  },
  {
    id: 'petcare',
    icon: '🐾',
    name: 'Pet Care',
    description: 'Dog walkers, boarding, grooming',
    defaultEnabled: true,
  },
  {
    id: 'booking',
    icon: '📋',
    name: 'Booking Confirmation',
    description: 'PMS reference retrieval, hotel contact',
    defaultEnabled: true,
  },
]

const CUSTOM_AGENTS: AgentDef[] = [
  {
    id: 'scuba',
    icon: '🤿',
    name: 'Scuba & Diving',
    description: 'Dive centres, PADI courses, equipment',
    defaultEnabled: false,
    custom: true,
    price: '+$99/mo',
  },
  {
    id: 'surf',
    icon: '🏄',
    name: 'Surf Concierge',
    description: 'Surf schools, break conditions, lessons',
    defaultEnabled: false,
    custom: true,
    price: '+$99/mo',
  },
  {
    id: 'transfers',
    icon: '🚌',
    name: 'Transfers & Transport',
    description: 'Airport pickups, private drivers, car hire',
    defaultEnabled: false,
    custom: true,
    price: '+$99/mo',
  },
]

interface AgentCardProps {
  agent: AgentDef
  enabled: boolean
  onToggle: () => void
  // eslint-disable-next-line react/no-unused-prop-types
  key?: React.Key
}

function ToggleSwitch({ enabled, onToggle }: { enabled: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="relative inline-flex h-5 w-9 items-center rounded-full transition-all duration-200 flex-shrink-0"
      style={{
        background: enabled ? '#0F6E56' : '#D1D5DB',
      }}
      role="switch"
      aria-checked={enabled}
    >
      <span
        className="inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-all duration-200"
        style={{
          transform: enabled ? 'translateX(18px)' : 'translateX(2px)',
        }}
      />
    </button>
  )
}

function AgentCard({ agent, enabled, onToggle }: AgentCardProps) {
  return (
    <div
      className="rounded-xl border p-4 flex flex-col gap-3 transition-all duration-150"
      style={{
        borderColor: enabled ? '#0F6E56' : '#E5E7EB',
        background: enabled ? '#F9FFFE' : '#ffffff',
        boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div
            className="flex items-center justify-center rounded-full flex-shrink-0"
            style={{
              width: '2.25rem',
              height: '2.25rem',
              background: '#E1F5EE',
              fontSize: '1.1rem',
            }}
          >
            {agent.icon}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className="font-medium text-sm"
                style={{ color: '#1A1A1A', fontFamily: 'var(--font-dm-sans), sans-serif' }}
              >
                {agent.name}
              </span>
              {agent.custom && agent.price && (
                <span
                  className="text-xs px-1.5 py-0.5 rounded-full font-medium"
                  style={{ background: '#FAEEDA', color: '#BA7517' }}
                >
                  {agent.price}
                </span>
              )}
            </div>
            <p className="text-xs mt-0.5" style={{ color: '#6B6B6B' }}>
              {agent.description}
            </p>
          </div>
        </div>
        <ToggleSwitch enabled={enabled} onToggle={onToggle} />
      </div>
    </div>
  )
}

export default function Step5Agents({ data, onChange }: Step5Props) {
  const toggleAgent = (id: string) => {
    onChange({
      agents: {
        ...data.agents,
        [id]: !data.agents[id],
      },
    })
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
          Choose your agents
        </h2>
        <p style={{ fontSize: '0.9rem', color: '#6B6B6B' }}>
          Select which specialist agents Sasha should be able to activate for your guests.
        </p>
      </div>

      {/* Core agents */}
      <div>
        <h3
          className="text-sm font-semibold mb-3"
          style={{ color: '#1A1A1A', fontFamily: 'var(--font-dm-sans), sans-serif' }}
        >
          Core agents
          <span
            className="ml-2 text-xs font-normal px-1.5 py-0.5 rounded-full"
            style={{ background: '#E1F5EE', color: '#0F6E56' }}
          >
            All included
          </span>
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {CORE_AGENTS.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              enabled={data.agents[agent.id] ?? true}
              onToggle={() => toggleAgent(agent.id)}
            />
          ))}
        </div>
      </div>

      {/* Custom agents */}
      <div>
        <h3
          className="text-sm font-semibold mb-1"
          style={{ color: '#1A1A1A', fontFamily: 'var(--font-dm-sans), sans-serif' }}
        >
          Add specialist agents
        </h3>
        <p className="text-xs mb-3" style={{ color: '#6B6B6B' }}>
          Expand Sasha&apos;s capabilities with domain experts. Each +$99/mo
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {CUSTOM_AGENTS.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              enabled={data.agents[agent.id] ?? false}
              onToggle={() => toggleAgent(agent.id)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
