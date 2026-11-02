# -*- coding: utf-8 -*-
"""La banda de holgura del PDF termina en el fin MÁS TARDÍO del motor.

No termina en fin + holgura en días NATURALES: la holgura va en días
LABORABLES y sobre un fin de semana la banda se quedaría corta. Aquí A dura 2
días y B 10;
los dos llegan al hito M, así que A tiene 8 días laborables de holgura, que
cruzan un fin de semana: su fin tardío es el viernes 13 y fin + 8 naturales
daría el miércoles 11.
"""
import json
from datetime import timedelta
from unittest.mock import patch

import pytz

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.project_planner_report.models.gantt_pdf import C, GanttPdf


@tagged("post_install", "-at_install")
class TestFloatBand(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cal = cls.env.company.resource_calendar_id
        cal.write({"tz": "UTC"})
        cal.global_leave_ids.unlink()
        cls.proyecto = cls.env["project.project"].create({"name": "Banda de holgura"})
        T = cls.env["project.task"]

        def tarea(nombre, ini, fin, **extra):
            return T.create({"name": nombre, "project_id": cls.proyecto.id,
                             "planned_date_begin": f"2026-11-{ini:02d} 08:00:00",
                             "date_deadline": f"2026-11-{fin:02d} 17:00:00", **extra})
        cls.a, cls.b = tarea("A", 2, 3), tarea("B", 2, 13)
        cls.m = tarea("M", 13, 13, is_milestone=True)
        for pred in (cls.a, cls.b):
            cls.env["project.dependency"].create({"predecessor_id": pred.id, "successor_id": cls.m.id, "link_type": "fs"})
        T.scheduler_run([("project_id", "=", cls.proyecto.id)], apply=True)
        cls.usuario = cls.env["res.users"].create({
            "name": "sched", "login": "sched", "tz": "UTC",
            "group_ids": [(4, cls.env.ref("project.group_project_user").id)]})

    def _bandas(self, **vals):
        """Renderiza el PDF y devuelve (lienzo, [borde derecho de cada rectángulo de holgura]).
        Sin leyenda: su muestra verde también es un rectángulo del color de la holgura."""
        wiz = self.env["project.planner.report.wizard"].with_user(self.usuario).create(
            {"domain": json.dumps([("project_id", "=", self.proyecto.id)]), "show_legend": False, **vals})
        dibujos, original = [], GanttPdf.rect

        def espia(gantt, x, top, w, h, fill, stroke=None):
            if fill == C["float"]:
                dibujos.append((gantt, x + w))
            return original(gantt, x, top, w, h, fill, stroke)
        with patch.object(GanttPdf, "rect", espia):
            wiz._render_pdf()
        return dibujos

    def test_the_planner_gets_the_late_finish(self):
        datos = self.env["project.task"].with_user(self.usuario).planner_data([("project_id", "=", self.proyecto.id)])
        fila = next(t for t in datos["tasks"] if t["id"] == self.a.id)
        self.assertEqual(fila["late_finish"], self.a.late_finish.isoformat() + "Z")
        self.assertGreater(self.a.total_float_days, 0)

    def test_the_band_ends_at_the_late_finish_across_the_weekend(self):
        tardio = self.a.late_finish
        ingenuo = self.a.date_deadline + timedelta(days=self.a.total_float_days)
        self.assertGreater(tardio - ingenuo, timedelta(days=1), "el fin de semana no cuenta como holgura")
        dibujos = self._bandas(show_float=True)
        self.assertEqual(len(dibujos), 1, "solo A tiene holgura: B y M son críticas")
        gantt, borde = dibujos[0]
        local = pytz.utc.localize(tardio).astimezone(pytz.utc).replace(tzinfo=None)
        self.assertAlmostEqual(borde, gantt.X(gantt.axis.pos(local)), delta=0.5)

    def test_no_band_when_it_is_switched_off(self):
        self.assertFalse(self._bandas(show_float=False))


@tagged("post_install", "-at_install")
class TestReportComparesBaselines(TestFloatBand):
    """El PDF imprime las líneas base que el planificador compara. El
    módulo es genérico: aquí los ganchos del dominio se redefinen en memoria."""

    def _con_lineas_base(self, funcion):
        clase = type(self.env["project.task"])
        originales = clase._planner_baselines, clase._planner_baseline_dates
        tid = self.a.id
        clase._planner_baselines = lambda self_, proyectos: [
            {"id": 7, "name": "v2 · Vigente", "current": True}, {"id": 5, "name": "v1 · Contractual", "current": False}]
        clase._planner_baseline_dates = lambda self_, ids, tareas: {
            5: {tid: ["2026-11-02T08:00:00Z", "2026-11-04T17:00:00Z"]}} if 5 in ids else {}
        try:
            return funcion()
        finally:
            clase._planner_baselines, clase._planner_baseline_dates = originales

    def _wizard(self, **vals):
        return self.env["project.planner.report.wizard"].with_user(self.usuario).create(
            {"domain": json.dumps([("project_id", "=", self.proyecto.id)]), **vals})

    def test_the_compared_version_is_printed_and_named(self):
        wiz = self._wizard(show_baseline=True, compare_ids="[5]")
        valores = self._con_lineas_base(wiz._report_values)
        self.assertEqual(valores["compare_names"], ["v1 · Contractual"])
        self.assertEqual(valores["current_baseline"], "v2 · Vigente")
        fila = next(f for f in valores["rows"] if f["id"] == self.a.id)
        self.assertEqual(fila["compare"][0][1].day, 4)
        dibujos, original = [], GanttPdf.rect

        def espia(gantt, x, top, w, h, fill, stroke=None):
            dibujos.append(fill)
            return original(gantt, x, top, w, h, fill, stroke)
        with patch.object(GanttPdf, "rect", espia):
            self._con_lineas_base(wiz._render_pdf)
        self.assertIn(C["compare1"], dibujos, "la franja de la versión comparada")

    def test_an_id_the_project_does_not_offer_is_ignored(self):
        """Control negativo: solo se imprimen versiones que el proyecto ofrece, y nunca la vigente como «comparada»."""
        valores = self._con_lineas_base(self._wizard(show_baseline=True, compare_ids="[99, 7]")._report_values)
        self.assertEqual(valores["compare_names"], [])

    def test_without_the_baseline_option_nothing_is_compared(self):
        valores = self._con_lineas_base(self._wizard(show_baseline=False, compare_ids="[5]")._report_values)
        self.assertEqual(valores["compare_names"], [])


@tagged("post_install", "-at_install")
class TestReportFreeFloatColumn(TransactionCase):
    """La holgura libre como columna del PDF, siguiendo las columnas del planificador."""

    def test_the_column_carries_the_free_float(self):
        cal = self.env.company.resource_calendar_id
        cal.write({"tz": "UTC"})
        cal.global_leave_ids.unlink()
        proyecto = self.env["project.project"].create({"name": "Columna FF"})
        T = self.env["project.task"]
        a = T.create({"name": "A", "project_id": proyecto.id, "planned_date_begin": "2026-11-02 08:00:00",
                      "date_deadline": "2026-11-06 17:00:00"})
        d = T.create({"name": "D", "project_id": proyecto.id, "planned_date_begin": "2026-11-02 08:00:00",
                      "date_deadline": "2026-11-03 17:00:00"})
        m = T.create({"name": "M", "project_id": proyecto.id, "is_milestone": True,
                      "planned_date_begin": "2026-11-06 17:00:00", "date_deadline": "2026-11-06 17:00:00"})
        for pred in (a, d):
            self.env["project.dependency"].create({"predecessor_id": pred.id, "successor_id": m.id, "link_type": "fs"})
        T.scheduler_run([("project_id", "=", proyecto.id)], apply=True)
        wiz = self.env["project.planner.report.wizard"].create({
            "domain": json.dumps([("project_id", "=", proyecto.id)]), "follow_view": True,
            "view_columns": json.dumps(["name", "free_float"])})
        valores = wiz._report_values()
        fila = next(f for f in valores["rows"] if f["id"] == d.id)
        self.assertTrue(fila["cells"]["free_float"].startswith("3"), fila["cells"]["free_float"])
        self.assertTrue(wiz._render_pdf()[0].startswith(b"%PDF"))
