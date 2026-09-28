from rest_framework.routers import DefaultRouter

from .views import (
    BeschlussViewSet, EVTeilnehmerViewSet, EigentuemerversammlungViewSet,
    TagesordnungspunktViewSet, VersammlungsortViewSet,
)

router = DefaultRouter()
router.register(r'versammlungen', EigentuemerversammlungViewSet, basename='versammlungen')
router.register(
    r'tagesordnungspunkte', TagesordnungspunktViewSet, basename='tagesordnungspunkte',
)
router.register(r'ev-teilnehmer', EVTeilnehmerViewSet, basename='ev-teilnehmer')
router.register(r'beschluesse', BeschlussViewSet, basename='beschluesse')
router.register(r'versammlungsorte', VersammlungsortViewSet, basename='versammlungsorte')

urlpatterns = router.urls
