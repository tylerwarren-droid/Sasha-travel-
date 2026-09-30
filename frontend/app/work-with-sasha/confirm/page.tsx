import type { Metadata } from 'next'
import LinkAction from '../LinkAction'
import { langOf } from '../copy'

export const metadata: Metadata = { title: 'Confirm · Work with Sasha', robots: { index: false } }

/** S-55 · The double opt-in: the emailed link lands here. Opening it writes nothing; the Confirm button does. */
export default async function Page({ searchParams }: { searchParams: Promise<{ [k: string]: string | string[] | undefined }> }) {
  const q = await searchParams
  return <LinkAction mode="confirm" token={typeof q.t === 'string' ? q.t : ''} lang={langOf(q.lang)} />
}
