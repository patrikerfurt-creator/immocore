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
from .views_verwaltung import PortalZugangViewSet

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
]
