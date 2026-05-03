from rest_framework.routers import DefaultRouter
from .views import (
    PersonViewSet, SEPAMandatViewSet,
    EigentumsVerhaeltnisViewSet, HausgeldHistorieViewSet,
    MietvertragViewSet,
)

router = DefaultRouter()
router.register(r'personen', PersonViewSet, basename='personen')
router.register(r'sepa-mandate', SEPAMandatViewSet, basename='sepa-mandate')
router.register(r'eigentumsverhaeltnisse', EigentumsVerhaeltnisViewSet, basename='eigentumsverhaeltnisse')
router.register(r'hausgeld-historie', HausgeldHistorieViewSet, basename='hausgeld-historie')
router.register(r'mietvertraege', MietvertragViewSet, basename='mietvertraege')

urlpatterns = router.urls
