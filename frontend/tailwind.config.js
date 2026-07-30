/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Covenant Study gold palette
        gold: {
          DEFAULT: '#c9a227',
          dark:    '#a07d1a',
          muted:   '#6b5416',
          subtle:  '#3a2e0d',
        },
        // Dark background scale
        bg: {
          base:     '#0d0d0e',
          surface:  '#15151a',
          elevated: '#1e1e28',
          overlay:  '#252535',
        },
        // Text scale
        text: {
          primary:   '#e8e4d4',
          secondary: '#a09880',
          muted:     '#6b6455',
        },
        // Highlight colours matching existing backend data
        highlight: {
          yellow: '#ffe066',
          green:  '#b8f0c8',
          blue:   '#a0c8ff',
          red:    '#ffb3b3',
          purple: '#d4b3ff',
        },
      },
      fontFamily: {
        // Serifed body for scripture; fallback chain stays legible everywhere
        scripture: ['"Palatino Linotype"', 'Palatino', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      borderRadius: {
        DEFAULT: '0.5rem',
      },
      keyframes: {
        'slide-in-right': {
          from: { transform: 'translateX(100%)' },
          to:   { transform: 'translateX(0)' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
        'loading-sweep': {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      animation: {
        'slide-in-right': 'slide-in-right 0.25s ease-out',
        'fade-in':        'fade-in 0.15s ease-out',
        'loading-sweep':  'loading-sweep 1.5s linear infinite',
      },
    },
  },
  plugins: [],
}
