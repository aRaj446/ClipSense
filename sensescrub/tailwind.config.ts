import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#D4A843',
          hover:   '#C49535',
          light:   '#E8C56A',
          glow:    '#D4A84330',
        },
        surface: {
          DEFAULT: '#0C0C14',
          card:    '#13131F',
          raised:  '#1A1A2E',
          border:  '#252538',
          muted:   '#363654',
        },
        accent: {
          violet: '#8B7CF6',
          rose:   '#F472B6',
          teal:   '#2DD4BF',
          amber:  '#F59E0B',
          red:    '#F87171',
          green:  '#4ADE80',
        },
        ink: {
          DEFAULT: '#F0EDE8',
          muted:   '#A8A4B8',
          faint:   '#5C5A72',
        },
      },
      backgroundImage: {
        'gradient-primary': 'linear-gradient(135deg, #D4A843 0%, #8B7CF6 100%)',
        'gradient-gold':    'linear-gradient(135deg, #D4A843 0%, #E8C56A 100%)',
        'gradient-card':    'linear-gradient(145deg, #13131F 0%, #1A1A2E 100%)',
        'gradient-subtle':  'linear-gradient(135deg, #D4A84308 0%, #8B7CF608 100%)',
      },
      boxShadow: {
        'glow-sm': '0 0 14px 0 #D4A84322',
        'glow-md': '0 0 32px 0 #D4A84332',
        'card':    '0 2px 20px 0 #00000055',
      },
      keyframes: {
        'fade-in': {
          '0%':   { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'spin-custom': {
          '0%':   { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
        'shimmer': {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition:  '200% 0' },
        },
      },
      animation: {
        'fade-in':    'fade-in 0.35s ease-out both',
        'spin':       'spin-custom 1s linear infinite',
        'shimmer':    'shimmer 2.2s linear infinite',
      },
    },
  },
  plugins: [],
} satisfies Config
