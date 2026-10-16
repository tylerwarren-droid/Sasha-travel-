import { NextResponse } from 'next/server'

/** Sasha 274 · item 1: the release now live (its commit). An open /s2 page compares it with the build it was made from
 *  (NEXT_PUBLIC_BUILD) when it comes back or a turn ends, and reloads at a safe moment when they differ. Public: a commit id only. */
export const dynamic = 'force-dynamic'

export async function GET(): Promise<Response> {
  return NextResponse.json({ build: process.env.VERCEL_GIT_COMMIT_SHA || 'dev' }, { headers: { 'cache-control': 'no-store' } })
}
