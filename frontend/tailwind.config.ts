import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#F8F9FA',
        paper: '#FCFBF8',
        ink: '#2F2A25',
        muted: '#80776E',
        clay: '#E8D8C7',
        clayDeep: '#B98D68',
        sage: '#DDE5DA',
        moss: '#65735D',
        line: '#E7E1D8',
      },
      boxShadow: {
        soft: '0 18px 60px rgba(62, 49, 36, 0.10)',
        quiet: '0 10px 30px rgba(62, 49, 36, 0.07)',
        focus: '0 0 0 4px rgba(185, 141, 104, 0.14), 0 16px 44px rgba(62, 49, 36, 0.10)',
      },
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        display: ['ui-serif', 'Georgia', 'Cambria', 'Times New Roman', 'serif'],
      },
      borderRadius: {
        '4xl': '2rem',
      },
    },
  },
  plugins: [],
} satisfies Config
