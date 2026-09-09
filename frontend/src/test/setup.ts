// Vitest-Setup: erweitert `expect` um jest-dom-Matcher (z. B. toBeInTheDocument).
// Wird über vite.config.ts -> test.setupFiles vor jedem Testlauf geladen.
import '@testing-library/jest-dom'
