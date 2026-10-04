import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MahnEinstellungSection } from './MahnEinstellungSection'
import { objekteApi } from '../../api/objekte'

vi.mock('../../api/objekte', () => ({
  objekteApi: {
    getMahnEinstellung: vi.fn(),
    putMahnEinstellung: vi.fn(),
  },
}))

const mockGet = vi.mocked(objekteApi.getMahnEinstellung)
const mockPut = vi.mocked(objekteApi.putMahnEinstellung)

const notFound = () => Object.assign(new Error('404'), { response: { status: 404, data: {} } })

beforeEach(() => {
  vi.clearAllMocks()
})

describe('MahnEinstellungSection', () => {
  it('zeigt bestehende Einstellung an', async () => {
    mockGet.mockResolvedValue({ mahngebuehr: '5.00', anzahl_mahnstufen: 2, zinsen_erheben: true })
    render(<MahnEinstellungSection objektId="o1" />)

    expect(await screen.findByText(/5,00/)).toBeInTheDocument()
    expect(screen.getByText('Ja')).toBeInTheDocument()
    expect(screen.queryByText(/Noch nicht konfiguriert/)).not.toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledWith('o1')
  })

  it('zeigt bei 404 "noch nicht konfiguriert" mit Sperr-Hinweis', async () => {
    mockGet.mockRejectedValue(notFound())
    render(<MahnEinstellungSection objektId="o1" />)

    expect(await screen.findByText(/Noch nicht konfiguriert/)).toBeInTheDocument()
    expect(screen.getByText(/Mahnlauf für dieses Objekt gesperrt/)).toBeInTheDocument()
  })

  it('zeigt bei anderem Ladefehler eine Fehlermeldung statt "nicht konfiguriert"', async () => {
    mockGet.mockRejectedValue(Object.assign(new Error('500'), { response: { status: 500 } }))
    render(<MahnEinstellungSection objektId="o1" />)

    expect(await screen.findByText(/konnte nicht geladen werden/)).toBeInTheDocument()
    expect(screen.queryByText(/Noch nicht konfiguriert/)).not.toBeInTheDocument()
  })

  it('speichert neue Einstellung via PUT (Komma wird zu Punkt)', async () => {
    mockGet.mockRejectedValue(notFound())
    mockPut.mockResolvedValue({ mahngebuehr: '7.50', anzahl_mahnstufen: 1, zinsen_erheben: true })
    const user = userEvent.setup()
    render(<MahnEinstellungSection objektId="o1" />)

    await user.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
    await user.type(screen.getByLabelText(/Mahngebühr/), '7,50')
    await user.selectOptions(screen.getByLabelText('Anzahl Mahnstufen'), '1')
    await user.selectOptions(screen.getByLabelText('Zinsen erheben'), 'ja')
    await user.click(screen.getByRole('button', { name: 'Speichern' }))

    await waitFor(() =>
      expect(mockPut).toHaveBeenCalledWith('o1', {
        mahngebuehr: '7.50',
        anzahl_mahnstufen: 1,
        zinsen_erheben: true,
      }),
    )
    expect(await screen.findByText(/7,50/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Speichern' })).not.toBeInTheDocument()
  })

  it('lehnt leere Mahngebühr ab und ruft PUT nicht auf', async () => {
    mockGet.mockRejectedValue(notFound())
    const user = userEvent.setup()
    render(<MahnEinstellungSection objektId="o1" />)

    await user.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
    await user.click(screen.getByRole('button', { name: 'Speichern' }))

    expect(await screen.findByText('Mahngebühr ist Pflicht.')).toBeInTheDocument()
    expect(mockPut).not.toHaveBeenCalled()
  })

  it('lehnt negative Mahngebühr ab', async () => {
    mockGet.mockRejectedValue(notFound())
    const user = userEvent.setup()
    render(<MahnEinstellungSection objektId="o1" />)

    await user.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
    await user.type(screen.getByLabelText(/Mahngebühr/), '-3')
    await user.click(screen.getByRole('button', { name: 'Speichern' }))

    expect(await screen.findByText(/Betrag >= 0/)).toBeInTheDocument()
    expect(mockPut).not.toHaveBeenCalled()
  })

  it('zeigt Serverfehler beim Speichern an', async () => {
    mockGet.mockResolvedValue({ mahngebuehr: '5.00', anzahl_mahnstufen: 2, zinsen_erheben: false })
    mockPut.mockRejectedValue({ response: { status: 400, data: { mahngebuehr: ['Ungültiger Betrag.'] } } })
    const user = userEvent.setup()
    render(<MahnEinstellungSection objektId="o1" />)

    await user.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
    await user.click(screen.getByRole('button', { name: 'Speichern' }))

    expect(await screen.findByText('Ungültiger Betrag.')).toBeInTheDocument()
  })
})
