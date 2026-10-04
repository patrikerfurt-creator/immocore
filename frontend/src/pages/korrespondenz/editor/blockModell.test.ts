import { describe, it, expect } from 'vitest'
import {
  blockZusammenfassung, editorHtmlZuJinja, eingabefelderAlsPlatzhalter, jinjaZuEditorHtml,
  neuerBlock, normalisiereBlock, normalisiereBloecke, platzhalterInText, platzhalterName,
  textQuellen, unbekanntePlatzhalter, zuBloecken, zuEintraegen,
} from './blockModell'

describe('jinjaZuEditorHtml', () => {
  it('macht aus Text ohne Tags Absätze (Leerzeile = neuer Absatz, Zeilenumbruch = br)', () => {
    expect(jinjaZuEditorHtml('Erster Absatz\nzweite Zeile\n\nZweiter Absatz'))
      .toBe('<p>Erster Absatz<br>zweite Zeile</p><p>Zweiter Absatz</p>')
  })

  it('lässt vorhandenes HTML unverändert', () => {
    expect(jinjaZuEditorHtml('<p>Hallo</p><ul><li>a</li></ul>')).toBe('<p>Hallo</p><ul><li>a</li></ul>')
  })

  it('escaped Sonderzeichen in Text ohne Tags', () => {
    expect(jinjaZuEditorHtml('a < b & c')).toBe('<p>a &lt; b &amp; c</p>')
  })

  it('wandelt Platzhalter samt Filter in Chips', () => {
    const html = jinjaZuEditorHtml('<p>Ab {{ hausgeld.gueltig_ab | datum }} gilt es</p>')
    expect(html).toContain('<span data-platzhalter="hausgeld.gueltig_ab | datum">{{ hausgeld.gueltig_ab | datum }}</span>')
  })

  it('kommt mit leerem/fehlendem Inhalt klar', () => {
    expect(jinjaZuEditorHtml('')).toBe('')
    expect(jinjaZuEditorHtml(undefined)).toBe('')
  })
})

describe('editorHtmlZuJinja', () => {
  it('macht Chips wieder zu {{ ausdruck }}', () => {
    const html = '<p>Sehr geehrte <span data-platzhalter="empfaenger.briefanrede" class="x">{{ empfaenger.briefanrede }}</span>,</p>'
    expect(editorHtmlZuJinja(html)).toBe('<p>Sehr geehrte {{ empfaenger.briefanrede }},</p>')
  })

  it('dekodiert Attribut-Entities (Anführungszeichen im Ausdruck)', () => {
    const html = '<p><span data-platzhalter="x | default(&quot;-&quot;)">{{ x }}</span></p>'
    expect(editorHtmlZuJinja(html)).toBe('<p>{{ x | default("-") }}</p>')
  })

  it('liefert für einen leeren Editor einen leeren String', () => {
    expect(editorHtmlZuJinja('<p></p>')).toBe('')
    expect(editorHtmlZuJinja('<p><br></p>')).toBe('')
  })

  it('ist zu jinjaZuEditorHtml invers (Hin- und Rückweg)', () => {
    const quelle = '<p>Betrag {{ mahnung.gesamtbetrag | euro }} bis {{ mahnung.frist | datum }}</p>'
    expect(editorHtmlZuJinja(jinjaZuEditorHtml(quelle))).toBe(quelle)
  })
})

