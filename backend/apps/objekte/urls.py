from rest_framework.routers import DefaultRouter
from .views import (
    ObjektViewSet, EingangViewSet, BankkontoViewSet, EinheitViewSet,
    VerteilerschluesselViewSet, VerteilerschluesselWertViewSet,
)

router = DefaultRouter()
router.register(r'objekte', ObjektViewSet, basename='objekte')
router.register(r'eingaenge', EingangViewSet, basename='eingaenge')
router.register(r'bankkonten', BankkontoViewSet, basename='bankkonten')
router.register(r'einheiten', EinheitViewSet, basename='einheiten')
router.register(r'verteilerschluessel', VerteilerschluesselViewSet, basename='verteilerschluessel')
router.register(r'verteilerschluessel-werte', VerteilerschluesselWertViewSet, basename='verteilerschluessel-werte')

urlpatterns = router.urls
