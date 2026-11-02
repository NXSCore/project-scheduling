# -*- coding: utf-8 -*-
"""La holgura LIBRE (MS Project «Free Slack»).

Lo que una tarea puede retrasarse sin que ninguna sucesora se mueva. Calendario
lunes a viernes en UTC; el 2-nov-2026 es lunes. Valores hechos a mano en días
laborables.
"""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestFreeFloat(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cal = cls.env.company.resource_calendar_id
        cal.write({"tz": "UTC"})
        cal.global_leave_ids.unlink()
        cls.T = cls.env["project.task"]
        cls.pm = cls.env["res.users"].create({
            "name": "sched_pm", "login": "sched_pm", "group_ids": [(4, cls.env.ref("project.group_project_user").id)]})

    def setUp(self):
        super().setUp()
        self.proyecto = self.env["project.project"].create({"name": "Holgura libre"})

    def _t(self, nombre, ini, fin, **extra):
        return self.T.create({"name": nombre, "project_id": self.proyecto.id,
                              "planned_date_begin": f"2026-11-{ini:02d} 08:00:00",
                              "date_deadline": f"2026-11-{fin:02d} 17:00:00", **extra})

    def _link(self, a, b, tipo="fs", lag=0.0):
        self.env["project.dependency"].create({"predecessor_id": a.id, "successor_id": b.id,
                                                  "link_type": tipo, "lag_days": lag})

    def _calcular(self):
        self.T.scheduler_run([("project_id", "=", self.proyecto.id)], apply=True)
        self.T.invalidate_model()

    def _ruta(self):
        """A (lun-mié) → B (jue-vie) → C (lun-mar): la ruta crítica, fin el martes 10."""
        a, b, c = self._t("A", 2, 4), self._t("B", 5, 6), self._t("C", 9, 10)
        self._link(a, b)
        self._link(b, c)
        return a, b, c

    def test_a_parallel_branch_has_its_float_free(self):
        """D (lun-mar) → C: C empieza el lunes 9, así que D puede retrasarse mié, jue y vie = 3 días."""
        a, b, c = self._ruta()
        d = self._t("D", 2, 3)
        self._link(d, c)
        self._calcular()
        d = d.with_user(self.pm)
        self.assertAlmostEqual(d.free_float_days, 3.0, places=1)
        self.assertAlmostEqual(d.total_float_days, 3.0, places=1)
        for t in (a, b, c):
            self.assertAlmostEqual(t.free_float_days, 0.0, places=1, msg=t.name)

    def test_shared_float_is_free_only_for_the_last_task_of_the_chain(self):
        """X (lun) → Y (mar) → C: los dos tienen 3 días de holgura TOTAL, pero si X la usa, Y se mueve: la libre
        de X es 0 y la de Y, 3. Control negativo de la definición: libre ≠ total."""
        _a, _b, c = self._ruta()
        x, y = self._t("X", 2, 2), self._t("Y", 3, 3)
        self._link(x, y)
        self._link(y, c)
        self._calcular()
        self.assertAlmostEqual(x.total_float_days, 3.0, places=1)
        self.assertAlmostEqual(x.free_float_days, 0.0, places=1)
        self.assertAlmostEqual(y.free_float_days, 3.0, places=1)

    def test_start_to_start_with_lag_counts_working_days(self):
        """P (lun-mar) SS+2 → Q (1 día), y R (lun-vie) → Q: Q empieza el lunes 9 por R. P podría empezar hasta que
        su inicio + 2 llegue al lunes 9: mié, jue y vie = 3 días LABORABLES (no 5 naturales).

        La ruta A-B-C termina el martes 10, así que Q tiene 1 día de holgura propia y la TOTAL de P es 4: la libre
        (3) queda por debajo del tope de la total. Sin eso, un desfase mal medido (5 en vez de 3) quedaría oculto
        por el tope y esta prueba no podría fallar."""
        self._ruta()
        p, r, q = self._t("P", 2, 3), self._t("R", 2, 6), self._t("Q", 20, 20)
        self._link(p, q, tipo="ss", lag=2)
        self._link(r, q)
        self._calcular()
        self.assertEqual(q.planned_date_begin.day, 9)
        self.assertAlmostEqual(p.total_float_days, 4.0, places=1)
        self.assertAlmostEqual(p.free_float_days, 3.0, places=1)
        self.assertAlmostEqual(r.free_float_days, 0.0, places=1)

    def test_without_successors_it_runs_to_the_project_finish(self):
        _a, _b, _c = self._ruta()
        suelta = self._t("Suelta", 2, 2)
        self._calcular()
        self.assertAlmostEqual(suelta.free_float_days, 6.0, places=1, msg="mar 3 a mar 10")
        self.assertLessEqual(suelta.free_float_days, suelta.total_float_days)

    def test_with_negative_total_float_the_free_float_is_zero(self):
        """Una fecha límite que ya no se alcanza deja la holgura TOTAL negativa; la libre queda en 0, como la
        guarda MS Project."""
        a, b, c = self._ruta()
        c.write({"finish_deadline": "2026-11-06 17:00:00"})
        self._calcular()
        self.assertLess(c.total_float_days, 0)
        self.assertEqual(c.free_float_days, 0.0)

    def test_a_finished_task_and_a_summary_have_none(self):
        a, b, c = self._ruta()
        d = self._t("D", 2, 3, actual_start="2026-11-02 08:00:00", actual_finish="2026-11-03 17:00:00")
        self._link(d, c)
        paquete = self._t("Paquete", 2, 6)
        (a | b).write({"parent_id": paquete.id})
        self._calcular()
        self.assertEqual(d.free_float_days, 0.0)
        self.assertEqual(paquete.free_float_days, 0.0)

    def test_the_planner_and_the_critical_report_show_it(self):
        _a, _b, c = self._ruta()
        d = self._t("D", 2, 3)
        self._link(d, c)
        self._calcular()
        datos = self.T.with_user(self.pm).planner_data([("project_id", "=", self.proyecto.id)])
        self.assertAlmostEqual(next(t for t in datos["tasks"] if t["id"] == d.id)["free_float"], 3.0, places=1)
        rep = self.env["project.schedule.report"].with_user(self.pm).with_context(
            active_model="project.project", active_id=self.proyecto.id).create(
            {"report_type": "critical", "near_critical_days": 5})
        rep.action_run()
        self.assertAlmostEqual(rep.line_ids.filtered(lambda x: x.task_id == d).free_float, 3.0, places=1)
