/**
 * Sasha 358 · THE ONE SOURCE OF FONTS: the files beside this module, in the repo (each family's OFL licence kept with it). Every page and
 * shell takes its fonts from here, through next/font/local — so no build fetches anything from the network (found 7 Nov: every Vercel
 * build failed because next/font/google couldn't reach Google Fonts, and nothing could deploy). tests: backend/tests/test_s358_fonts.py
 *
 *   Geist, Geist Mono       — Copyright 2024 The Geist Project Authors (OFL-Geist.txt, OFL-GeistMono.txt)
 *   DM Sans, DM Serif Display — Copyright the DM Sans / DM Serif Display Project Authors; Adobe (OFL-DMSans.txt, OFL-DMSerifDisplay.txt)
 */
import localFont from 'next/font/local'

export const geistSans = localFont({ src: './Geist-Variable.ttf', weight: '100 900', variable: '--font-geist-sans', display: 'swap' })
export const geistMono = localFont({ src: './GeistMono-Variable.ttf', weight: '100 900', variable: '--font-geist-mono', display: 'swap' })

// next/font reads each call's options literally (no spread): the same file, written out per variable
export const dmSans = localFont({ src: './DMSans-Variable.ttf', weight: '100 1000', style: 'normal', variable: '--font-dm-sans', display: 'swap' })
export const siteBody = localFont({ src: './DMSans-Variable.ttf', weight: '100 1000', style: 'normal', variable: '--site-body', display: 'swap' })

export const dmSerif = localFont({
  src: [{ path: './DMSerifDisplay-Regular.ttf', weight: '400', style: 'normal' }, { path: './DMSerifDisplay-Italic.ttf', weight: '400', style: 'italic' }],
  variable: '--font-dm-serif', display: 'swap',
})
export const siteHead = localFont({ src: './DMSerifDisplay-Regular.ttf', weight: '400', style: 'normal', variable: '--site-head', display: 'swap' })
