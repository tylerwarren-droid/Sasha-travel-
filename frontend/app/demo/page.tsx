import type { Metadata } from 'next'
import DemoPortal from '../components/portal/DemoPortal'

export const metadata: Metadata = {
  title: 'Live Demos — Kanoe.ai',
  description: 'Live Kanoe concierge demos: Luxurious Traveler, Vietnam and Phu Quoc.',
}

export default function DemoPage() {
  return <DemoPortal />
}
