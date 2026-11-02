# -*- coding: utf-8 -*-
"""Descansos obligatorios del artículo 74 de la LFT, calculados por año."""
from datetime import date

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestMxHolidays(TransactionCase):

    def test_mexican_public_holidays_follow_the_law(self):
        """Art. 74 LFT: los «puentes» caen en lunes; el cambio de poder, cada seis años."""
        calendario = self.env["resource.calendar"].create({"name": "Calendario"})
        festivos = dict((n, d) for d, n in calendario._mx_public_holidays(2026))
        self.assertEqual(festivos["Día de la Constitución"], date(2026, 2, 2))
        self.assertEqual(festivos["Día de la Revolución"], date(2026, 11, 16))
        self.assertTrue(any("Transmisión" in n for _d, n in calendario._mx_public_holidays(2030)))
        calendario._ensure_mx_holidays(2026)
        cuantas = self.env["resource.calendar.leaves"].search_count([("calendar_id", "=", calendario.id)])
        calendario._ensure_mx_holidays(2026)
        self.assertEqual(self.env["resource.calendar.leaves"].search_count([("calendar_id", "=", calendario.id)]), cuantas)

    def test_the_bridges_fall_on_mondays(self):
        """El 5 de febrero, el 21 de marzo y el 20 de noviembre se descansan en lunes."""
        calendario = self.env.ref("resource.resource_calendar_std")
        for year in (2025, 2026, 2027, 2031):
            for dia, nombre in calendario._mx_public_holidays(year):
                if dia.month in (2, 3, 11):
                    self.assertEqual(dia.weekday(), 0, "%s %s no cae en lunes" % (nombre, year))
        self.assertEqual(
            dict((n, d) for d, n in calendario._mx_public_holidays(2027))["Natalicio de Benito Juárez"],
            date(2027, 3, 15))
