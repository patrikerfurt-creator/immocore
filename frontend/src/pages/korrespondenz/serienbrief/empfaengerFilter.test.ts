import { describe, it, expect } from 'vitest'
import { LEERE_AUSWAHL, filterAufbauen, filterBeschreibung } from './empfaengerFilter'

describe('filterAufbauen', () => {
  it('liefert bei leerer Auswahl einen leeren Filter (= alle aktiven Eigentümer)', () => {
    expect(filterAufbauen(LEERE_AUSWAHL)).toEqual({})
  })

  it('übernimmt Einheitstyp, E-Mail-Zustimmung und trennt Ab- von Zuwahl (sortiert)', () => {
    expect(filterAufbauen({
      einheit_typ: ['Wohnung', 'Gewerbe'],
      email_zustimmung: 'mit',
      ausnahmen: { b: 'aus', a: 'aus', c: 'zu' },
    })).toEqual({
      einheit_typ: ['Wohnung', 'Gewerbe'],
      email_zustimmung: 'mit',
      ausschliessen: ['a', 'b'],
      hinzufuegen: ['c'],
    })
  })
})

describe('filterBeschreibung', () => {
  it('fasst den Empfängerkreis lesbar zusammen', () => {
    expect(filterBeschreibung({
      einheit_typ: ['Wohnung'], email_zustimmung: 'ohne', ausnahmen: { a: 'aus', b: 'zu', c: 'zu' },
    })).toBe('Alle aktiven Eigentümer · Einheitstyp: Wohnung · nur ohne E-Mail-Zustimmung · 1 abgewählt · 2 zusätzlich')
  })
})
