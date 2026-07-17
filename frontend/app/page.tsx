import { redirect } from 'next/navigation'

// For now the root URL should open the polished "Discover Vietnam" concierge.
// (Temporary — change or remove this redirect when a dedicated home page is ready.)
export default function Home() {
  redirect('/vietnam')
}
