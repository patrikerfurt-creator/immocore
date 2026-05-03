from django.core.management.base import BaseCommand
from apps.rechnungen.models import Rechnung


class Command(BaseCommand):
    help = "Prüft OP-Konsistenz: freigegeben haben aufwandskonto, bezahlt haben aufwand_buchung."

    def handle(self, *args, **opts):
        fehler = 0

        freigegeben = Rechnung.objects.filter(status="freigegeben")
        for r in freigegeben.iterator():
            if not r.aufwandskonto_id:
                self.stdout.write(self.style.ERROR(
                    f"Rechnung {r.rechnungsnummer or r.id} (Objekt {r.objekt_id}): "
                    f"status=freigegeben, aber kein aufwandskonto"
                ))
                fehler += 1

        bezahlt = Rechnung.objects.filter(status="bezahlt")
        for r in bezahlt.iterator():
            if not r.aufwand_buchung_id and not r.buchung_id:
                self.stdout.write(self.style.ERROR(
                    f"Rechnung {r.rechnungsnummer or r.id} (Objekt {r.objekt_id}): "
                    f"status=bezahlt, aber keine aufwand_buchung"
                ))
                fehler += 1

        if fehler == 0:
            self.stdout.write(self.style.SUCCESS("OP-Konsistenz: OK"))
        else:
            self.stdout.write(self.style.ERROR(f"OP-Konsistenz: {fehler} Abweichung(en)"))
