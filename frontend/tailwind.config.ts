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
        'shimmer':          'linear-gradient(90deg, transparent 0%, #ffffff08 50%, transparent 100%)',
      },
      boxShadow: {
        'glow-sm':    '0 0 14px 0 #D4A84322',
        'glow-md':    '0 0 32px 0 #D4A84332',
        'glow-lg':    '0 0 60px 0 #D4A84320',
        'glow-violet':'0 0 24px 0 #8B7CF630',
        'card':       '0 2px 20px 0 #00000055',
        'card-hover': '0 6px 36px 0 #00000065, 0 0 0 1px #D4A84322',
      },
      keyframes: {
        'fade-in': {
          '0%':   { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          '0%':   { opacity: '0', transform: 'scale(0.97)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'slide-in': {
          '0%':   { opacity: '0', transform: 'translateX(-10px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        'shimmer': {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition:  '200% 0' },
        },
        'pulse-glow': {
          '0%, 100%': { boxShadow: '0 0 14px 0 #D4A84322' },
          '50%':      { boxShadow: '0 0 32px 0 #D4A84344' },
        },
        'bounce-subtle': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%':      { transform: 'translateY(-4px)' },
        },
        'float': {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%':      { transform: 'translateY(-6px)' },
        },
      },
      animation: {
        'fade-in':      'fade-in 0.35s ease-out both',
        'scale-in':     'scale-in 0.25s ease-out both',
        'slide-in':     'slide-in 0.3s ease-out both',
        'shimmer':      'shimmer 2.2s linear infinite',
        'pulse-glow':   'pulse-glow 3s ease-in-out infinite',
        'bounce-subtle':'bounce-subtle 1.2s ease-in-out infinite',
        'float':        'float 4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
} satisfies Config
