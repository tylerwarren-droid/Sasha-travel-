'use client'
/**
 * Sasha 349 · ONE answer to "is this a phone?" — /next's own rule (Sasha 214), moved here so every page asks the same question
 * (found live, 6 Nov: the Trip tab offered "Continue on my phone" ON his phone).
 */
import { useEffect, useState } from 'react'

export const PHONE_QUERY = '(max-width: 640px), (pointer: coarse) and (max-width: 920px) and (orientation: portrait)'

export function usePhone(): boolean {
  const [phone, setPhone] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia(PHONE_QUERY)
    const on = () => setPhone(mq.matches)
    on(); mq.addEventListener?.('change', on)
    return () => mq.removeEventListener?.('change', on)
  }, [])
  return phone
}