describe('Platzhalter-Prüfung', () => {
  it('extrahiert den Namen vor dem Filter', () => {
    expect(platzhalterName('hausgeld.betrag | euro')).toBe('hausgeld.betrag')
    expect(platzhalterInText('{{ a.b }} und {{ c.d | datum }}')).toEqual(['a.b', 'c.d'])
  })

  it('findet unbekannte Platzhalter und berücksichtigt Eingabefelder', () => {
    const felder = [{ name: 'ort', label: 'Ort', typ: 'text' as const, pflicht: true }]
    const unbekannt = unbekanntePlatzhalter(
      ['{{ empfaenger.name }} {{ eingabe.ort }} {{ erfunden.feld }}'],
      ['empfaenger.name'], felder,
    )
    expect(unbekannt).toEqual(['erfunden.feld'])
  })

  it('sammelt Betreff, Blocktexte und Bedingungen als Quellen', () => {
    const q = textQuellen('Betreff {{ a.b }}', [
      { typ: 'text', inhalt: 'x' },
      { typ: 'bedingt', bedingung: 'ev.sepa_mandat_fehlt', inhalt: 'y' },
      { typ: 'seitenumbruch' },
    ])
    expect(q).toEqual(['Betreff {{ a.b }}', 'x', 'y', '{{ ev.sepa_mandat_fehlt }}'])
  })

  it('macht aus Eingabefeldern Platzhalter der Gruppe eingabe; ungültige Namen entfallen', () => {
    const p = eingabefelderAlsPlatzhalter([
      { name: 'tagesordnung', label: 'TOPs', typ: 'liste', pflicht: true },
      { name: 'mit_sepa', label: 'SEPA', typ: 'ja_nein', pflicht: false },
      { name: 'Ungültig!', label: '', typ: 'text', pflicht: false },
    ])
    expect(p.map(x => [x.name, x.typ, x.gruppe])).toEqual([
      ['eingabe.tagesordnung', 'liste', 'eingabe'],
      ['eingabe.mit_sepa', 'bool', 'eingabe'],
    ])
  })
})

describe('Blockmodell', () => {
  it('legt Blöcke mit den Feldern des Blockstruktur-Contracts an', () => {
    expect(neuerBlock('text')).toEqual({ typ: 'text', inhalt: '' })
    expect(neuerBlock('tabelle')).toEqual({ typ: 'tabelle', quelle: '' })
    expect(neuerBlock('liste')).toEqual({ typ: 'liste', quelle: '' })
    expect(neuerBlock('bedingt')).toEqual({ typ: 'bedingt', bedingung: '', inhalt: '' })
    expect(neuerBlock('anlage_seite')).toEqual({ typ: 'anlage_seite', titel: '', inhalt: '' })
    expect(neuerBlock('seitenumbruch')).toEqual({ typ: 'seitenumbruch' })
    expect(neuerBlock('baustein')).toEqual({ typ: 'baustein', code: '' })
  })

  it('vergibt lokale Schlüssel, die beim Speichern nicht mitgehen', () => {
    const eintraege = zuEintraegen([{ typ: 'text', inhalt: 'a' }, { typ: 'seitenumbruch' }])
    expect(new Set(eintraege.map(e => e.key)).size).toBe(2)
    expect(zuBloecken(eintraege)).toEqual([{ typ: 'text', inhalt: 'a' }, { typ: 'seitenumbruch' }])
  })

  it('normalisiert KI-Blöcke, verwirft ungültige und behält spalten der Tabelle', () => {
    expect(normalisiereBlock({ typ: 'gibts_nicht' })).toBeNull()
    expect(normalisiereBlock('text')).toBeNull()
    expect(normalisiereBlock({ typ: 'bedingt', bedingung: 'x', inhalt: 5 }))
      .toEqual({ typ: 'bedingt', bedingung: 'x', inhalt: '' })
    expect(normalisiereBlock({ typ: 'tabelle', quelle: 'a.b', spalten: [{ feld: 'f', titel: 'F' }] }))
      .toEqual({ typ: 'tabelle', quelle: 'a.b', spalten: [{ feld: 'f', titel: 'F' }] })
    expect(normalisiereBloecke([{ typ: 'text', inhalt: 'ok' }, null, { typ: 'x' }]))
      .toEqual([{ typ: 'text', inhalt: 'ok' }])
    expect(normalisiereBloecke('kein array')).toEqual([])
  })

  it('fasst Blöcke als Klartext zusammen', () => {
    expect(blockZusammenfassung({ typ: 'text', inhalt: '<p>Hallo <b>Welt</b></p>' })).toBe('Hallo Welt')
    expect(blockZusammenfassung({ typ: 'tabelle', quelle: 'a.b' })).toBe('Tabelle: a.b')
  })
})
