'use client'
import { useState, useEffect, useCallback, useRef } from 'react'
import { apiUrl, apiHeaders } from '@/lib/api'
import { User } from '@/types'

export interface Idea {
  title: string
  blurb: string
  days: number
  tags: string[]
  estimated_total_usd: number
  match?: string
  build_prompt: string
  // Real photo of the destination, attached server-side. Optional: the card's gradient shows
  // through when a lookup fails, so a missing image degrades quietly.
  image?: string
  image_thumb?: string
  image_by?: string
}

interface IdeasPanelProps {
  user: User
  // Sends the idea's build_prompt through the normal conductor turn, so the plan is built by
  // the same path as a spoken request and Sasha talks the guest through it.
  onBuild: (prompt: string) => void
  building: boolean
  // Ideas already fetched this session, held by the parent so they survive this panel
  // unmounting when the guest switches tabs.
  cached?: Idea[] | null
  onLoaded?: (ideas: Idea[]) => void
}

/**
 * The Ideas tab: ready-made trips, generated for THIS guest.
 *
 * The cards are pitches, not itineraries — the backend produces them from the guest's
 * preferences and past trips in one cheap call (it won't re-pitch somewhere they've already
 * been). Tapping "Build this" hands the idea's build_prompt to the conductor, so the actual
 * itinerary comes from the one real builder rather than a second, diverging code path.
 */
export default function IdeasPanel({ user, onBuild, building, cached, onLoaded }: IdeasPanelProps) {
  const [ideas, setIdeas] = useState<Idea[]>(cached ?? [])
  const [loading, setLoading] = useState(!cached?.length)
  const [failed, setFailed] = useState(false)
  const [builtTitle, setBuiltTitle] = useState<string | null>(null)
  // One id per session, owned by the page. A new visit gets a fresh set of ideas; switching
  // tabs within a visit does not.
  const visitIdRef = useRef<string>(
    typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Date.now())
  )

  const load = useCallback(async (force = false) => {
    setLoading(true)
    setFailed(false)
    try {
      const res = await fetch(apiUrl('/api/agents/ideas'), {
        method: 'POST',
        headers: apiHeaders(),
        body: JSON.stringify({
          name: user.display_name,
          travellers: user.travellers?.map(t => t.first_name).filter(Boolean) ?? [],
          preferences: user.preferences?.map(p => `${p.key.replace(/\./g, ' ')}: ${String(p.value).replace(/_/g, ' ')}`) ?? [],
          past_trips: user.past_trips?.map((t: any) => `${t.title} (${t.return_date})`) ?? [],
          session_id: visitIdRef.current,
          force,
        }),
      })
      if (!res.ok) throw new Error(String(res.status))
      const data = await res.json()
      const next = Array.isArray(data.ideas) ? data.ideas : []
      setIdeas(next)
      onLoaded?.(next)   // hand them up so they survive this panel unmounting
    } catch {
      setFailed(true)
    } finally {
      setLoading(false)
    }
  }, [user, onLoaded])

  // Only fetch when the parent has nothing cached — returning to this tab must not discard
  // the ideas the guest was already looking at.
  useEffect(() => { if (!cached?.length) load() }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <div className="lw-stream">
        <div className="lw-when">Ideas for you</div>
        {[0, 1, 2].map(i => <div className="lw-idea-skel" key={i} />)}
      </div>
    )
  }

  if (failed) {
    return (
      <div className="lw-stream">
        <div className="lw-empty">
          <div className="lw-empty-ic">💡</div>
          <div className="lw-empty-t">Couldn't load ideas</div>
          <div className="lw-empty-s">Sasha can still plan anything you ask for — just tell her where you'd like to go.</div>
          <button className="lw-empty-cta" onClick={() => load(true)}>Try again</button>
        </div>
      </div>
    )
  }

  return (
    <div className="lw-stream">
      <div className="lw-when">
        Ideas for you
        <button className="lw-refresh" onClick={() => load(true)} title="Generate new ideas">↻</button>
      </div>
      <p className="lw-lead">
        Built around how you travel, skipping the places you've already been. Pick one and Sasha
        plans it live.
      </p>

      {ideas.map((idea, i) => (
        <article className="lw-idea" key={`${idea.title}-${i}`}>
          <div className={`lw-idea-art art${(i % 3) + 1}`}>
            {idea.image && (
              <img src={idea.image_thumb || idea.image} alt={idea.title} loading="lazy" />
            )}
          </div>
          <div className="lw-idea-b">
            <div className="lw-idea-hd">
              <h3>{idea.title}</h3>
              {idea.match ? <span className="lw-idea-tag" title={idea.match}>Matches your taste</span> : null}
            </div>
            <p>{idea.blurb}</p>
            {idea.match ? <div className="lw-idea-why">✦ {idea.match}</div> : null}
            <div className="lw-idea-f">
              <span className="lw-idea-chips">
                {idea.days ? <i>{idea.days} days</i> : null}
                {(idea.tags || []).slice(0, 3).map(t => <i key={t}>{t}</i>)}
              </span>
              {idea.estimated_total_usd ? (
                <span className="lw-idea-price">${idea.estimated_total_usd.toLocaleString()}</span>
              ) : null}
              <button
                className="lw-idea-cta"
                disabled={building}
                onClick={() => { setBuiltTitle(idea.title); onBuild(idea.build_prompt) }}
              >
                {building && builtTitle === idea.title ? 'Building…' : 'Build this →'}
              </button>
            </div>
          </div>
        </article>
      ))}
    </div>
  )
}
