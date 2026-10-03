import type { Metadata } from 'next'
import { TabPage } from './components/site/TabPage'
import { agapi } from './(site)/content'

// Sasha 123 · the new project.kanoe.ai (kanoe-site-scope.md §9, copy §11). The previous home page is /archive.
export const metadata: Metadata = {
  title: agapi.title,
  description: agapi.description,
  openGraph: { title: agapi.title, description: agapi.description, siteName: 'Kanoe', type: 'website', url: agapi.route },
}

export default function Page() {
  return <TabPage tab={agapi} />
}
