from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AbmeldenView,
    BankverbindungView,
    EmailAendernView,
    EmailBestaetigenView,
    IbanPruefenView,
    MagicLinkAnfordernView,
    MagicLinkEinloesenView,
    MeineDatenView,
    MeineEinheitenView,
)
from .views_konto import PortalFaelligkeitenView, PortalSaldoView
from .views_verwaltung import PortalZugangViewSet
from .views_vorgaenge import (
    PortalVorgaengeView,
    PortalVorgangDetailView,
    PortalVorgangTypenView,
)

router = DefaultRouter()
# Interner Bereich — klar getrennt von den Portal-Routen unterhalb von
# 'portal/', damit an der URL ablesbar ist, welche Authentifizierung gilt.
router.register(
    r'portal-verwaltung/zugaenge', PortalZugangViewSet, basename='portal-zugaenge',
)

urlpatterns = router.urls + [
    path('portal/auth/magic-link/request/', MagicLinkAnfordernView.as_view(),
         name='portal-magic-link-request'),
    path('portal/auth/magic-link/verify/', MagicLinkEinloesenView.as_view(),
         name='portal-magic-link-verify'),
    path('portal/auth/logout/', AbmeldenView.as_view(), name='portal-logout'),

    path('portal/meine-einheiten/', MeineEinheitenView.as_view(),
         name='portal-meine-einheiten'),
    path('portal/meine-daten/', MeineDatenView.as_view(), name='portal-meine-daten'),
    # Reihenfolge unkritisch (keine überlappenden Präfixe), aber die
    # spezielleren Routen stehen bewusst nach der Basisroute.
    path('portal/meine-daten/email/', EmailAendernView.as_view(),
         name='portal-email-aendern'),
    path('portal/meine-daten/email/bestaetigen/', EmailBestaetigenView.as_view(),
         name='portal-email-bestaetigen'),
    path('portal/meine-daten/bankverbindung/', BankverbindungView.as_view(),
         name='portal-bankverbindung'),
    path('portal/iban-check/', IbanPruefenView.as_view(), name='portal-iban-check'),

    # Vorgänge (Spec Portal-Erweiterung v1.1, Kap. 4/5). 'vorgang-typen'
    # steht vor der Detailroute — keine überlappenden Präfixe, aber die
    # Lesbarkeit folgt der Reihenfolge im Formular.
    path('portal/vorgang-typen/', PortalVorgangTypenView.as_view(),
         name='portal-vorgang-typen'),
    path('portal/vorgaenge/', PortalVorgaengeView.as_view(), name='portal-vorgaenge'),
    path('portal/vorgaenge/<uuid:vorgang_id>/', PortalVorgangDetailView.as_view(),
         name='portal-vorgang-detail'),

    # Konto-Reiter (Spec Portal-Erweiterung v1.1, Kap. 6/7). Bewusst ohne
    # ID im Pfad: die Zuordnung kommt ausschließlich aus der Sitzung, damit
    # eine geratene fremde ID nichts erreichen kann.
    path('portal/personenkonto/saldo/', PortalSaldoView.as_view(), name='portal-saldo'),
    path('portal/faelligkeiten/', PortalFaelligkeitenView.as_view(),
         name='portal-faelligkeiten'),
]
