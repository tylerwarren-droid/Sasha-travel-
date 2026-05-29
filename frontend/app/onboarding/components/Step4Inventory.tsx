'use client'

import React, { useState, useRef, type ChangeEvent } from 'react'
import { OnboardingData, InventoryItem } from '../types'

interface Step4Props {
  data: OnboardingData
  onChange: (partial: Partial<OnboardingData>) => void
}

type TabKey = 'hotels' | 'restaurants' | 'spas' | 'experiences'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'hotels', label: 'Hotels' },
  { key: 'restaurants', label: 'Restaurants' },
  { key: 'spas', label: 'Spas' },
  { key: 'experiences', label: 'Experiences' },
]

const inputClass =
  'border border-gray-200 rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-teal/30 focus:border-teal bg-white'
const labelClass = 'text-xs font-medium text-muted uppercase tracking-wide mb-1 block'

const TIER_COLORS: Record<InventoryItem['tier'], { bg: string; text: string }> = {
  Platinum: { bg: '#EDE9FE', text: '#6D28D9' },
  Gold: { bg: '#FAEEDA', text: '#BA7517' },
  Silver: { bg: '#F3F4F6', text: '#6B7280' },
}

function TierBadge({ tier }: { tier: InventoryItem['tier'] }) {
  const colors = TIER_COLORS[tier]
  return (
    <span
      className="text-xs font-medium px-2 py-0.5 rounded-full"
      style={{ background: colors.bg, color: colors.text }}
    >
      {tier}
    </span>
  )
}

interface InlineFormState {
  name: string
  location: string
  commission: string
  tier: InventoryItem['tier']
}

const defaultFormState: InlineFormState = {
  name: '',
  location: '',
  commission: '',
  tier: 'Gold',
}

