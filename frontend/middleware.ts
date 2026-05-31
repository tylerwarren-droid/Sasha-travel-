import { NextResponse, type NextRequest } from 'next/server'

// App is fully public — no auth required on any route.
export function middleware(request: NextRequest) {
  return NextResponse.next({ request })
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|api/).*)'],
}
