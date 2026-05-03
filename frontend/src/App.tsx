import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout } from './components/Layout'
import { ProtectedRoute } from './components/ProtectedRoute'
import { Login } from './pages/Login'
import { Dashboard } from './pages/Dashboard'
import { ObjekteListe } from './pages/objekte/ObjekteListe'
import { ObjektDetail } from './pages/objekte/ObjektDetail'
import { PersonenListe } from './pages/personen/PersonenListe'
import { PersonNeu } from './pages/personen/PersonNeu'
import { PersonDetail } from './pages/personen/PersonDetail'
import { PersonenImport } from './pages/personen/PersonenImport'
import { EinheitenPage } from './pages/einheiten/EinheitenPage'
import { VertragsmanagementPage } from './pages/vertragsmanagement/VertragsmanagementPage'
import { Buchungsjournal } from './pages/buchhaltung/Buchungsjournal'
import { BankImport } from './pages/buchhaltung/BankImport'
import { Sollstellungen } from './pages/buchhaltung/Sollstellungen'
import { EBanking } from './pages/buchhaltung/EBanking'
import { Debitoren } from './pages/buchhaltung/Debitoren'
import { Kontoauszug } from './pages/buchhaltung/Kontoauszug'
import { Dialogbuchhaltung } from './pages/buchhaltung/Dialogbuchhaltung'
import { RechnungenListe } from './pages/rechnungen/RechnungenListe'
import { KreditorenListe } from './pages/rechnungen/KreditorenListe'
import PrueffallDetail from './pages/rechnungen/PrueffallDetail'
import MatchRegeln from './pages/rechnungen/MatchRegeln'
import FrontofficeInbox from './pages/rechnungen/FrontofficeInbox'
import { ProzessWizard } from './pages/prozesse/ProzessWizard'
import { DokumenteListe } from './pages/dokumente/DokumenteListe'
import { TicketsListe } from './pages/tickets/TicketsListe'
import { AbrechnungsartenPage } from './pages/stammdaten/AbrechnungsartenPage'
import { VerteilerschluesselPage } from './pages/stammdaten/VerteilerschluesselPage'
import { KontenplanPage } from './pages/stammdaten/KontenplanPage'
import { Einstellungen } from './pages/Einstellungen'
import { MassenimportWEG } from './pages/massenimport/MassenimportWEG'
import { Lastschrift } from './pages/zahlungsverkehr/Lastschrift'
import { Zahlungen } from './pages/zahlungsverkehr/Zahlungen'
import { MitarbeiterPage } from './pages/mitarbeiter/MitarbeiterPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="objekte" element={<ObjekteListe />} />
            <Route path="objekte/:id" element={<ObjektDetail />} />
            <Route path="personen" element={<PersonenListe />} />
            <Route path="personen/neu" element={<PersonNeu />} />
            <Route path="personen/import" element={<PersonenImport />} />
            <Route path="personen/:id" element={<PersonDetail />} />
            <Route path="einheiten" element={<EinheitenPage />} />
            <Route path="vertragsmanagement" element={<VertragsmanagementPage />} />
            <Route path="stammdaten/abrechnungsarten" element={<AbrechnungsartenPage />} />
            <Route path="stammdaten/verteilerschluessel" element={<VerteilerschluesselPage />} />
            <Route path="stammdaten/kontenplan" element={<KontenplanPage />} />
            <Route path="buchhaltung" element={<Buchungsjournal />} />
            <Route path="buchhaltung/bankimport" element={<BankImport />} />
            <Route path="buchhaltung/debitoren" element={<Debitoren />} />
            <Route path="buchhaltung/kontoauszug" element={<Kontoauszug />} />
            <Route path="buchhaltung/sollstellungen" element={<Sollstellungen />} />
            <Route path="buchhaltung/ebanking" element={<EBanking />} />
            <Route path="buchhaltung/dialog" element={<Dialogbuchhaltung />} />
            <Route path="rechnungen" element={<RechnungenListe />} />
            <Route path="rechnungen/:id/prueffall" element={<PrueffallDetail />} />
            <Route path="rechnungen/frontoffice" element={<FrontofficeInbox />} />
            <Route path="kreditoren" element={<KreditorenListe />} />
            <Route path="admin/rechnungen/match-regeln" element={<MatchRegeln />} />
            <Route path="prozesse" element={<ProzessWizard />} />
            <Route path="dokumente" element={<DokumenteListe />} />
            <Route path="tickets" element={<TicketsListe />} />
            <Route path="massenimport/weg" element={<MassenimportWEG />} />
            <Route path="zahlungsverkehr/lastschrift" element={<Lastschrift />} />
            <Route path="zahlungsverkehr/zahlungen" element={<Zahlungen />} />
            <Route path="mitarbeiter" element={<MitarbeiterPage />} />
            <Route path="einstellungen" element={<Einstellungen />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
