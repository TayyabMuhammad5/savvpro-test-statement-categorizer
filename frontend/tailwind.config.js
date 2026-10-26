/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        serif: ['"Instrument Serif"', 'Georgia', 'serif'],
        sans: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        brand: {
          terracotta: '#FF4F17',
          terracottaDark: '#D34516',
          terracottaLight: '#FFF2EC',
          cream: '#F3EFE6',
          creamDark: '#EAE4D7',
          ink: '#141311',
          muted: '#635E54',
          border: 'rgba(20, 19, 17, 0.12)',
        },
      },
    },
  },
  plugins: [],
};
