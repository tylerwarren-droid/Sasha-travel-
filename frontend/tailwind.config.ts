import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        teal: { DEFAULT: '#0F6E56', light: '#E1F5EE', mid: '#1D9E75' },
        gold: { DEFAULT: '#BA7517', light: '#FAEEDA' },
        ink: '#1A1A1A',
        muted: '#6B6B6B',
        subtle: '#F4F3EF',
      },
    },
  },
  plugins: [],
}

export default config
