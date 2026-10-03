import type { Metadata } from 'next'
import { TabPage } from '../components/site/TabPage'
import { campusme } from '../(site)/content'

// Sasha 123 · the new project.kanoe.ai (kanoe-site-scope.md §9, copy §11). The previous home page is /archive.
export const metadata: Metadata = {
  title: campusme.title,
  description: campusme.description,
  openGraph: { title: campusme.title, description: campusme.description, siteName: 'Kanoe', type: 'website', url: campusme.route },
}

export default function Page() {
  return <TabPage tab={campusme} />
}
