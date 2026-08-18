from rest_framework.routers import DefaultRouter

from .views import VorgangTypAdminViewSet, VorgangTypViewSet, VorgangViewSet

router = DefaultRouter()
# Reihenfolge wichtig: 'vorgang-typen/admin' muss VOR 'vorgang-typen' registriert
# werden, damit die Admin-Detail-Route (…/admin/<pk>/) nicht von der generischen
# 'vorgang-typen/<pk>/'-Route des Lese-ViewSets verschluckt wird.
router.register(r'vorgang-typen/admin', VorgangTypAdminViewSet, basename='vorgang-typen-admin')
router.register(r'vorgang-typen', VorgangTypViewSet, basename='vorgang-typen')
router.register(r'vorgaenge', VorgangViewSet, basename='vorgaenge')

urlpatterns = router.urls
