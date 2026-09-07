/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50:  '#eff6ff',
          100: '#dbeafe',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
        // Eigene Palette für das Eigentümer-Portal, 1:1 aus dem abgenommenen
        // Mockup (docs/immocore_portal_mockup.html). Bewusst getrennt von
        // 'primary': das Portal ist eine eigene Anwendung für Eigentümer und
        // teilt die Optik der Verwaltungsoberfläche nicht.
        portal: {
          ink: '#1c2430',
          soft: '#5a6472',
          paper: '#f6f7f9',
          line: '#e2e5ea',
          brand: '#2f5d50',
          'brand-soft': '#eaf1ee',
          accent: '#b5651d',
          debit: '#a13a3a',
          credit: '#2f7d5a',
        },
      },
    },
  },
  plugins: [],
}
