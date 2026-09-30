import type { Metadata } from 'next'
import WorkWithSasha from './WorkWithSasha'
import { langOf } from './copy'

export const metadata: Metadata = { title: 'Work with Sasha · Trabaja con Sasha' }

/** S-55 · The venue opt-in page. ?lang=es for Spanish. Public: no founder session. */
export default async function Page({ searchParams }: { searchParams: Promise<{ [k: string]: string | string[] | undefined }> }) {
  return <WorkWithSasha lang={langOf((await searchParams).lang)} />
}
