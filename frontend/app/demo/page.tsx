import type { Metadata } from 'next'
import DemoPortal from '../components/portal/DemoPortal'

export const metadata: Metadata = {
  robots: { index: false, follow: false },   // Sasha 123 · an archive page (kanoe-site-scope.md §9.1)
  title: 'Live Demos — Kanoe.ai',
  description: 'Live Kanoe concierge demos: Luxurious Traveler, Vietnam and Phu Quoc.',
}

export default function DemoPage() {
  return <DemoPortal />
}
