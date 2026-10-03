import type { Metadata } from 'next'
import { TabPage } from '../components/site/TabPage'
import { relocation } from '../(site)/content'

// Sasha 123 · the new project.kanoe.ai (kanoe-site-scope.md §9, copy §11). The previous home page is /archive.
export const metadata: Metadata = {
  title: relocation.title,
  description: relocation.description,
  openGraph: { title: relocation.title, description: relocation.description, siteName: 'Kanoe', type: 'website', url: relocation.route },
}

export default function Page() {
  return <TabPage tab={relocation} />
}
