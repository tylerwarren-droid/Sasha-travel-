import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Sasha 104 · the link preview (WhatsApp, iMessage, Slack) for every page without its own: no Vietnam
const PREVIEW = { title: "Sasha by Kanoe: AI concierge",
  description: "Talk to Sasha: she finds places and books them for you — only after your yes." };
export const metadata: Metadata = {
  metadataBase: new URL("https://project.kanoe.ai"),
  title: PREVIEW.title,
  description: PREVIEW.description,
  openGraph: { ...PREVIEW, siteName: "Sasha by Kanoe", type: "website", url: "/" },
  twitter: { card: "summary", ...PREVIEW },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      // The portal stylesheet sets `html{scroll-behavior:smooth}`. Without this attribute Next
      // warns, and its scroll restoration animates between routes instead of jumping — so a
      // tab change visibly scrolls through the previous page on the way to the top.
      data-scroll-behavior="smooth"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
