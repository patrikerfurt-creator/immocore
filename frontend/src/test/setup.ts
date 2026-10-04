// Vitest-Setup: erweitert `expect` um jest-dom-Matcher (z. B. toBeInTheDocument).
// Wird über vite.config.ts -> test.setupFiles vor jedem Testlauf geladen.
import '@testing-library/jest-dom'
import { configure } from '@testing-library/react'
import { vi } from 'vitest'

// jsdom kennt keine Layout-Geometrie; ProseMirror/TipTap (Vorlagen-Editor) ruft sie
// beim Scrollen zur Auswahl auf. Minimal-Polyfills, damit der Editor testbar ist.
const leereRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: function* () {} }) as unknown as DOMRectList
const leeresRect = () => ({ x: 0, y: 0, top: 0, left: 0, bottom: 0, right: 0, width: 0, height: 0, toJSON: () => ({}) }) as DOMRect
if (typeof Range !== 'undefined') {
  Range.prototype.getClientRects ??= leereRects
  Range.prototype.getBoundingClientRect ??= leeresRect
}
if (typeof Element !== 'undefined') {
  Element.prototype.getClientRects ??= leereRects
}
if (typeof document !== 'undefined') {
  document.elementFromPoint ??= () => null
}

// Im Docker-Container laufen die Testdateien parallel; TipTap-/userEvent-lastige Tests brauchen
// unter Last länger als die Vitest-Vorgabe von 5 s (Test) bzw. 1 s (findBy*/waitFor).
vi.setConfig({ testTimeout: 20000 })
configure({ asyncUtilTimeout: 5000 })
