# -*- coding: utf-8 -*-
"""Simular la reprogramación (fechas y duraciones) sin aplicarla.

Mismo arreglo que el motor (`test_scheduler`): calendario lunes a viernes en UTC; el 2-nov-2026 es lunes.
"""
from datetime import datetime

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestScheduleSimulation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cal = cls.env.company.resource_calendar_id
        cal.write({"tz": "UTC"})
        cal.global_leave_ids.unlink()
        cls.proyecto = cls.env["project.project"].create({"name": "Simulación"})
        T = cls.env["project.task"]

        def tarea(nombre, ini, fin):
            return T.create({"name": nombre, "project_id": cls.proyecto.id,
                             "planned_date_begin": f"2026-11-{ini:02d} 08:00:00",
                             "date_deadline": f"2026-11-{fin:02d} 17:00:00"})
        cls.a, cls.b, cls.c = tarea("A", 2, 4), tarea("B", 5, 6), tarea("C", 9, 10)
        cls.d = tarea("D", 2, 3)
        for pred, succ in ((cls.a, cls.b), (cls.b, cls.c)):
            cls.env["project.dependency"].create({"predecessor_id": pred.id, "successor_id": succ.id, "link_type": "fs"})
        T.scheduler_run([("project_id", "=", cls.proyecto.id)], apply=True)
        cls.usuario = cls.env["res.users"].create({
            "name": "sched_pm", "login": "sched_pm", "group_ids": [(4, cls.env.ref("project.group_project_user").id)]})

    def _simular(self, lineas):
        simulacion = self.env["project.schedule.simulation"].with_user(self.usuario).with_context(
            active_model="project.project", active_id=self.proyecto.id).create({"line_ids": [(0, 0, l) for l in lineas]})
        simulacion.action_simulate()
        return simulacion

    def test_moving_a_start_shows_the_new_delivery_without_applying_it(self):
        """A empieza una semana después → B y C se recorren y la entrega se mueve 7 días; nada se guarda."""
        simulacion = self._simular([{"task_id": self.a.id, "new_start": datetime(2026, 11, 9, 8, 0)}])
        self.assertEqual(simulacion.finish_before.day, 10)
        self.assertEqual(simulacion.finish_after.day, 17)
        self.assertEqual(simulacion.delay_days, 7)
        self.assertIn("C", simulacion.result_html, "se recorre la cadena")
        self.assertEqual((self.a.planned_date_begin.day, self.c.date_deadline.day), (2, 10), "la simulación no aplica nada")

    def test_the_critical_path_is_recalculated(self):
        """Si D dura 10 días pasa a mandar la entrega: la ruta crítica nueva es D, no A-B-C."""
        resultado = self.env["project.task"].scheduler_simulate(self.proyecto, {self.d.id: {"duration": 10.0}})
        self.assertIn(self.d.id, resultado["critical_ids"])
        self.assertNotIn(self.a.id, resultado["critical_ids"])
        actual = self.env["project.task"].scheduler_simulate(self.proyecto, {})
        self.assertTrue({self.a.id, self.b.id, self.c.id} <= set(actual["critical_ids"]), "hoy manda la cadena A-B-C")
