from django.urls import path
from . import views

urlpatterns = [
    path('massenimport/vorlage/weg/',  views.vorlage_weg,  name='massenimport-vorlage-weg'),
    path('massenimport/weg/preview/',  views.preview_weg,  name='massenimport-preview-weg'),
    path('massenimport/weg/commit/',   views.commit_weg,   name='massenimport-commit-weg'),
    path('massenimport/jobs/<uuid:job_id>/', views.job_status, name='massenimport-job-status'),
]
