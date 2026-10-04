import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BriefbogenVerwaltung } from './BriefbogenVerwaltung'
import { briefboegenApi } from '../../api/korrespondenz'
import type { Briefbogen } from '../../types'

vi.mock('../../api/korrespondenz', async () => {
  const echt = await vi.importActual<typeof import('../../api/korrespondenz')>('../../api/korrespondenz')
  return { ...echt, briefboegenApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() } }
})

const liste = vi.mocked(briefboegenApi.list)
const update = vi.mocked(briefboegenApi.update)

const BB1: Briefbogen = {
  id: 'b1', bezeichnung: 'Demme Standard', firma_name: 'Demme Immobilien GmbH',
  firma_strasse: 'Musterweg 1', firma_plz: '12345', firma_ort: 'Musterstadt',
  telefon: '0123 456', email: 'info@example.de', web: 'www.example.de',
  sprechzeiten: 'Mo\t9-12', hinweis_infoblock: '', logo: 'dok1', fuss_logo: null,
  fuss_firma_zeile1: 'HRB 111, AG Musterstadt', fuss_firma_zeile2: 'GF: A', fuss_firma_zeile3: '',
  pflichtangaben: 'HRB 111, AG Musterstadt', pflichtangaben_anzeigen: true,
  steuerzeichen_unsichtbar: '', ist_standard: true, aktiv: true,
}
const BB2: Briefbogen = { ...BB1, id: 'b2', bezeichnung: 'Zweitbogen', ist_standard: false }

function rendere() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter><BriefbogenVerwaltung /></MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => { vi.clearAllMocks() })

describe('BriefbogenVerwaltung', () => {
  it('lädt die Briefbögen und zeigt den ersten schreibgeschützt', async () => {
    liste.mockResolvedValue([BB1, BB2])
    rendere()
    expect(await screen.findByText('Briefbogen: Demme Standard')).toBeInTheDocument()
    expect(screen.getByLabelText('Firmenname *')).toHaveValue('Demme Immobilien GmbH')
    expect(screen.getByLabelText('Firmenname *')).toBeDisabled()
    expect(screen.getByText('Zweitbogen')).toBeInTheDocument()
    expect(screen.getByTestId('briefbogen-logo-info')).toHaveTextContent('Dokument dok1')
  })

  it('beschriftet die beiden Registerfelder und weist auf die Doppelpflege hin', async () => {
    liste.mockResolvedValue([BB1])
    rendere()
    expect(await screen.findByLabelText('Firmen-Fußzeile Zeile 1 (enthält HRB/Amtsgericht)')).toHaveValue('HRB 111, AG Musterstadt')
    expect(screen.getByLabelText('Pflichtangaben (enthält HRB/Amtsgericht)')).toHaveValue('HRB 111, AG Musterstadt')
    expect(screen.getByRole('note')).toHaveTextContent(/konsistent/)
  })

  it('bearbeitet und speichert per PATCH', async () => {
    liste.mockResolvedValue([BB1])
    update.mockResolvedValue({ ...BB1, firma_name: 'Neu GmbH', fuss_firma_zeile1: 'HRB 222' })
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
    const name = screen.getByLabelText('Firmenname *')
    await userEvent.clear(name)
    await userEvent.type(name, 'Neu GmbH')
    const zeile1 = screen.getByLabelText('Firmen-Fußzeile Zeile 1 (enthält HRB/Amtsgericht)')
    await userEvent.clear(zeile1)
    await userEvent.type(zeile1, 'HRB 222')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1))
    const [id, payload] = update.mock.calls[0]
    expect(id).toBe('b1')
    expect(payload).toMatchObject({ firma_name: 'Neu GmbH', fuss_firma_zeile1: 'HRB 222', pflichtangaben: 'HRB 111, AG Musterstadt' })
    expect(payload).not.toHaveProperty('logo')
    expect(await screen.findByText('Briefbogen gespeichert.')).toBeInTheDocument()
  })

  it('validiert die Pflichtfelder vor dem Speichern', async () => {
    liste.mockResolvedValue([BB1])
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
    await userEvent.clear(screen.getByLabelText('Firmenname *'))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText('Firmenname ist Pflicht.')).toBeInTheDocument()
    expect(update).not.toHaveBeenCalled()
  })

  it('zeigt Serverfehler beim Speichern an', async () => {
    liste.mockResolvedValue([BB1])
    update.mockRejectedValue({ isAxiosError: true, response: { status: 400, data: { email: ['Ungültig.'] } } })
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText('Ungültig.')).toBeInTheDocument()
  })

  it('warnt, wenn ein zweiter Briefbogen Standard würde', async () => {
    liste.mockResolvedValue([BB1, BB2])
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: 'Briefbogen Zweitbogen auswählen' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
    await userEvent.click(screen.getByLabelText('Standard-Briefbogen'))
    expect(screen.getByText(/Bereits Standard ist: Demme Standard/)).toBeInTheDocument()
  })

  it('zeigt bei 403 einen klaren Hinweis statt der Liste', async () => {
    liste.mockRejectedValue(Object.assign(new Error('403'), { isAxiosError: true, response: { status: 403, data: {} } }))
    rendere()
    expect(await screen.findByText(/nur für Administratoren/)).toBeInTheDocument()
    expect(screen.queryByTestId('briefbogen-karte')).not.toBeInTheDocument()
  })

  it('zeigt bei 403 beim Speichern den Admin-Hinweis', async () => {
    liste.mockResolvedValue([BB1])
    update.mockRejectedValue(Object.assign(new Error('403'), { isAxiosError: true, response: { status: 403, data: { detail: 'x' } } }))
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText(/nur Administratoren ändern/)).toBeInTheDocument()
  })
})
