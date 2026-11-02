# -*- coding: utf-8 -*-
"""Días festivos oficiales de México, calculados en vez de cargados.

El retraso se mide en **días hábiles**, y un día hábil en México no es
solo "no es fin de semana": el artículo 74 de la Ley Federal del Trabajo fija
los días de descanso obligatorio.

**Se calculan, no se siembran.** Cargar una lista de fechas obligaría a que
alguien la actualizara cada año —y el año que se le olvidara, las alertas
empezarían a dispararse en festivos sin que nadie entendiera por qué—. Las
reglas del artículo 74 son deterministas, así que se derivan del año.

El propio artículo ya resuelve los "puentes": el 5 de febrero, el 21 de marzo y
el 20 de noviembre NO se descansan en su fecha, sino el primer o tercer lunes
del mes. No es una política de empresa, es la ley.

**Lo que NO se calcula y hay que saber:** el artículo 74 fracción IX incluye
"el que determinen las leyes electorales" para las jornadas de elección. Esas
fechas no son deterministas y hay que cargarlas a mano el año que toque, como
cualquier otro asueto propio de la empresa.
"""
from datetime import date, timedelta

from odoo import models


def _nth_weekday(year, month, weekday, n):
    """El n-ésimo `weekday` (0=lunes) del mes. `n` empieza en 1."""
    d = date(year, month, 1)
    adelanto = (weekday - d.weekday()) % 7
    return d + timedelta(days=adelanto + 7 * (n - 1))


class ResourceCalendar(models.Model):
    _inherit = "resource.calendar"

    def _mx_public_holidays(self, year):
        """Los descansos obligatorios del artículo 74 de la LFT para ese año."""
        festivos = [
            (date(year, 1, 1), "Año Nuevo"),
            (_nth_weekday(year, 2, 0, 1), "Día de la Constitución"),
            (_nth_weekday(year, 3, 0, 3), "Natalicio de Benito Juárez"),
            (date(year, 5, 1), "Día del Trabajo"),
            (date(year, 9, 16), "Independencia de México"),
            (_nth_weekday(year, 11, 0, 3), "Día de la Revolución"),
            (date(year, 12, 25), "Navidad"),
        ]
        # Fracción I bis: transmisión del Poder Ejecutivo Federal, cada seis
        # años. 2024 fue una; de ahí la progresión.
        if (year - 2024) % 6 == 0:
            festivos.append((date(year, 12, 1), "Transmisión del Poder Ejecutivo"))
        return festivos

    def _ensure_mx_holidays(self, year):
        """Deja los festivos del año en el calendario, sin duplicarlos.

        Se escriben como `resource.calendar.leaves` para que se VEAN en la
        interfaz de Odoo: quien quiera añadir un asueto propio de la empresa lo hace
        en el mismo sitio, y quien dude de por qué una alerta no saltó puede
        mirarlo. Un cálculo escondido en el código no se puede auditar.
        """
        Ausencia = self.env["resource.calendar.leaves"]
        for calendario in self:
            for dia, nombre in calendario._mx_public_holidays(year):
                inicio = "%s 00:00:00" % dia
                ya_esta = Ausencia.search_count([
                    ("calendar_id", "=", calendario.id),
                    ("date_from", ">=", inicio),
                    ("date_from", "<=", "%s 23:59:59" % dia),
                ])
                if ya_esta:
                    continue
                Ausencia.create({
                    "name": "%s (LFT art. 74)" % nombre,
                    "calendar_id": calendario.id,
                    "date_from": inicio,
                    "date_to": "%s 23:59:59" % dia,
                })
