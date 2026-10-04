// TipTap-Erweiterungen des Vorlagen-Editors:
//  - PlatzhalterChip: Inline-Knoten für `{{ ausdruck }}`
//  - PlatzhalterAutovervollstaendigung: erkennt `{{ teil` vor dem Cursor und meldet
//    Bereich + Position an React (Dropdown wird dort gerendert).
import { Extension, Node, mergeAttributes } from '@tiptap/react'
import { Plugin, PluginKey } from '@tiptap/pm/state'

export const PlatzhalterChip = Node.create({
  name: 'platzhalter',
  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      ausdruck: {
        default: '',
        parseHTML: (el: HTMLElement) => el.getAttribute('data-platzhalter') ?? '',
        renderHTML: () => ({}),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'span[data-platzhalter]' }]
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      'span',
      mergeAttributes(HTMLAttributes, {
        'data-platzhalter': node.attrs.ausdruck,
        class: 'inline-block rounded bg-blue-100 text-blue-800 px-1.5 mx-0.5 text-xs font-mono align-baseline',
      }),
      `{{ ${node.attrs.ausdruck} }}`,
    ]
  },

  renderText({ node }) {
    return `{{ ${node.attrs.ausdruck} }}`
  },
})

export interface AutovervollstaendigungZustand {
  /** Dokumentbereich von `{{` bis Cursor — wird beim Einfügen ersetzt. */
  von: number
  bis: number
  /** Bereits getippter Namensteil nach `{{`. */
  suche: string
  /** Viewport-Koordinaten (unterhalb der Cursorzeile) für das Dropdown. */
  links: number
  unten: number
}

export interface AutovervollstaendigungOptionen {
  onZustand: (zustand: AutovervollstaendigungZustand | null) => void
  /** Rückgabe true = Taste wurde vom Dropdown verbraucht. */
  onTaste: (event: KeyboardEvent) => boolean
}

const OFFEN = /\{\{\s*([\w.]*)$/
const schluessel = new PluginKey('platzhalterAutovervollstaendigung')

export const PlatzhalterAutovervollstaendigung = Extension.create<AutovervollstaendigungOptionen>({
  name: 'platzhalterAutovervollstaendigung',

  addOptions() {
    return { onZustand: () => {}, onTaste: () => false }
  },

  addProseMirrorPlugins() {
    const optionen = this.options
    let letzter = ''
    const melde = (z: AutovervollstaendigungZustand | null) => {
      const signatur = z ? `${z.von}|${z.bis}|${z.suche}` : ''
      if (signatur === letzter) return
      letzter = signatur
      optionen.onZustand(z)
    }

    return [
      new Plugin({
        key: schluessel,
        view: () => ({
          update: view => {
            const { selection } = view.state
            if (!selection.empty || !view.hasFocus()) return melde(null)
            const { $from } = selection
            const davor = $from.parent.textBetween(0, $from.parentOffset, undefined, '￼')
            const treffer = OFFEN.exec(davor)
            if (!treffer) return melde(null)
            let links = 0
            let unten = 0
            try {
              const koord = view.coordsAtPos(selection.from)
              links = koord.left
              unten = koord.bottom
            } catch {
              // z. B. in jsdom nicht berechenbar — Dropdown erscheint dann ohne Feinposition
            }
            melde({
              von: selection.from - treffer[0].length,
              bis: selection.from,
              suche: treffer[1],
              links,
              unten,
            })
          },
          destroy: () => melde(null),
        }),
        props: {
          handleKeyDown: (_view, event) => optionen.onTaste(event),
        },
      }),
    ]
  },
})
