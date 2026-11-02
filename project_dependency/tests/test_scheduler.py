# -*- coding: utf-8 -*-
"""El motor de programación (calendario, 4 tipos de vínculo, restricciones).

Proyecto genérico, calendario lunes a viernes en UTC para que las fechas sean
deterministas. El 2-nov-2026 es lunes.
"""
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestScheduler(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cal = cls.env.company.resource_calendar_id
        cal.write({"tz": "UTC"})
        cal.global_leave_ids.unlink()
        cls.cal = cal
        cls.proyecto = cls.env["project.project"].create({"name": "Motor"})
        cls.T = cls.env["project.task"]

    def _t(self, nombre, ini, fin, **extra):
        return self.T.create({"name": nombre, "project_id": self.proyecto.id,
                              "planned_date_begin": f"2026-11-{ini:02d} 08:00:00",
                              "date_deadline": f"2026-11-{fin:02d} 17:00:00", **extra})

    def _link(self, a, b, tipo="fs", lag=0.0, natural=False):
        self.env["project.dependency"].create({"predecessor_id": a.id, "successor_id": b.id,
                                                  "link_type": tipo, "lag_days": lag, "lag_elapsed": natural})

    def _run(self, apply=True):
        return self.T.scheduler_run([("project_id", "=", self.proyecto.id)], apply=apply)

    def _dias(self, t):
        return (t.planned_date_begin.day, t.date_deadline.day)

    def test_finish_to_start_skips_the_weekend(self):
        a = self._t("A", 2, 4)          # lun–mié, 3 días
        b = self._t("B", 20, 23)        # 2 días laborables (vie 20 – lun 23)
        c = self._t("C", 2, 3)          # 2 días
        self._link(a, b)
        self._link(b, c)
        self._run()
        self.assertEqual(self._dias(b), (5, 6), "jue–vie, después de A")
        self.assertEqual(self._dias(c), (9, 10), "lun–mar: el fin de semana no cuenta")

    def test_lag_in_working_and_calendar_days(self):
        a = self._t("A", 2, 4)
        b = self._t("B", 2, 2)
        c = self._t("C", 2, 2)
        self._link(a, b, lag=2)                 # jue + 2 laborables = lun 9
        self._link(a, c, lag=1, natural=True)   # jue + 1 natural = vie 6
        self._run()
        self.assertEqual(self._dias(b), (9, 9))
        self.assertEqual(self._dias(c), (6, 6))

    def test_start_to_start_and_finish_to_finish(self):
        a = self._t("A", 2, 4)
        b = self._t("B", 16, 16)
        c = self._t("C", 16, 17)   # 2 días
        self._link(a, b, "ss", lag=1)
        self._link(a, c, "ff")
        self._run()
        self.assertEqual(self._dias(b), (3, 3))
        self.assertEqual(self._dias(c), (3, 4), "termina cuando termina A")

    def test_a_milestone_after_a_task_falls_on_its_finish_day(self):
        a = self._t("A", 2, 4)
        h = self._t("Hito", 20, 20, is_milestone=True)
        self._link(a, h)
        self._run()
        self.assertEqual(h.planned_date_begin.day, 4)
        self.assertEqual(h.planned_date_begin, h.date_deadline)

    def test_a_holiday_is_not_a_working_day(self):
        self.env["resource.calendar.leaves"].create({
            "name": "Feriado", "calendar_id": self.cal.id,
            "date_from": "2026-11-05 00:00:00", "date_to": "2026-11-05 23:59:59"})
        a = self._t("A", 2, 4)
        b = self._t("B", 2, 2)
        self._link(a, b)
        self._run()
        self.assertEqual(self._dias(b), (6, 6))

    def test_constraints(self):
        a = self._t("A", 2, 4)
        snet = self._t("SNET", 2, 2, constraint_type="snet", constraint_date="2026-11-16 08:00:00")
        mfo = self._t("MFO", 2, 3, constraint_type="mfo", constraint_date="2026-11-04 17:00:00")
        self._link(a, mfo)  # A empujaría su inicio al jue 5: choca con «debe terminar el mié 4»
        snlt = self._t("SNLT", 2, 2, constraint_type="snlt", constraint_date="2026-11-03 08:00:00")
        self._link(a, snlt)
        r = self._run()
        self.assertEqual(self._dias(snet), (16, 16))
        self.assertEqual(self._dias(mfo), (3, 4), "la restricción manda")
        self.assertEqual({c["id"] for c in r["conflicts"]}, {mfo.id, snlt.id}, "y se avisan los dos incumplimientos")

    def test_as_late_as_possible(self):
        a = self._t("A", 2, 4)
        b = self._t("B", 5, 10)       # fin del proyecto: mar 10
        x = self._t("X", 2, 2, constraint_type="alap")
        self._link(a, b)
        self._run()
        self.assertEqual(self._dias(x), (10, 10))

    def test_summary_rolls_up_and_preview_does_not_write(self):
        padre = self._t("Padre", 2, 2)
        a = self._t("A", 2, 4, parent_id=padre.id)
        b = self._t("B", 2, 3, parent_id=padre.id)
        self._link(a, b)
        vista = self._run(apply=False)
        self.assertEqual(self._dias(b), (2, 3), "la vista previa no escribe")
        self.assertIn(b.id, {c["id"] for c in vista["changes"]})
        self._run()
        self.assertEqual(self._dias(padre), (2, 6), "el resumen abarca a sus hijas")

    def test_tasks_without_predecessors_stay_where_they_are(self):
        sola = self._t("Sola", 18, 19)
        self._run()
        self.assertEqual(self._dias(sola), (18, 19))

    def test_who_cannot_edit_tasks_cannot_apply(self):
        a = self._t("A", 2, 4)
        b = self._t("B", 2, 2)
        self._link(a, b)
        lector = self.env["res.users"].create({"name": "sched", "login": "sched_reader",
                                               "group_ids": [(6, 0, [self.env.ref("base.group_user").id])]})
        with self.assertRaises(AccessError):
            self.T.with_user(lector).scheduler_run([("project_id", "=", self.proyecto.id)], apply=True)

    def test_links_to_and_from_a_summary_apply_to_its_subtasks(self):
        """Como MS Project: hacia un resumen = hacia sus subtareas; desde un
        resumen = desde su fin (la más tardía) o su inicio (la más temprana)."""
        a = self._t("A", 2, 4)
        paquete = self._t("Paquete", 2, 2)
        p1 = self._t("P1", 2, 2, parent_id=paquete.id)     # 1 día
        p2 = self._t("P2", 16, 17, parent_id=paquete.id)   # 2 días
        despues = self._t("Después", 2, 2)
        junto = self._t("Junto", 20, 20)
        self._link(a, paquete)              # hacia el resumen: P1 y P2 tras A
        self._link(paquete, despues)        # desde su fin: tras la más tardía
        self._link(paquete, junto, "ss")    # desde su inicio: con la más temprana
        r = self._run()
        self.assertEqual(r["skipped_links"], 0)
        self.assertEqual((self._dias(p1), self._dias(p2)), ((5, 5), (5, 6)))
        self.assertEqual(self._dias(despues), (9, 9), "después del fin del paquete (vie 6)")
        self.assertEqual(self._dias(junto), (5, 5), "con el inicio del paquete (jue 5)")

    def test_the_project_calendar_rules_and_the_duration_is_kept(self):
        """Calendario por proyecto; la duración guardada se
        conserva al cambiarlo y las fechas se ajustan al calcular."""
        a = self._t("A", 2, 4)        # 3 días laborables
        b = self._t("B", 2, 3)        # 2 días
        self._link(a, b)
        self.assertEqual(b.duration_days, 2.0)
        seis = self.cal.copy({"name": "Lunes a sábado"})
        sabado = self.env["resource.calendar.attendance"]
        sabado.create({"calendar_id": seis.id, "name": "Sábado", "dayofweek": "5", "hour_from": 8, "hour_to": 17, "day_period": "full_day"})
        self.proyecto.schedule_calendar_id = seis
        self._run()
        self.assertEqual(self._dias(b), (5, 6), "jue–vie")
        self.assertEqual(b.duration_days, 2.0)
        b._set_planned_duration(3)            # vie + sáb: el sábado ya es laborable
        self.assertEqual(self._dias(b), (5, 7))

    def test_manual_tasks_and_actual_dates_are_not_moved(self):
        a = self._t("A", 2, 4)
        manual = self._t("Manual", 2, 3, manually_scheduled=True)
        hecha = self._t("Hecha", 2, 2, actual_start="2026-11-02 08:00:00", actual_finish="2026-11-02 17:00:00")
        en_curso = self._t("En curso", 2, 3, actual_start="2026-11-03 08:00:00")
        for t in (manual, hecha, en_curso):
            self._link(a, t)
        self._run()
        self.assertEqual(self._dias(manual), (2, 3), "manual: no se mueve")
        self.assertEqual(self._dias(hecha), (2, 2), "terminada: fechas reales")
        self.assertEqual(self._dias(en_curso), (3, 4), "en curso: inicio real, fin por duración")

    def test_honor_constraints_decides_between_link_and_constraint(self):
        a = self._t("A", 2, 4)
        b = self._t("B", 2, 2, constraint_type="fnlt", constraint_date="2026-11-03 17:00:00")
        self._link(a, b)
        r = self._run()
        self.assertEqual(self._dias(b), (3, 3), "respeta la restricción: se queda en su límite")
        self.assertIn(b.id, {c["id"] for c in r["conflicts"]})
        self.proyecto.honor_constraints = False
        self._run()
        self.assertEqual(self._dias(b), (5, 5), "sin respetar: gana el vínculo")

    def test_schedule_from_finish_puts_tasks_at_their_latest_dates(self):
        self.proyecto.write({"schedule_from": "finish", "project_finish": "2026-11-20 17:00:00"})
        a = self._t("A", 2, 4)   # 3 días
        b = self._t("B", 2, 3)   # 2 días, la última
        self._link(a, b)
        self._run()
        self.assertEqual(self._dias(b), (19, 20), "termina en la fecha de fin del proyecto")
        self.assertEqual(self._dias(a), (16, 18), "y su predecesora, justo antes")

    def test_removing_a_link_removes_its_native_arrow(self):
        """Sin esto, reimportar con vínculos al revés chocaba con Odoo."""
        a = self._t("A", 2, 4)
        b = self._t("B", 5, 6)
        self._link(a, b)
        self.assertIn(a, b.depend_on_ids)
        b.predecessor_link_ids.unlink()
        self.assertNotIn(a, b.depend_on_ids)
        self._link(b, a)   # al revés: ya no choca
        self.assertIn(b, a.depend_on_ids)

    def test_a_cycle_through_a_summary_does_not_break_the_calculation(self):
        """Un vínculo hacia un resumen y otro desde su subtarea de vuelta
        cierran un ciclo al expandirse; se reporta en vez de tronar."""
        paquete = self._t("Paquete", 2, 2)
        hija = self._t("Hija", 2, 3, parent_id=paquete.id)
        fuera = self._t("Fuera", 9, 10)
        self._link(fuera, paquete)   # hacia el resumen = hacia «Hija»
        self._link(hija, fuera)      # y de «Hija» de vuelta a «Fuera»
        r = self._run(apply=False)
        self.assertGreaterEqual(r["skipped_links"], 1)


@tagged("post_install", "-at_install")
class TestCompanyHolidays(TransactionCase):
    """Un día festivo SIN calendario es feriado de todos los calendarios
    de la compañía (regla de Odoo, `_leave_intervals_batch`)."""

    def test_a_holiday_without_calendar_counts(self):
        from datetime import date
        from odoo.addons.project_dependency.models.scheduler import calendar_for
        cal = self.env["resource.calendar"].create({"name": "L-V", "tz": "UTC"})
        self.env["resource.calendar.leaves"].create({
            "name": "Festivo de la empresa", "calendar_id": False, "resource_id": False,
            "date_from": "2026-11-16 00:00:00", "date_to": "2026-11-16 23:59:00"})
        otra = self.env["res.company"].create({"name": "Otra"})
        # La compañía de un festivo sin calendario la calcula Odoo
        # (`_compute_company_id`: la activa de quien lo crea); se fija aquí.
        ajeno = self.env["resource.calendar.leaves"].create({
            "name": "Festivo de otra empresa", "calendar_id": False, "resource_id": False,
            "date_from": "2026-11-17 00:00:00", "date_to": "2026-11-17 23:59:00"})
        ajeno.company_id = otra
        self.assertTrue(cal.company_id)
        self.assertEqual(ajeno.company_id, otra)
        work, _tz = calendar_for(cal, date(2026, 11, 1), date(2026, 11, 30))
        self.assertIn(date(2026, 11, 16), work.holidays)
        self.assertNotIn(date(2026, 11, 17), work.holidays, "el de otra compañía no aplica")

    def test_between_counts_whole_days_like_walking_them(self):
        """Rendimiento: `between` cuenta los días completos con aritmética en vez de recorrerlos.
        Tiene que dar EXACTAMENTE lo mismo que sumar los turnos día por día: con feriados, fines
        de semana, un turno de 24 h y tramos de un minuto a más de un año."""
        import random
        from datetime import date, datetime as dt, timedelta

        from odoo.addons.project_dependency.models.scheduler import WorkTime

        def a_pie(cal, ini, fin):
            if fin <= ini:
                return 0.0
            total, d = 0.0, ini.date()
            while d <= fin.date():
                for a, b in cal.intervals(d):
                    x, y = max(a, ini), min(b, fin)
                    if y > x:
                        total += (y - x).total_seconds() / 60
                d += timedelta(days=1)
            return total

        azar = random.Random(84)
        feriados = {date(2026, 1, 1) + timedelta(days=azar.randint(0, 700)) for _ in range(40)}
        calendarios = [WorkTime({}, set()),
                       WorkTime({0: [(540, 780), (900, 1140)], 5: [(480, 840)], 6: [(0, 1440)]}, feriados)]
        for cal in calendarios:
            for _ in range(3000):
                ini = dt(2026, 1, 1) + timedelta(minutes=azar.randint(0, 700 * 1440))
                fin = ini + timedelta(minutes=azar.randint(-3000, 400 * 1440))
                self.assertAlmostEqual(cal.between(ini, fin), a_pie(cal, ini, fin), places=6,
                                       msg=f"{ini} → {fin}")
