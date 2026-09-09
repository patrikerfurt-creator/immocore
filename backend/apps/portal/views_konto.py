"""
Personenkonto-Saldo und Fälligkeiten im Portal (Spec Portal-Erweiterung
v1.1, Kap. 6 und 7).

Beide Endpunkte rechnen NICHT selbst: der Saldo kommt aus
``saldi_je_personenkonto`` (apps.konten.services.personenkonto_service) —
derselben Funktion, die auch die interne Debitorenansicht (``mit-saldo``)
speist. Eine zweite Saldo-Berechnung würde früher oder später von der
internen Anzeige abweichen — und ein Eigentümer, der zwei verschiedene
Zahlen sieht, ruft an.

Begründete Abweichung von Spec Kap. 6.1 (Aufschlüsselung je Unterkonto):
Ein Saldo je Unterkonto existiert im Datenmodell nicht — die Soll-Seite
hängt am Eigentumsverhältnis (`HausgeldSollstellung`), die Haben-Seite am
Personenkonto (`Buchung.personenkonto`); eine Zuordnung
Buchungsart→Unterkonto ist nirgends definiert. Eine erfundene Verteilung
wäre genau die zweite Saldo-Berechnung, die Kap. 6.2 verbietet. Deshalb wird
stattdessen nach `sollstellungs_typ` aufgeschlüsselt — denselben Zahlen, die
auch in den Gesamtsaldo eingehen (`soll_je_typ` aus dem Service).

Kernregel (siehe auch `apps.portal.auth`): die Person kommt ausschließlich
aus der Portal-Sitzung, niemals aus einer vom Client mitgeschickten ID.
"""
from django.utils import timezone
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.buchhaltung.models import HausgeldSollstellung
from apps.konten.models import Personenkonto
from apps.konten.services.personenkonto_service import saldi_je_personenkonto

from .auth import IstPortalNutzer, PortalSessionAuthentication
from .serializers_konto import TYP_LABEL, FaelligkeitSerializer, SaldoSerializer


class PortalSaldoView(APIView):
    """``GET /api/v1/portal/personenkonto/saldo/``

    Reine Liste (keine Pagination) — ein Eintrag je Personenkonto der
    Portal-Person, auch für beendete Eigentumsverhältnisse: ein Verkauf
    lässt offene Posten nicht verschwinden.
    """
    authentication_classes = [PortalSessionAuthentication]
    permission_classes = [IstPortalNutzer]

    def get(self, request, *args, **kwargs):
        personenkonten = (
            Personenkonto.objects
            .filter(vertrag__person=request.portal_zugang.person)
            .select_related('objekt', 'vertrag__einheit')
            .order_by('objekt__bezeichnung', 'kontonummer')
        )
        salden = saldi_je_personenkonto(personenkonten)

        ergebnisse = []
        for pk in personenkonten:
            werte = salden[pk.id]

            aufschluesselung = [
                {'bezeichnung': TYP_LABEL.get(typ, typ), 'betrag': -betrag}
                for typ, betrag in werte['soll_je_typ'].items()
                if betrag
            ]
            if werte['haben']:
                aufschluesselung.append({
                    'bezeichnung': 'Ihre Zahlungen',
                    'betrag': werte['haben'],
                })

            ergebnisse.append({
                'objekt_id': pk.objekt_id,
                'objekt_bezeichnung': pk.objekt.bezeichnung,
                'einheit_id': pk.vertrag.einheit_id,
                'einheit_nr': pk.vertrag.einheit.einheit_nr,
                'kontonummer': pk.kontonummer,
                'gesamtsaldo': werte['saldo'],
                'stand_am': timezone.now(),
                'aufschluesselung': aufschluesselung,
            })

        serializer = SaldoSerializer(ergebnisse, many=True)
        return Response(serializer.data)


class _FaelligkeitenPagination(PageNumberPagination):
    """Eigene Pagination nur für diese View (Spec Kap. 7.3, Edge-Case „viele
    offene Posten") — die globale Pagination-Einstellung bleibt unangetastet."""
    page_size = 50
    page_size_query_param = 'page_size'


class PortalFaelligkeitenView(generics.ListAPIView):
    """``GET /api/v1/portal/faelligkeiten/``

    Paginiert (anders als der Saldo-Endpunkt): die Zahl offener Posten ist
    über die Lebenszeit eines Eigentumsverhältnisses nicht begrenzt.
    """
    authentication_classes = [PortalSessionAuthentication]
    permission_classes = [IstPortalNutzer]
    serializer_class = FaelligkeitSerializer
    pagination_class = _FaelligkeitenPagination

    def get_queryset(self):
        return (
            HausgeldSollstellung.objects
            .filter(
                eigentumsverhaeltnis__person=self.request.portal_zugang.person,
                status_cached__in=['offen', 'teilbezahlt'],
                storniert_am__isnull=True,
            )
            .select_related('objekt', 'eigentumsverhaeltnis__einheit')
            .order_by('faellig_am')
        )
