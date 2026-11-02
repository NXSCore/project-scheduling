# -*- coding: utf-8 -*-
"""El motor dice QUÉ fija las fechas de cada tarea y qué vínculos
mandan.

Calendario lunes a viernes en UTC; el 2-nov-2026 es lunes. Las aserciones van
sobre el `kind` del motor y sobre nombres de tareas (datos), no sobre textos en
inglés: la prueba no depende del idioma.
"""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.project_dependency.models.scheduler import schedule


@tagged("post_install", "-at_install")
class TestScheduleDrivers(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cal = cls.env.company.resource_calendar_id
        cal.write({"tz": "UTC"})
        cal.global_leave_ids.unlink()
        cls.proyecto = cls.env["project.project"].create({"name": "Motivos"})
        cls.T = cls.env["project.task"]
        cls.pm = cls.env["res.users"].create({
            "name": "sched_pm", "login": "sched_pm", "group_ids": [(4, cls.env.ref("project.group_project_user").id)]})
        cls.ajeno = cls.env["res.users"].create({
            "name": "sched_portal", "login": "sched_portal", "group_ids": [(4, cls.env.ref("base.group_portal").id)]})

    def _t(self, nombre, ini, fin, **extra):
        return self.T.create({"name": nombre, "project_id": self.proyecto.id,
                              "planned_date_begin": f"2026-11-{ini:02d} 08:00:00",
                              "date_deadline": f"2026-11-{fin:02d} 17:00:00", **extra})

    def _link(self, a, b, tipo="fs"):
        self.env["project.dependency"].create({"predecessor_id": a.id, "successor_id": b.id, "link_type": tipo})

    def _motivos(self):
        entrada = self.T._scheduler_input(self.proyecto)
        motivos = {}
        schedule(entrada["data"], entrada["links"], entrada["cal"], entrada["tz"], entrada["mpd"],
                 project=entrada["options"], drivers=motivos)
        return motivos

    def test_each_task_says_what_fixes_its_dates(self):
        a = self._t("A", 2, 4)
        b = self._t("B", 20, 23)
        c = self._t("C", 2, 2, constraint_type="snet", constraint_date="2026-11-16 08:00:00")
        m = self._t("M", 2, 3, manually_scheduled=True)
        r = self._t("R", 2, 3, actual_start="2026-11-02 08:00:00")
        self._link(a, b)
        self._link(b, c)
        motivos = self._motivos()
        self.assertEqual(motivos[a.id]["kind"], "own_start")
        self.assertEqual((motivos[b.id]["kind"], motivos[b.id]["preds"]), ("predecessor", [a.id]))
        self.assertEqual(motivos[c.id]["kind"], "constraint", "el «no antes del 16» empuja más que B")
        self.assertEqual(motivos[m.id]["kind"], "manual")
        self.assertEqual(motivos[r.id]["kind"], "progress")

    def test_a_constraint_that_does_not_push_is_not_the_reason(self):
        """Control negativo: un «no antes de» ya cumplido por la predecesora no es lo que manda."""
        a = self._t("A", 2, 4)
        b = self._t("B", 20, 23, constraint_type="snet", constraint_date="2026-11-02 08:00:00")
        self._link(a, b)
        self.assertEqual(self._motivos()[b.id]["kind"], "predecessor")

    def test_only_the_driving_link_is_reported(self):
        """A termina el 6 y X el 3: los dos llegan a C, pero solo A→C fija su inicio."""
        a = self._t("A", 2, 6)
        x = self._t("X", 2, 3)
        c = self._t("C", 20, 20)
        self._link(a, c)
        self._link(x, c)
        pares = self.T.with_user(self.pm).scheduler_driving_links([("project_id", "=", self.proyecto.id)])
        self.assertIn([a.id, c.id], pares)
        self.assertNotIn([x.id, c.id], pares, "X tiene holgura respecto de C: no manda")

    def test_tied_predecessors_drive_together(self):
        a = self._t("A", 2, 4)
        x = self._t("X", 2, 4)
        c = self._t("C", 20, 20)
        self._link(a, c)
        self._link(x, c)
        self.assertEqual(self._motivos()[c.id]["preds"], sorted([a.id, x.id]))

    def test_calculate_preview_carries_the_reason(self):
        """«Calcular» (vista previa) explica cada cambio; el de B nombra a su predecesora."""
        a = self._t("A", 2, 4)
        b = self._t("B", 20, 23)
        self._link(a, b)
        res = self.T.with_user(self.pm).scheduler_run([("project_id", "=", self.proyecto.id)])
        cambio = next(c for c in res["changes"] if c["id"] == b.id)
        self.assertIn("A", cambio["reason"])
        self.assertTrue(all(c["reason"] for c in res["changes"]), "ningún cambio sin motivo")

    def test_simulation_explains_the_moves(self):
        a = self._t("A", 2, 4)
        b = self._t("B", 5, 6)
        self._link(a, b)
        self.T.scheduler_run([("project_id", "=", self.proyecto.id)], apply=True)
        res = self.T.with_user(self.pm).scheduler_simulate(self.proyecto, {a.id: {"duration": 5.0}})
        motivo = {c["task"].id: c["reason"] for c in res["changes"]}
        self.assertIn("A", motivo[b.id], "B se mueve por su predecesora A")
        self.assertNotIn("A", motivo[a.id], "A se mueve por su propia duración, no por sí misma")
        sim = self.env["project.schedule.simulation"].with_user(self.pm).with_context(
            active_model="project.project", active_id=self.proyecto.id).create(
            {"line_ids": [(0, 0, {"task_id": a.id, "new_duration": 5.0})]})
        sim.action_simulate()
        self.assertIn(motivo[b.id], sim.result_html, "el asistente muestra el motivo")

    def test_driving_links_only_among_visible_tasks(self):
        """Quien no ve el proyecto no recibe ningún vínculo (la búsqueda va con sus permisos)."""
        a, c = self._t("A", 2, 4), self._t("C", 20, 20)
        self._link(a, c)
        dominio = [("project_id", "=", self.proyecto.id)]
        self.assertEqual(self.T.with_user(self.pm).scheduler_driving_links(dominio), [[a.id, c.id]])
        self.assertEqual(self.T.with_user(self.ajeno).scheduler_driving_links(dominio), [])
