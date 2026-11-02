# -*- coding: utf-8 -*-
"""La salud del cronograma (evaluación DCMA de 14 puntos).

Calendario lunes a viernes en UTC; el 2-nov-2026 es lunes. Se compara por el
`code` de cada chequeo y su `result`, no por textos: independiente del idioma.
"""
from datetime import datetime
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestScheduleHealth(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cal = cls.env.company.resource_calendar_id
        cal.write({"tz": "UTC"})
        cal.global_leave_ids.unlink()
        cls.T = cls.env["project.task"]
        cls.proyecto = cls.env["project.project"].create({"name": "Salud"})
        cls.pm = cls.env["res.users"].create({
            "name": "sched_pm", "login": "sched_pm", "groups_id": [(4, cls.env.ref("project.group_project_user").id)]})

    def _t(self, nombre, ini, fin, proyecto=None, **extra):
        return self.T.create({"name": nombre, "project_id": (proyecto or self.proyecto).id,
                              "planned_date_begin": f"2026-11-{ini:02d} 08:00:00",
                              "date_deadline": f"2026-11-{fin:02d} 17:00:00", **extra})

    def _link(self, a, b, tipo="fs", lag=0.0):
        self.env["project.dependency"].create({"predecessor_id": a.id, "successor_id": b.id,
                                                  "link_type": tipo, "lag_days": lag})

    def _check(self, usuario=None, proyecto=None):
        salud = self.env["project.schedule.health"].with_user(usuario or self.pm).with_context(
            active_model="project.project", active_id=(proyecto or self.proyecto).id).create(
            {"status_date": datetime(2026, 11, 2, 0, 0)})
        salud.action_check()
        return salud, {linea.code: linea for linea in salud.line_ids}

    def _cadena(self):
        a, b, c = self._t("A", 2, 4), self._t("B", 5, 6), self._t("C", 9, 10)
        self._link(a, b)
        self._link(b, c)
        self.T.scheduler_run([("project_id", "=", self.proyecto.id)], apply=True)
        return a, b, c

    def test_a_clean_chain_passes_the_logic_checks(self):
        self._cadena()
        salud, r = self._check()
        self.assertEqual(len(r), 14, "los catorce puntos")
        self.assertEqual(salud.task_count, 3)
        for code in ("leads", "lags", "link_types", "hard_constraints", "negative_float", "invalid_dates",
                     "critical_path_test"):
            self.assertEqual(r[code].result, "pass", code)
        # Sin línea base (proyecto genérico): los puntos que la necesitan no se inventan.
        for code in ("missed_tasks", "cpli", "bei"):
            self.assertEqual(r[code].result, "na", code)
        # Lo que no aplica no muestra conteo ni tareas (se leía como hallazgo).
        # (Recursos sí aplica aquí: en Odoo 19 la tarea nace asignada a quien la crea.)
        for code in ("missed_tasks", "cpli", "bei"):
            self.assertEqual((r[code].value, len(r[code].task_ids)), ("—", 0), code)

    def test_defects_are_found_and_listed(self):
        """Control negativo: cada defecto sembrado enciende SU chequeo y lista la tarea culpable."""
        a, b, c = self._cadena()
        suelta = self._t("Suelta", 2, 3)
        dura = self._t("Dura", 16, 17, constraint_type="mso", constraint_date="2026-11-16 08:00:00")
        self._link(c, dura, tipo="ss", lag=-1)
        _salud, r = self._check()
        self.assertEqual(r["logic"].result, "fail")
        self.assertIn(suelta, r["logic"].task_ids)
        self.assertEqual(r["leads"].result, "fail")
        self.assertIn(dura, r["leads"].task_ids)
        self.assertEqual(r["link_types"].result, "fail", "1 de 3 no es fin-inicio")
        self.assertEqual(r["hard_constraints"].result, "fail")
        self.assertIn(dura, r["hard_constraints"].task_ids)

    def test_the_critical_path_test_fails_when_a_constraint_absorbs_the_delay(self):
        """Control negativo del punto 12: si el fin lo fija un «debe terminar el», alargar la ruta no lo mueve."""
        _a, _b, c = self._cadena()
        fin = self._t("Fin", 30, 30, constraint_type="mfo", constraint_date="2026-11-30 17:00:00")
        self._link(c, fin)
        self.T.scheduler_run([("project_id", "=", self.proyecto.id)], apply=True)
        _salud, r = self._check()
        self.assertEqual(r["critical_path_test"].result, "fail")

    def test_forecast_dates_before_the_status_date_are_invalid(self):
        self._cadena()
        salud = self.env["project.schedule.health"].with_user(self.pm).with_context(
            active_model="project.project", active_id=self.proyecto.id).create(
            {"status_date": datetime(2026, 11, 7, 0, 0)})
        salud.action_check()
        linea = salud.line_ids.filtered(lambda x: x.code == "invalid_dates")
        self.assertEqual(linea.result, "fail", "A y B debían haber empezado y no tienen inicio real")
        self.assertEqual(len(linea.task_ids), 2)

    def test_the_baseline_hook_feeds_the_baseline_checks(self):
        """Con línea base (aquí, el gancho redefinido en memoria), BEI y tareas incumplidas sí se miden."""
        a, b, c = self._cadena()
        base = {a.id: (datetime(2026, 11, 2, 8), datetime(2026, 11, 4, 17)),
                b.id: (datetime(2026, 11, 5, 8), datetime(2026, 11, 6, 17)),
                c.id: (datetime(2026, 11, 9, 8), datetime(2026, 11, 10, 17))}
        salud = self.env["project.schedule.health"].with_user(self.pm).with_context(
            active_model="project.project", active_id=self.proyecto.id).create(
            {"status_date": datetime(2026, 11, 9, 0, 0)})
        # patch.object y no asignar y «regresar» el original: eso deja una copia del método en el
        # __dict__ de la clase (antes era heredado) y Odoo 18 lo marca al terminar la prueba.
        with patch.object(type(self.env["project.task"]), "_schedule_baseline",
                          lambda self_: {i: v for i, v in base.items() if i in self_.ids}):
            salud.action_check()
        r = {linea.code: linea for linea in salud.line_ids}
        self.assertEqual(r["missed_tasks"].result, "fail", "A y B debían terminar el 4 y el 6 y no tienen fin real")
        self.assertEqual(r["bei"].result, "fail")
        self.assertEqual(r["cpli"].result, "pass", "el fin pronosticado coincide con la línea base")

    def test_permissions(self):
        """Solo quien trabaja proyectos revisa la salud (la misma ACL que la simulación)."""
        portal = self.env["res.users"].create({
            "name": "sched_portal", "login": "sched_portal", "groups_id": [(4, self.env.ref("base.group_portal").id)]})
        with self.assertRaises(AccessError):
            self.env["project.schedule.health"].with_user(portal).create({"project_id": self.proyecto.id})

    def test_company_isolation(self):
        """Un usuario de la compañía A no lee las tareas de un cronograma de la compañía B."""
        otra = self.env["res.company"].create({"name": "Otra"})
        ajeno = self.env["project.project"].create({"name": "Ajeno", "company_id": otra.id})
        x, y = self._t("X", 2, 4, proyecto=ajeno), self._t("Y", 5, 6, proyecto=ajeno)
        self._link(x, y)
        salud, _r = self._check(proyecto=ajeno)
        self.assertEqual(salud.task_count, 0)
        self.assertFalse(salud.line_ids)
