import { describe, it, expect, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import type { Editor } from '@tiptap/react'
import { BlockTextEditor, platzhalterEinfuegen } from './BlockTextEditor'

const PLATZHALTER = [
  { name: 'empfaenger.briefanrede', beschreibung: 'Briefanrede' },
  { name: 'empfaenger.name', beschreibung: 'Name' },
  { name: 'mahnung.frist', beschreibung: 'Zahlungsfrist' },
]

/** Rendert den Editor und liefert die TipTap-Instanz über onFokus (im Test per editor.commands.focus()). */
function rendere(inhalt: string, extra: Partial<Parameters<typeof BlockTextEditor>[0]> = {}) {
  const onChange = vi.fn()
  let editor: Editor | undefined
  const ergebnis = render(
    <BlockTextEditor
      label="Testblock" inhalt={inhalt} onChange={onChange} platzhalter={PLATZHALTER}
      onFokus={e => { editor = e }} {...extra}
    />,
  )
  return { ...ergebnis, onChange, holeEditor: () => editor! }
}

describe('BlockTextEditor', () => {
  it('zeigt gespeicherte {{ }}-Platzhalter als Chips', async () => {
    const { container } = rendere('<p>Hallo {{ empfaenger.briefanrede }},</p>')
    const chip = await screen.findByText('{{ empfaenger.briefanrede }}')
    expect(chip).toHaveAttribute('data-platzhalter', 'empfaenger.briefanrede')
    expect(container.querySelector('[contenteditable="true"]')).not.toBeNull()
  })

  it('zeigt Text ohne Tags als Absätze', async () => {
    rendere('Erster Absatz\n\nZweiter Absatz')
    expect(await screen.findByText('Erster Absatz')).toBeInTheDocument()
    expect(screen.getByText('Zweiter Absatz')).toBeInTheDocument()
  })

  it('gibt Änderungen als Jinja-Text zurück (Chip -> {{ ausdruck }})', async () => {
    const { onChange, holeEditor } = rendere('<p>Hallo </p>')
    // Die Editor-Instanz kommt über onFokus (DOM-Fokus auf das Editierfeld).
    const feld = await screen.findByLabelText('Testblock')
    await act(async () => { feld.focus() })
    const editor = holeEditor()
    expect(editor).toBeDefined()

    await act(async () => { platzhalterEinfuegen(editor, 'mahnung.frist | datum') })
    const letzter = onChange.mock.calls[onChange.mock.calls.length - 1][0] as string
    expect(letzter).toContain('{{ mahnung.frist | datum }}')
    expect(letzter).not.toContain('data-platzhalter')
    expect(letzter).toContain('Hallo')
  })

  it('schlägt nach „{{“ passende Platzhalter vor und ersetzt beim Klick', async () => {
    const { onChange, holeEditor } = rendere('')
    const feld = await screen.findByLabelText('Testblock')
    await act(async () => { feld.focus() })
    const editor = holeEditor()

    await act(async () => { editor.chain().focus().insertContent('{{ empf').run() })
    const liste = await screen.findByRole('listbox', { name: 'Platzhalter-Vorschläge' })
    const optionen = screen.getAllByRole('option')
    expect(optionen).toHaveLength(2)
    expect(liste).toHaveTextContent('empfaenger.briefanrede')
    expect(liste).not.toHaveTextContent('mahnung.frist')

    // mousedown wie im echten Klick auf einen Eintrag
    await act(async () => {
      optionen[1].dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    })
    const letzter = onChange.mock.calls[onChange.mock.calls.length - 1][0] as string
    expect(letzter).toContain('{{ empfaenger.name }}')
    expect(letzter).not.toContain('{{ empf ')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('meldet beim bloßen Öffnen keine Änderung (sonst wäre jede Version sofort „ungespeichert“)', async () => {
    const { onChange } = rendere('<p>Unverändert {{ empfaenger.name }}</p>')
    await screen.findByLabelText('Testblock')
    await act(async () => { await new Promise(r => setTimeout(r, 100)) })
    expect(onChange).not.toHaveBeenCalled()
  })

  it('bietet im Lesemodus weder Toolbar noch Bearbeitung', async () => {
    const { container } = rendere('<p>Nur lesen</p>', { readOnly: true })
    await screen.findByText('Nur lesen')
    expect(screen.queryByRole('toolbar')).not.toBeInTheDocument()
    expect(container.querySelector('[contenteditable="true"]')).toBeNull()
  })
})
