# -*- coding: utf-8 -*-
"""Holgura y ruta crítica de un proyecto programado DESDE EL FIN, como MS Project.

Dos reglas de MS Project (ver `scheduler.slack`): en la pasada
temprana una manual se calcula como automática y toma el menor entre eso y su
posición; en la tardía, «terminar no antes de» se impone aunque el proyecto no
respete restricciones. Calendario lunes a viernes en UTC; el 2-nov-2026 es lunes y
el proyecto termina el viernes 20.
"""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestScheduleFromFinish(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cal = cls.env.company.resource_calendar_id
        cal.write({"tz": "UTC"})
        cal.global_leave_ids.unlink()
        cls.T = cls.env["project.task"]
        cls.pm = cls.env["res.users"].create({
            "name": "sched_pm", "login": "sched_pm", "groups_id": [(4, cls.env.ref("project.group_project_user").id)]})

    def setUp(self):
        super().setUp()
        self.proyecto = self.env["project.project"].create({
            "name": "Desde el fin", "schedule_from": "finish",
            "project_finish": "2026-11-20 17:00:00", "honor_constraints": False})

    def _t(self, nombre, ini, fin, **extra):
        return self.T.create({"name": nombre, "project_id": self.proyecto.id,
                              "planned_date_begin": f"2026-11-{ini:02d} 08:00:00",
                              "date_deadline": f"2026-11-{fin:02d} 17:00:00", **extra})

    def _link(self, a, b, tipo="fs"):
        self.env["project.dependency"].create({"predecessor_id": a.id, "successor_id": b.id, "link_type": tipo})

    def _run(self):
        r = self.T.scheduler_run([("project_id", "=", self.proyecto.id)], apply=True)
        self.T.invalidate_model()
        return r

    def _cadena(self):
        """A (3 días) → B (2 días): desde el fin quedan A 16-18 y B 19-20; el proyecto empieza el lunes 16."""
        a, b = self._t("A", 2, 4), self._t("B", 2, 3)
        self._link(a, b)
        return a, b

    def test_a_manual_task_without_predecessors_has_float_from_the_project_start(self):
        """La manual M está el miércoles 18. Su inicio temprano es el del proyecto (lunes 16): 2 días de holgura.
        No queda fija en las dos pasadas (eso le daría holgura 0 y la haría crítica)."""
        self._cadena()
        m = self._t("M", 18, 18, manually_scheduled=True)
        self._run()
        m = m.with_user(self.pm)
        self.assertEqual((m.planned_date_begin.day, m.date_deadline.day), (18, 18), "una manual no se mueve")
        self.assertAlmostEqual(m.total_float_days, 2.0, places=1)
        self.assertFalse(m.is_critical)

    def test_a_manual_task_never_starts_early_after_its_own_position(self):
        """N es manual y está el martes 17; depende de R, que ya TERMINÓ el miércoles 18 (fechas reales: nada la
        mueve). Calculada como automática, N empezaría el jueves 19, después de su posición: su inicio temprano es
        el 17 y su holgura 0, no −2."""
        self._cadena()
        r = self._t("R", 18, 18, actual_start="2026-11-18 08:00:00", actual_finish="2026-11-18 17:00:00")
        n = self._t("N", 17, 17, manually_scheduled=True)
        self._link(r, n)
        self._run()
        self.assertAlmostEqual(n.total_float_days, 0.0, places=1)

    def test_finish_no_earlier_than_wins_over_the_link(self):
        """C («terminar no antes del viernes 20») → D. El vínculo pondría a C el jueves 19; aunque el proyecto no
        respete restricciones, la restricción gana y se reporta el conflicto. El retraso lo paga su sucesora: D ya
        no cabe antes del fin del proyecto y su holgura es negativa."""
        c = self._t("C", 2, 2, constraint_type="fnet", constraint_date="2026-11-20 17:00:00")
        d = self._t("D", 2, 2)
        self._link(c, d)
        r = self._run()
        self.assertEqual(c.date_deadline.day, 20)
        self.assertIn(c.id, {x["id"] for x in r["conflicts"]})
        self.assertAlmostEqual(d.total_float_days, -1.0, places=1)
        self.assertTrue(d.is_critical)

    def test_start_no_earlier_than_does_not(self):
        """Control negativo: con «comenzar no antes del viernes 20», el vínculo sí gana (E queda el jueves 19)."""
        e = self._t("E", 2, 2, constraint_type="snet", constraint_date="2026-11-20 08:00:00")
        f = self._t("F", 2, 2)
        self._link(e, f)
        r = self._run()
        self.assertEqual(e.planned_date_begin.day, 19)
        self.assertIn(e.id, {x["id"] for x in r["conflicts"]})

    def test_from_the_start_a_manual_task_stays_fixed(self):
        """En un proyecto desde el INICIO nada cambia: la manual sigue fija en las dos pasadas (holgura 0)."""
        self.proyecto.write({"schedule_from": "start"})
        a, b = self._t("A", 2, 4), self._t("B", 5, 6)
        self._link(a, b)
        m = self._t("M", 4, 4, manually_scheduled=True)
        self._run()
        self.assertAlmostEqual(m.total_float_days, 0.0, places=1)
