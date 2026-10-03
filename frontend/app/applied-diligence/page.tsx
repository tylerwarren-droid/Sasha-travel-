import type { Metadata } from 'next'
import { TabPage } from '../components/site/TabPage'
import { ad } from '../(site)/content'

// Sasha 123 · the new project.kanoe.ai (kanoe-site-scope.md §9, copy §11). The previous home page is /archive.
export const metadata: Metadata = {
  title: ad.title,
  description: ad.description,
  openGraph: { title: ad.title, description: ad.description, siteName: 'Kanoe', type: 'website', url: ad.route },
}

export default function Page() {
  return <TabPage tab={ad} />
}
