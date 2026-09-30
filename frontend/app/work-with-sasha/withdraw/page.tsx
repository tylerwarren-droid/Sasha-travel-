import type { Metadata } from 'next'
import LinkAction from '../LinkAction'
import { langOf } from '../copy'

export const metadata: Metadata = { title: 'Withdraw · Work with Sasha', robots: { index: false } }

/** S-55 · Withdrawal by the emailed link: every one of Sasha's channels to the venue stops, phone and email included. */
export default async function Page({ searchParams }: { searchParams: Promise<{ [k: string]: string | string[] | undefined }> }) {
  const q = await searchParams
  return <LinkAction mode="withdraw" token={typeof q.t === 'string' ? q.t : ''} lang={langOf(q.lang)} />
}
