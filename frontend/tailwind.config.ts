import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#2563EB',
          hover: '#1D4ED8',
          light: '#3B82F6',
        },
        surface: {
          DEFAULT: '#0F172A',
          card: '#1E293B',
          border: '#334155',
          muted: '#475569',
        },
      },
    },
  },
  plugins: [],
} satisfies Config
