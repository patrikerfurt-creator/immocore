import { useEffect, useMemo, useRef, useState } from 'react'
import { EditorContent, useEditor, useEditorState } from '@tiptap/react'
import type { Editor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import {
  PlatzhalterAutovervollstaendigung, PlatzhalterChip,
} from './tiptapErweiterungen'
import type { AutovervollstaendigungZustand } from './tiptapErweiterungen'
import { editorHtmlZuJinja, jinjaZuEditorHtml } from './blockModell'

export interface PlatzhalterVorschlag {
  name: string
  beschreibung: string
}

interface Props {
  /** Gespeicherter Blocktext (Jinja); wird nur beim Mounten geladen. */
  inhalt: string
  onChange: (inhalt: string) => void
  platzhalter: PlatzhalterVorschlag[]
  readOnly?: boolean
  onFokus?: (editor: Editor) => void
  label: string
}

const MAX_VORSCHLAEGE = 8

/** Ein TipTap-Editor für den Rich-Text-Körper eines Blocks (text / bedingt / anlage_seite). */
export function BlockTextEditor({ inhalt, onChange, platzhalter, readOnly = false, onFokus, label }: Props) {
  const [ac, setAc] = useState<AutovervollstaendigungZustand | null>(null)
  const [acIndex, setAcIndex] = useState(0)

  const vorschlaege = useMemo(() => {
    if (!ac) return []
    const suche = ac.suche.toLowerCase()
    return platzhalter
      .filter(p => p.name.toLowerCase().includes(suche))
      .slice(0, MAX_VORSCHLAEGE)
  }, [ac, platzhalter])

  // Die Erweiterungs-Callbacks werden nur einmal beim Anlegen des Editors gebunden —
  // aktuelle Werte deshalb über Refs lesen.
  const editorRef = useRef<Editor | null>(null)
  const acRef = useRef(ac)
  const vorschlaegeRef = useRef(vorschlaege)
  const acIndexRef = useRef(acIndex)
  const onChangeRef = useRef(onChange)
  const onFokusRef = useRef(onFokus)
  acRef.current = ac
  vorschlaegeRef.current = vorschlaege
  acIndexRef.current = acIndex
  onChangeRef.current = onChange
  onFokusRef.current = onFokus

  function uebernehmen(name: string) {
    const editor = editorRef.current
    const zustand = acRef.current
    if (!editor || !zustand) return
    editor.chain().focus()
      .insertContentAt({ from: zustand.von, to: zustand.bis }, [
        { type: 'platzhalter', attrs: { ausdruck: name } },
        { type: 'text', text: ' ' },
      ])
      .run()
    setAc(null)
  }
  const uebernehmenRef = useRef(uebernehmen)
  uebernehmenRef.current = uebernehmen

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false, codeBlock: false, blockquote: false, code: false, strike: false,
        horizontalRule: false, link: false, underline: false,
      }),
      PlatzhalterChip,
      PlatzhalterAutovervollstaendigung.configure({
        onZustand: z => {
          setAc(z)
          setAcIndex(0)
        },
        onTaste: event => {
          const liste = vorschlaegeRef.current
          if (!acRef.current || liste.length === 0) return false
          if (event.key === 'ArrowDown') {
            setAcIndex(i => (i + 1) % liste.length)
            return true
          }
          if (event.key === 'ArrowUp') {
            setAcIndex(i => (i - 1 + liste.length) % liste.length)
            return true
          }
          if (event.key === 'Enter' || event.key === 'Tab') {
            uebernehmenRef.current(liste[Math.min(acIndexRef.current, liste.length - 1)].name)
            return true
          }
          if (event.key === 'Escape') {
            setAc(null)
            return true
          }
          return false
        },
      }),
    ],
    content: jinjaZuEditorHtml(inhalt),
    editable: !readOnly,
    editorProps: {
      attributes: { 'aria-label': label, class: 'px-3 py-2 text-sm' },
    },
    onUpdate: ({ editor: e }) => onChangeRef.current(editorHtmlZuJinja(e.getHTML())),
    onFocus: ({ editor: e }) => onFokusRef.current?.(e),
    onBlur: () => setAc(null),
  })
  editorRef.current = editor

  // emitUpdate=false: setEditable löst sonst ein „update“-Ereignis aus und würde die
  // Version beim bloßen Öffnen als geändert markieren.
  useEffect(() => {
    if (editor && editor.isEditable === readOnly) editor.setEditable(!readOnly, false)
  }, [editor, readOnly])

  const aktiv = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      fett: e?.isActive('bold') ?? false,
      kursiv: e?.isActive('italic') ?? false,
      aufzaehlung: e?.isActive('bulletList') ?? false,
      nummeriert: e?.isActive('orderedList') ?? false,
    }),
  })

  if (!editor) return null

  const knopf = (aktivFlag: boolean) =>
    `px-2 py-0.5 text-xs rounded border ${aktivFlag ? 'bg-primary-100 border-primary-400' : 'bg-white border-gray-300 hover:bg-gray-50'}`

  return (
    <div className="border border-gray-300 rounded bg-white">
      {!readOnly && (
        <div className="flex gap-1 border-b border-gray-200 px-2 py-1 bg-gray-50 rounded-t" role="toolbar" aria-label="Formatierung">
          <button type="button" className={`${knopf(aktiv?.fett ?? false)} font-bold`} title="Fett"
            onMouseDown={e => e.preventDefault()}
            onClick={() => editor.chain().focus().toggleBold().run()}>F</button>
          <button type="button" className={`${knopf(aktiv?.kursiv ?? false)} italic`} title="Kursiv"
            onMouseDown={e => e.preventDefault()}
            onClick={() => editor.chain().focus().toggleItalic().run()}>K</button>
          <button type="button" className={knopf(aktiv?.aufzaehlung ?? false)} title="Aufzählung"
            onMouseDown={e => e.preventDefault()}
            onClick={() => editor.chain().focus().toggleBulletList().run()}>• Liste</button>
          <button type="button" className={knopf(aktiv?.nummeriert ?? false)} title="Nummerierte Liste"
            onMouseDown={e => e.preventDefault()}
            onClick={() => editor.chain().focus().toggleOrderedList().run()}>1. Liste</button>
          <span className="ml-auto text-xs text-gray-400 self-center">
            „{'{{'}“ tippen für Platzhalter
          </span>
        </div>
      )}
      <div className="vorlagen-text">
        <EditorContent editor={editor} />
      </div>

      {ac && vorschlaege.length > 0 && (
        <ul
          role="listbox"
          aria-label="Platzhalter-Vorschläge"
          className="fixed z-50 bg-white border border-gray-300 rounded shadow-lg text-sm max-h-64 overflow-auto w-80"
          style={{ left: ac.links, top: ac.unten + 4 }}
        >
          {vorschlaege.map((p, i) => (
            <li
              key={p.name}
              role="option"
              aria-selected={i === acIndex}
              className={`px-3 py-1.5 cursor-pointer ${i === acIndex ? 'bg-primary-100' : 'hover:bg-gray-50'}`}
              onMouseDown={e => {
                e.preventDefault()
                uebernehmen(p.name)
              }}
            >
              <div className="font-mono text-xs text-blue-800">{p.name}</div>
              <div className="text-xs text-gray-500 truncate">{p.beschreibung}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Fügt einen Platzhalter-Chip an der Cursorposition des Editors ein. */
export function platzhalterEinfuegen(editor: Editor, name: string) {
  editor.chain().focus()
    .insertContent([{ type: 'platzhalter', attrs: { ausdruck: name } }, { type: 'text', text: ' ' }])
    .run()
}
