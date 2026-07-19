import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#2563EB',
          hover:   '#1D4ED8',
          light:   '#3B82F6',
          glow:    '#2563EB40',
        },
        surface: {
          DEFAULT: '#080D18',
          card:    '#0E1525',
          raised:  '#141E30',
          border:  '#1C2A3F',
          muted:   '#2D3F55',
        },
        accent: {
          purple: '#7C3AED',
          cyan:   '#06B6D4',
          green:  '#10B981',
          amber:  '#F59E0B',
          red:    '#EF4444',
        },
      },
      backgroundImage: {
        'gradient-primary': 'linear-gradient(135deg, #2563EB 0%, #7C3AED 100%)',
        'gradient-card':    'linear-gradient(145deg, #0E1525 0%, #141E30 100%)',
        'gradient-subtle':  'linear-gradient(135deg, #2563EB08 0%, #7C3AED08 100%)',
        'gradient-glow':    'radial-gradient(ellipse at top, #2563EB1A 0%, transparent 65%)',
        'shimmer':          'linear-gradient(90deg, transparent 0%, #ffffff0A 50%, transparent 100%)',
      },
      boxShadow: {
        'glow-sm':    '0 0 12px 0 #2563EB28',
        'glow-md':    '0 0 28px 0 #2563EB38',
        'glow-lg':    '0 0 56px 0 #2563EB28',
        'glow-purple':'0 0 24px 0 #7C3AED38',
        'card':       '0 4px 24px 0 #00000050',
        'card-hover': '0 8px 40px 0 #00000060, 0 0 0 1px #2563EB28',
      },
      keyframes: {
        'fade-in': {
          '0%':   { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          '0%':   { opacity: '0', transform: 'scale(0.96)' },
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
          '0%, 100%': { boxShadow: '0 0 12px 0 #2563EB28' },
          '50%':      { boxShadow: '0 0 28px 0 #2563EB50' },
        },
        'bounce-subtle': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%':      { transform: 'translateY(-4px)' },
        },
      },
      animation: {
        'fade-in':      'fade-in 0.3s ease-out both',
        'scale-in':     'scale-in 0.25s ease-out both',
        'slide-in':     'slide-in 0.3s ease-out both',
        'shimmer':      'shimmer 2s linear infinite',
        'pulse-glow':   'pulse-glow 2.5s ease-in-out infinite',
        'bounce-subtle':'bounce-subtle 1s ease-in-out infinite',
      },
    },
  },
  plugins: [],
} satisfies Config
