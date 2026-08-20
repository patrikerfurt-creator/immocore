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
import { AutoPipeline } from './pages/buchhaltung/AutoPipeline'
import { AutoPipelineProtokollDetail } from './pages/buchhaltung/AutoPipelineProtokollDetail'
import { EBanking } from './pages/buchhaltung/EBanking'
import { BankMatchRulesPage } from './pages/buchhaltung/BankMatchRulesPage'
import { Debitoren } from './pages/buchhaltung/Debitoren'
import { Kontoauszug } from './pages/buchhaltung/Kontoauszug'
import { Dialogbuchhaltung } from './pages/buchhaltung/Dialogbuchhaltung'
import { RechnungenListe } from './pages/rechnungen/RechnungenListe'
import { KreditorenListe } from './pages/rechnungen/KreditorenListe'
import PrueffallDetail from './pages/rechnungen/PrueffallDetail'
import MatchRegeln from './pages/rechnungen/MatchRegeln'
import FrontofficeInbox from './pages/rechnungen/FrontofficeInbox'
import BuchhaltungsInbox from './pages/rechnungen/BuchhaltungsInbox'
import RechnungErfassen from './pages/rechnungen/RechnungErfassen'
import RechnungsFreigabe from './pages/rechnungen/RechnungsFreigabe'
import { ProzessWizard } from './pages/prozesse/ProzessWizard'
import { DokumenteListe } from './pages/dokumente/DokumenteListe'
import { VorgaengeListe } from './pages/vorgaenge/VorgaengeListe'
import { VorgangDetail } from './pages/vorgaenge/VorgangDetail'
import { VorgangTypenAdmin } from './pages/vorgaenge/VorgangTypenAdmin'
import { AbrechnungsartenPage } from './pages/stammdaten/AbrechnungsartenPage'
import { VerteilerschluesselPage } from './pages/stammdaten/VerteilerschluesselPage'
import { KontenplanPage } from './pages/stammdaten/KontenplanPage'
import { Einstellungen } from './pages/Einstellungen'
import { MassenimportWEG } from './pages/massenimport/MassenimportWEG'
import { Lastschrift } from './pages/zahlungsverkehr/Lastschrift'
import { Zahlungen } from './pages/zahlungsverkehr/Zahlungen'
import { MitarbeiterPage } from './pages/mitarbeiter/MitarbeiterPage'
import VorlagenListe from './pages/buchhaltung/wkz/VorlagenListe'
import VorlageDetail from './pages/buchhaltung/wkz/VorlageDetail'
import VorlageWizard from './pages/buchhaltung/wkz/VorlageWizard'
import OPDetail from './pages/buchhaltung/wkz/OPDetail'
import Forecast from './pages/buchhaltung/wkz/Forecast'
import { WirtschaftsplanListe } from './pages/abrechnung-wp/wirtschaftsplan/WirtschaftsplanListe'
import { WirtschaftsplanDetail } from './pages/abrechnung-wp/wirtschaftsplan/WirtschaftsplanDetail'
import { WirtschaftsplanWizard } from './pages/abrechnung-wp/wirtschaftsplan/WirtschaftsplanWizard'
import { JahresabrechnungListe } from './pages/abrechnung-wp/jahresabrechnung/JahresabrechnungListe'
import { JahresabrechnungWizard } from './pages/abrechnung-wp/jahresabrechnung/JahresabrechnungWizard'
import { HandwerkerauftraegeListe } from './pages/handwerker/HandwerkerauftraegeListe'
import { HandwerkerauftragDetail } from './pages/handwerker/HandwerkerauftragDetail'
import { GewerkeAdmin } from './pages/handwerker/GewerkeAdmin'
import { VersammlungenListe } from './pages/versammlungen/VersammlungenListe'
import { VersammlungDetail } from './pages/versammlungen/VersammlungDetail'
import { BeschlussSammlung } from './pages/versammlungen/BeschlussSammlung'
import { AuftragBestaetigung } from './pages/oeffentlich/AuftragBestaetigung'

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
          {/* Öffentlich, ohne Login — Handwerker bestätigen ihren Auftrag per Mail-Link. */}
          <Route path="/auftrag-bestaetigung/:token" element={<AuftragBestaetigung />} />
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
            <Route path="buchhaltung/auto-pipeline" element={<AutoPipeline />} />
            <Route path="buchhaltung/auto-pipeline/protokoll/:id" element={<AutoPipelineProtokollDetail />} />
            <Route path="buchhaltung/ebanking" element={<EBanking />} />
            <Route path="buchhaltung/ebanking/regeln" element={<BankMatchRulesPage />} />
            <Route path="buchhaltung/dialog" element={<Dialogbuchhaltung />} />
            <Route path="rechnungen" element={<RechnungenListe />} />
            <Route path="rechnungen/inbox" element={<BuchhaltungsInbox />} />
            <Route path="rechnungen/freigabe" element={<RechnungsFreigabe />} />
            <Route path="rechnungen/erfassen" element={<RechnungErfassen />} />
            <Route path="rechnungen/erfassen/:id" element={<RechnungErfassen />} />
            <Route path="rechnungen/:id/prueffall" element={<PrueffallDetail />} />
            <Route path="rechnungen/frontoffice" element={<FrontofficeInbox />} />
            <Route path="kreditoren" element={<KreditorenListe />} />
            <Route path="admin/rechnungen/match-regeln" element={<MatchRegeln />} />
            <Route path="prozesse" element={<ProzessWizard />} />
            <Route path="dokumente" element={<DokumenteListe />} />
            <Route path="vorgaenge" element={<VorgaengeListe />} />
            <Route path="vorgaenge/:id" element={<VorgangDetail />} />
            <Route path="admin/vorgang-typen" element={<VorgangTypenAdmin />} />
            <Route path="handwerker/auftraege" element={<HandwerkerauftraegeListe />} />
            <Route path="handwerker/auftraege/:id" element={<HandwerkerauftragDetail />} />
            <Route path="versammlungen" element={<VersammlungenListe />} />
            <Route path="versammlungen/beschluesse" element={<BeschlussSammlung />} />
            <Route path="versammlungen/:id" element={<VersammlungDetail />} />
            <Route path="admin/gewerke" element={<GewerkeAdmin />} />
            <Route path="massenimport/weg" element={<MassenimportWEG />} />
            <Route path="zahlungsverkehr/lastschrift" element={<Lastschrift />} />
            <Route path="zahlungsverkehr/zahlungen" element={<Zahlungen />} />
            <Route path="buchhaltung/wkz-vorlagen" element={<VorlagenListe />} />
            <Route path="buchhaltung/wkz-vorlagen/neu" element={<VorlageWizard />} />
            <Route path="buchhaltung/wkz-vorlagen/:id" element={<VorlageDetail />} />
            <Route path="buchhaltung/wkz-ops/:id" element={<OPDetail />} />
            <Route path="buchhaltung/wkz-forecast" element={<Forecast />} />
            <Route path="mitarbeiter" element={<MitarbeiterPage />} />
            <Route path="einstellungen" element={<Einstellungen />} />
            <Route path="abrechnung-wp/wirtschaftsplan" element={<WirtschaftsplanListe />} />
            <Route path="abrechnung-wp/wirtschaftsplan/wizard" element={<WirtschaftsplanWizard />} />
            <Route path="abrechnung-wp/wirtschaftsplan/:id" element={<WirtschaftsplanDetail />} />
            <Route path="abrechnung-wp/jahresabrechnung" element={<JahresabrechnungListe />} />
            <Route path="abrechnung-wp/jahresabrechnung/wizard" element={<JahresabrechnungWizard />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
