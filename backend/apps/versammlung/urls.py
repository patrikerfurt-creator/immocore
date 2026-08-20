from rest_framework.routers import DefaultRouter

from .views import (
    BeschlussViewSet, EVTeilnehmerViewSet, EigentuemerversammlungViewSet,
    TagesordnungspunktViewSet,
)

router = DefaultRouter()
router.register(r'versammlungen', EigentuemerversammlungViewSet, basename='versammlungen')
router.register(
    r'tagesordnungspunkte', TagesordnungspunktViewSet, basename='tagesordnungspunkte',
)
router.register(r'ev-teilnehmer', EVTeilnehmerViewSet, basename='ev-teilnehmer')
router.register(r'beschluesse', BeschlussViewSet, basename='beschluesse')

urlpatterns = router.urls
