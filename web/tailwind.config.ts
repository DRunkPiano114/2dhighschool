import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#faf6f0',
        ink: '#2c2c2c',
        'ink-light': '#666666',
        amber: '#d4a853',
        teal: '#5a8f7b',
        'bg-base': '#0d0d1a',
        'bg-stage': '#1a1a2e',
        'bg-narrative': '#141422',
        thought: {
          bg: 'rgba(255, 248, 235, 0.95)',
          border: '#e8dcc8',
        },
      },
      fontFamily: {
        hand: ['"LXGW WenKai"', 'cursive'],
        body: ['"Noto Sans SC"', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config
