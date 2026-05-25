from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import WirtschaftsplanViewSet

router = DefaultRouter()
router.register(r'wirtschaftsplaene', WirtschaftsplanViewSet, basename='wirtschaftsplaene')

urlpatterns = router.urls
