# -*- coding: utf-8 -*-
"""La ruta critica, y por que el TIPO de vinculo la cambia.

Este es el test que justifica el modulo entero: la misma red, con los mismos
plazos, da rutas criticas DISTINTAS segun el tipo de vinculo. Con solo el
fin-a-inicio de Odoo, la respuesta seria siempre la misma y estaria mal.
"""
from datetime import datetime, timedelta

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCriticalPath(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # La holgura es en días LABORABLES del calendario del proyecto.
        # Calendario de lunes a viernes 8–12 y 13–17 en UTC, para que las
        # cuentas de la prueba no dependan del huso del servidor.
        cls.calendario = cls.env["resource.calendar"].create({"name": "L-V UTC", "tz": "UTC"})
        cls.proyecto = cls.env["project.project"].create({
            "name": "Red critica", "schedule_calendar_id": cls.calendario.id})
        cls.lunes = datetime(2026, 10, 5)  # lunes

    def _dia(self, n):
        """El n-ésimo día laborable desde el lunes de arranque."""
        d = self.lunes
        while n:
            d += timedelta(days=1)
            if d.weekday() < 5:
                n -= 1
        return d

    def _tarea(self, nombre, dia_inicio, dias, **extra):
        return self.env["project.task"].create({
            "name": nombre, "project_id": self.proyecto.id,
            "planned_date_begin": self._dia(dia_inicio).replace(hour=8),
            "date_deadline": self._dia(dia_inicio + dias - 1).replace(hour=17),
            **extra,
        })

    def _vinculo(self, pre, suc, tipo="fs", lag=0.0):
        return self.env["project.dependency"].create({
            "predecessor_id": pre.id, "successor_id": suc.id,
            "link_type": tipo, "lag_days": lag,
        })

    def test_the_longest_chain_is_the_critical_path(self):
        """A -> B -> D es mas larga que A -> C -> D: C tiene holgura."""
        a = self._tarea("A", 0, 2)
        b = self._tarea("B", 2, 6)
        c = self._tarea("C", 2, 2)
        d = self._tarea("D", 8, 2)
        self._vinculo(a, b)
        self._vinculo(a, c)
        self._vinculo(b, d)
        self._vinculo(c, d)
        self.assertTrue(a.is_critical)
        self.assertTrue(b.is_critical)
        self.assertTrue(d.is_critical)
        self.assertFalse(c.is_critical)
        self.assertAlmostEqual(c.total_float_days, 4.0, delta=0.1)

    def test_start_to_start_lets_two_tasks_run_together(self):
        """Con fin-a-inicio irian en fila y el proyecto duraria el doble.

        Es exactamente el error que Odoo comete por no guardar el tipo.
        """
        a = self._tarea("Arquitectura", 0, 10)
        b = self._tarea("Estructura", 0, 4)
        self._vinculo(a, b, tipo="ss")
        # B arranca con A, dura menos, y por tanto le sobran dias.
        self.assertTrue(a.is_critical)
        self.assertFalse(b.is_critical)
        self.assertAlmostEqual(b.total_float_days, 6.0, delta=0.1)

    def test_a_lag_pushes_the_successor_and_can_make_it_critical(self):
        a = self._tarea("A", 0, 2)
        b = self._tarea("B", 2, 2)
        sin_desfase = b.total_float_days
        self._vinculo(a, b, tipo="fs", lag=5.0)
        b.invalidate_recordset()
        self.assertGreater(b.early_finish, a.late_finish)
        self.assertEqual(sin_desfase, 0.0)

    def test_a_negative_lag_gives_slack_to_the_PREDECESSOR(self):
        """Un adelanto es tan real como la espera, y la holgura cae del lado
        que no es obvio.

        Si B puede arrancar 3 dias antes de que A termine, entonces A puede
        terminar 3 dias TARDE sin mover a B. La holgura es de A, no de B.
        Escribi este test al reves la primera vez y el motor me corrigio.

        B lleva «no comenzar antes del» su fecha. Sin eso, como en MS
        Project, el cálculo la adelanta 3 días y las dos quedan críticas.
        """
        a = self._tarea("A", 0, 10)
        b = self._tarea("B", 10, 10, constraint_type="snet", constraint_date=self._dia(10).replace(hour=8))
        self._vinculo(a, b, tipo="fs", lag=-3.0)
        a.invalidate_recordset()
        b.invalidate_recordset()
        self.assertAlmostEqual(a.total_float_days, 3.0, delta=0.1)
        self.assertAlmostEqual(b.total_float_days, 0.0, delta=0.1)

    def test_float_counts_working_days_not_weekends(self):
        """A termina el viernes y B empieza el lunes: sin holgura, aunque
        haya dos días naturales en medio (antes salían 2.6 días de holgura)."""
        a = self._tarea("A", 0, 5)
        b = self._tarea("B", 5, 5)
        self._vinculo(a, b)
        self.assertTrue(a.is_critical)
        self.assertAlmostEqual(a.total_float_days, 0.0, delta=0.01)

    def test_a_deadline_that_cannot_be_met_gives_negative_float(self):
        """La fecha límite de MS Project no mueve la tarea; si no se
        alcanza, la holgura sale negativa y la tarea (y su cadena) es crítica."""
        a = self._tarea("A", 0, 5)
        b = self._tarea("B", 5, 5, finish_deadline=self._dia(7).replace(hour=17))
        c = self._tarea("C", 0, 20)  # la más larga: sin la fecha límite, A y B tendrían holgura
        self._vinculo(a, b)
        for t in (a, b, c):
            t.invalidate_recordset()
        self.assertAlmostEqual(b.total_float_days, -2.0, delta=0.01)
        self.assertTrue(a.is_critical and b.is_critical)
        self.assertEqual(b.planned_date_begin, self._dia(5).replace(hour=8), "la fecha límite no mueve la tarea")

    def test_a_finished_task_is_never_critical(self):
        a = self._tarea("A", 0, 5, actual_start=self._dia(0).replace(hour=8),
                        actual_finish=self._dia(4).replace(hour=17))
        b = self._tarea("B", 5, 5)
        self._vinculo(a, b)
        self.assertFalse(a.is_critical)
        self.assertTrue(b.is_critical)

    def test_a_task_without_dates_stays_out_of_the_network(self):
        """Meterla arrastraria a sus sucesoras a una fecha inventada."""
        suelta = self.env["project.task"].create({
            "name": "Sin fechas", "project_id": self.proyecto.id,
        })
        self.assertFalse(suelta.is_critical)
        self.assertEqual(suelta.total_float_days, 0.0)

    def test_the_critical_path_can_be_filtered(self):
        a = self._tarea("A", 0, 2)
        b = self._tarea("B", 2, 6)
        c = self._tarea("C", 2, 2)
        d = self._tarea("D", 8, 2)
        for pre, suc in ((a, b), (a, c), (b, d), (c, d)):
            self._vinculo(pre, suc)
        criticas = self.env["project.task"].search([
            ("project_id", "=", self.proyecto.id), ("is_critical", "=", True)])
        self.assertIn(a, criticas)
        self.assertNotIn(c, criticas)

    def test_the_critical_path_is_on_screen(self):
        arch = self.env["project.task"].get_view(
            self.env.ref("project.view_task_form2").id, "form")["arch"]
        self.assertIn('name="is_critical"', arch)
        self.assertIn('name="predecessor_link_ids"', arch)
        self.assertIn('name="link_type"', arch)
