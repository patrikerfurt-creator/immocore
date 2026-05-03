from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ImportJob
from .services import commit_import, erzeuge_vorlage, preview_erstellen


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def vorlage_weg(request):
    """Liefert die MI-WEG.xlsx-Vorlage zum Herunterladen."""
    xlsx = erzeuge_vorlage()
    resp = HttpResponse(
        xlsx,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    resp['Content-Disposition'] = 'attachment; filename="MI-WEG.xlsx"'
    return resp


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def preview_weg(request):
    """Excel hochladen → Vorschau und preview_token zurückgeben. Kein DB-Commit der Objekte."""
    datei = request.FILES.get('datei')
    if not datei:
        return Response({'error': 'Datei fehlt (Feldname: datei).'}, status=status.HTTP_400_BAD_REQUEST)
    if not datei.name.lower().endswith('.xlsx'):
        return Response({'error': 'Nur .xlsx-Dateien werden unterstützt.'}, status=status.HTTP_400_BAD_REQUEST)
    if datei.size > 10 * 1024 * 1024:
        return Response({'error': 'Datei zu groß (max. 10 MB).'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = preview_erstellen(datei.read(), request.user)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return Response({'error': f'Fehler beim Verarbeiten der Datei: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

    return Response(result)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def commit_weg(request):
    """preview_token bestätigen → Objekte anlegen."""
    token = request.data.get('preview_token')
    if not token:
        return Response({'error': 'preview_token fehlt.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = commit_import(str(token), request.user)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_410_GONE)
    except Exception as exc:
        return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def job_status(request, job_id):
    """Status eines Import-Jobs abfragen."""
    try:
        job = ImportJob.objects.get(pk=job_id)
    except ImportJob.DoesNotExist:
        return Response({'error': 'Import-Job nicht gefunden.'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'id':             str(job.id),
        'typ':            job.typ,
        'status':         job.status,
        'zeilen_gesamt':  job.zeilen_gesamt,
        'zeilen_ok':      job.zeilen_ok,
        'zeilen_warnung': job.zeilen_warnung,
        'zeilen_fehler':  job.zeilen_fehler,
        'ergebnis':       job.ergebnis,
        'erstellt_am':    job.erstellt_am.isoformat(),
        'aktualisiert_am': job.aktualisiert_am.isoformat(),
    })
