# -*- coding: utf-8 -*-
"""Pronóstico a corto plazo y críticas y casi críticas.

Calendario lunes a viernes en UTC; el 2-nov-2026 es lunes. Se compara por el
estado (código) y por la tarea, no por textos: independiente del idioma.
"""
from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestScheduleReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cal = cls.env.company.resource_calendar_id
        cal.write({"tz": "UTC"})
        cal.global_leave_ids.unlink()
        cls.T = cls.env["project.task"]
        cls.proyecto = cls.env["project.project"].create({"name": "Reportes"})
        cls.pm = cls.env["res.users"].create({
            "name": "sched_pm", "login": "sched_pm", "group_ids": [(4, cls.env.ref("project.group_project_user").id)]})
        t = cls._t
        # A→B→C es la ruta crítica (fin el 10); E tiene 2 días laborables de holgura (jue 5 y vie 6) y F 4.
        cls.a, cls.b, cls.c = t("A", 2, 4), t("B", 5, 6), t("C", 9, 10)
        cls.e, cls.f = t("E", 2, 4), t("F", 2, 2)
        cls.lejos = t("Lejos", 30, 30)
        for pred, succ in ((cls.a, cls.b), (cls.b, cls.c), (cls.e, cls.c), (cls.f, cls.c), (cls.c, cls.lejos)):
            cls.env["project.dependency"].create({"predecessor_id": pred.id, "successor_id": succ.id, "link_type": "fs"})
        cls.lejos.write({"constraint_type": "snet", "constraint_date": "2026-11-30 08:00:00"})
        cls.T.scheduler_run([("project_id", "=", cls.proyecto.id)], apply=True)

    @classmethod
    def _t(cls, nombre, ini, fin):
        return cls.T.create({"name": nombre, "project_id": cls.proyecto.id,
                             "planned_date_begin": f"2026-11-{ini:02d} 08:00:00",
                             "date_deadline": f"2026-11-{fin:02d} 17:00:00"})

    def _run(self, usuario=None, proyecto=None, **vals):
        rep = self.env["project.schedule.report"].with_user(usuario or self.pm).with_context(
            active_model="project.project", active_id=(proyecto or self.proyecto).id).create(vals)
        rep.action_run()
        return rep, {linea.task_id: linea for linea in rep.line_ids}

    def test_the_period_counts_weeks_of_seven_days_from_the_reference_day(self):
        rep, _f = self._run(reference_date=date(2026, 11, 5), period="next_1w")
        self.assertEqual((rep.date_from, rep.date_to), (date(2026, 11, 5), date(2026, 11, 11)))
        rep, _f = self._run(reference_date=date(2026, 11, 5), period="next_month")
        self.assertEqual(rep.date_to, date(2026, 12, 4))

    def test_a_custom_period_needs_two_dates_in_order(self):
        with self.assertRaises(UserError):
            self._run(period="custom", date_from=date(2026, 11, 5))
        with self.assertRaises(UserError):
            self._run(period="custom", date_from=date(2026, 11, 9), date_to=date(2026, 11, 5))

    def test_lookahead_lists_what_runs_or_starts_and_what_is_overdue(self):
        """Día 5, siguiente semana (5-11): A está vencida, B y C por empezar; «Lejos» (el 30) no entra."""
        self.b.write({"actual_start": "2026-11-05 08:00:00"})
        rep, f = self._run(reference_date=date(2026, 11, 5), period="next_1w")
        self.assertEqual(f[self.a].status, "overdue")
        self.assertEqual(f[self.b].status, "in_progress", "tiene inicio real")
        self.assertEqual(f[self.c].status, "starting")
        self.assertNotIn(self.lejos, f, "control negativo: fuera del periodo")
        self.assertEqual(rep.overdue_count, sum(1 for linea in rep.line_ids if linea.status == "overdue"))

    def test_a_started_task_with_no_progress_should_have_started(self):
        rep, f = self._run(reference_date=date(2026, 11, 6), period="next_1w")
        self.assertEqual(f[self.b].status, "should_have_started")

    def test_critical_and_near_critical_by_threshold(self):
        # «Lejos» (no antes del 30) alargaría el proyecto y le daría holgura a la ruta A-B-C.
        self.lejos.unlink()
        _rep, f = self._run(report_type="critical", near_critical_days=3)
        self.assertTrue(f[self.a].critical and f[self.c].critical)
        self.assertTrue(f[self.e].near_critical)
        self.assertNotIn(self.f, f, "control negativo: 4 días de holgura pasan del umbral de 3")
        rep, f = self._run(report_type="critical", near_critical_days=5)
        self.assertTrue(f[self.f].near_critical)
        self.assertTrue(rep.line_ids[0].critical, "las críticas van primero")
        self.assertFalse(rep.line_ids[-1].critical)

    def test_the_pdf_template_renders(self):
        self.lejos.unlink()
        rep, _f = self._run(report_type="critical")
        html = self.env["ir.actions.report"].with_user(self.pm)._render_qweb_html(
            "project_dependency.project_schedule_report_document", rep.ids)[0]
        self.assertIn(b"C", html)
        self.assertEqual(rep.action_print()["report_name"], "project_dependency.project_schedule_report_document")

    def test_permissions(self):
        portal = self.env["res.users"].create({
            "name": "sched_portal", "login": "sched_portal", "group_ids": [(4, self.env.ref("base.group_portal").id)]})
        with self.assertRaises(AccessError):
            self.env["project.schedule.report"].with_user(portal).create({"project_id": self.proyecto.id})

    def test_company_isolation(self):
        otra = self.env["res.company"].create({"name": "Otra"})
        ajeno = self.env["project.project"].create({"name": "Ajeno", "company_id": otra.id})
        self.T.create({"name": "X", "project_id": ajeno.id, "planned_date_begin": "2026-11-02 08:00:00",
                       "date_deadline": "2026-11-04 17:00:00"})
        rep, _f = self._run(proyecto=ajeno, report_type="critical")
        self.assertFalse(rep.line_ids)