export default function Step4Inventory({ data, onChange }: Step4Props) {
  const [activeTab, setActiveTab] = useState<TabKey>('hotels')
  const [showAddForm, setShowAddForm] = useState(false)
  const [formState, setFormState] = useState<InlineFormState>(defaultFormState)
  const [urlInput, setUrlInput] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const items: InventoryItem[] = data.inventory[activeTab as keyof typeof data.inventory]

  const updateInventory = (tab: TabKey, newItems: InventoryItem[]) => {
    onChange({
      inventory: {
        ...data.inventory,
        [tab]: newItems,
      },
    })
  }

  const handleAddItem = () => {
    if (!formState.name.trim()) return
    const newItem: InventoryItem = {
      name: formState.name.trim(),
      location: formState.location.trim(),
      commission: formState.commission.trim(),
      tier: formState.tier,
    }
    updateInventory(activeTab, [...items, newItem])
    setFormState(defaultFormState)
    setShowAddForm(false)
  }

  const handleDeleteItem = (idx: number) => {
    updateInventory(activeTab, items.filter((_item: InventoryItem, i: number) => i !== idx))
  }

  const handleCSV = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      const text = ev.target?.result as string
      const lines = text.split('\n').filter((l) => l.trim())
      const parsed: InventoryItem[] = []
      // Skip header row if it starts with "name"
      const startIdx = lines[0]?.toLowerCase().startsWith('name') ? 1 : 0
      for (let i = startIdx; i < lines.length; i++) {
        const cols = lines[i].split(',').map((c) => c.trim().replace(/^"|"$/g, ''))
        if (cols.length >= 1 && cols[0]) {
          const tier = (['Platinum', 'Gold', 'Silver'].includes(cols[3])
            ? cols[3]
            : 'Gold') as InventoryItem['tier']
          parsed.push({
            name: cols[0] || '',
            location: cols[1] || '',
            commission: cols[2] || '',
            tier,
          })
        }
      }
      updateInventory(activeTab, [...items, ...parsed])
    }
    reader.readAsText(file)
    // Reset file input
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handlePasteURL = () => {
    if (!urlInput.trim()) return
    onChange({
      inventory_urls: {
        ...data.inventory_urls,
        [activeTab]: urlInput.trim(),
      },
    })
    setUrlInput('')
  }

  return (
    <div className="space-y-5">
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
          Upload your inventory
        </h2>
        <p style={{ fontSize: '0.9rem', color: '#6B6B6B' }}>
          Add hotels, restaurants, spas, and experiences that Sasha can recommend.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200">
        {TABS.map((tab) => {
          const count = data.inventory[tab.key].length
          const isActive = activeTab === tab.key
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => {
                setActiveTab(tab.key)
                setShowAddForm(false)
                setFormState(defaultFormState)
              }}
              className="px-4 py-2.5 text-sm font-medium border-b-2 transition-all duration-150 flex items-center gap-1.5"
              style={{
                borderColor: isActive ? '#0F6E56' : 'transparent',
                color: isActive ? '#0F6E56' : '#6B6B6B',
                fontFamily: 'var(--font-dm-sans), sans-serif',
              }}
            >
              {tab.label}
              {count > 0 && (
                <span
                  className="text-xs px-1.5 py-0.5 rounded-full"
                  style={{
                    background: isActive ? '#E1F5EE' : '#F3F4F6',
                    color: isActive ? '#0F6E56' : '#6B7280',
                  }}
                >
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Action bar */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-150"
          style={{
            background: '#0F6E56',
            color: '#ffffff',
            fontFamily: 'var(--font-dm-sans), sans-serif',
          }}
        >
          <span>+ Add item</span>
        </button>

        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium border border-gray-200 transition-all duration-150 bg-white"
          style={{
            color: '#1A1A1A',
            fontFamily: 'var(--font-dm-sans), sans-serif',
          }}
        >
          Upload CSV
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleCSV}
        />

        <div className="flex items-center gap-2 flex-1 min-w-0">
          <input
            type="url"
            className={`${inputClass} flex-1 min-w-0`}
            placeholder="Paste curated list URL…"
            value={urlInput}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setUrlInput(e.target.value)}
            onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => {
              if (e.key === 'Enter') handlePasteURL()
            }}
          />
          {urlInput && (
            <button
              type="button"
              onClick={handlePasteURL}
              className="px-3 py-2 rounded-lg text-sm font-medium border"
              style={{
                borderColor: '#0F6E56',
                color: '#0F6E56',
                background: '#E1F5EE',
                fontFamily: 'var(--font-dm-sans), sans-serif',
                flexShrink: 0,
              }}
            >
              Add
            </button>
          )}
        </div>
      </div>

      {/* Inline add form */}
      {showAddForm && (
        <div
          className="rounded-xl border p-4 space-y-3"
          style={{ borderColor: '#E5E7EB', background: '#F4F3EF' }}
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Name</label>
              <input
                type="text"
                className={inputClass}
                placeholder="e.g. The Metropole Hotel"
                value={formState.name}
                onChange={(e: ChangeEvent<HTMLInputElement>) =>
                  setFormState((p: InlineFormState) => ({ ...p, name: e.target.value }))
                }
              />
            </div>
            <div>
              <label className={labelClass}>Location</label>
              <input
                type="text"
                className={inputClass}
                placeholder="e.g. Hanoi, Vietnam"
                value={formState.location}
                onChange={(e: ChangeEvent<HTMLInputElement>) =>
                  setFormState((p: InlineFormState) => ({ ...p, location: e.target.value }))
                }
              />
            </div>
            <div>
              <label className={labelClass}>Commission %</label>
              <input
                type="text"
                className={inputClass}
                placeholder="e.g. 15"
                value={formState.commission}
                onChange={(e: ChangeEvent<HTMLInputElement>) =>
                  setFormState((p: InlineFormState) => ({ ...p, commission: e.target.value }))
                }
              />
            </div>
            <div>
              <label className={labelClass}>Tier</label>
              <select
                className={inputClass}
                value={formState.tier}
                onChange={(e: ChangeEvent<HTMLSelectElement>) =>
                  setFormState((p: InlineFormState) => ({ ...p, tier: e.target.value as InventoryItem['tier'] }))
                }
              >
                <option value="Platinum">Platinum</option>
                <option value="Gold">Gold</option>
                <option value="Silver">Silver</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleAddItem}
              className="px-4 py-2 rounded-lg text-sm font-medium"
              style={{ background: '#0F6E56', color: '#ffffff' }}
            >
              Add
            </button>
            <button
              type="button"
              onClick={() => {
                setShowAddForm(false)
                setFormState(defaultFormState)
              }}
              className="px-4 py-2 rounded-lg text-sm font-medium border border-gray-200 bg-white"
              style={{ color: '#6B6B6B' }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      {items.length === 0 ? (
        <div
          className="rounded-xl border-2 border-dashed py-12 flex flex-col items-center justify-center gap-2"
          style={{ borderColor: '#E5E7EB' }}
        >
          <p style={{ color: '#6B6B6B', fontSize: '0.875rem' }}>
            No items yet — add manually or upload a CSV
          </p>
          <p style={{ color: '#9CA3AF', fontSize: '0.75rem' }}>
            CSV format: name, location, commission, tier
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border" style={{ borderColor: '#E5E7EB' }}>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: '#F4F3EF', borderBottom: '1px solid #E5E7EB' }}>
                <th
                  className="text-left px-4 py-2.5"
                  style={{
                    color: '#6B6B6B',
                    fontWeight: 500,
                    fontSize: '11px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  Name
                </th>
                <th
                  className="text-left px-4 py-2.5"
                  style={{
                    color: '#6B6B6B',
                    fontWeight: 500,
                    fontSize: '11px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  Location
                </th>
                <th
                  className="text-left px-4 py-2.5"
                  style={{
                    color: '#6B6B6B',
                    fontWeight: 500,
                    fontSize: '11px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  Commission %
                </th>
                <th
                  className="text-left px-4 py-2.5"
                  style={{
                    color: '#6B6B6B',
                    fontWeight: 500,
                    fontSize: '11px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  Tier
                </th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {items.map((item: InventoryItem, idx: number) => (
                <tr key={idx} className="border-t" style={{ borderColor: '#E5E7EB' }}>
                  <td className="px-4 py-3" style={{ color: '#1A1A1A' }}>
                    {item.name}
                  </td>
                  <td className="px-4 py-3" style={{ color: '#6B6B6B' }}>
                    {item.location}
                  </td>
                  <td className="px-4 py-3" style={{ color: '#6B6B6B' }}>
                    {item.commission ? `${item.commission}%` : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <TierBadge tier={item.tier} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => handleDeleteItem(idx)}
                      className="text-xs px-2 py-1 rounded hover:bg-red-50 transition-colors"
                      style={{ color: '#EF4444' }}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
