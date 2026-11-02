# -*- coding: utf-8 -*-
"""Los cuatro tipos de vinculo, el desfase, y la convivencia con Odoo."""
from datetime import datetime, timedelta

from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestDependencyTypes(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.proyecto = cls.env["project.project"].create({"name": "Red de prueba"})
        cls.inicio = datetime(2026, 10, 1, 8, 0)

    def _tarea(self, nombre, dia_inicio, dias):
        return self.env["project.task"].create({
            "name": nombre, "project_id": self.proyecto.id,
            "planned_date_begin": self.inicio + timedelta(days=dia_inicio),
            "date_deadline": self.inicio + timedelta(days=dia_inicio + dias),
        })

    def _vinculo(self, pre, suc, tipo="fs", lag=0.0):
        return self.env["project.dependency"].create({
            "predecessor_id": pre.id, "successor_id": suc.id,
            "link_type": tipo, "lag_days": lag,
        })

    def test_a_task_cannot_depend_on_itself(self):
        a = self._tarea("A", 0, 5)
        with self.assertRaises(ValidationError):
            self._vinculo(a, a)

    def test_a_loop_is_refused_even_three_hops_away(self):
        """Mirar solo el vinculo nuevo no basta: el ciclo se cierra lejos."""
        a, b, c = self._tarea("A", 0, 2), self._tarea("B", 2, 2), self._tarea("C", 4, 2)
        self._vinculo(a, b)
        self._vinculo(b, c)
        with self.assertRaises(ValidationError):
            self._vinculo(c, a)

    def test_a_plain_finish_to_start_reaches_the_native_gantt(self):
        """Para que Odoo siga dibujando la flecha y bloqueando la tarea."""
        a, b = self._tarea("A", 0, 2), self._tarea("B", 2, 2)
        self._vinculo(a, b)
        self.assertIn(a, b.depend_on_ids)

    def test_the_other_types_do_not_pretend_to_be_finish_to_start(self):
        """Un diagrama que miente es peor que uno incompleto."""
        a, b = self._tarea("A", 0, 2), self._tarea("B", 0, 2)
        self._vinculo(a, b, tipo="ss")
        self.assertNotIn(a, b.depend_on_ids)

    def test_adding_a_lag_pulls_it_out_of_the_native_field(self):
        a, b = self._tarea("A", 0, 2), self._tarea("B", 2, 2)
        vinculo = self._vinculo(a, b)
        self.assertIn(a, b.depend_on_ids)
        vinculo.lag_days = 3.0
        self.assertNotIn(a, b.depend_on_ids)

    def test_the_same_pair_cannot_be_linked_twice(self):
        a, b = self._tarea("A", 0, 2), self._tarea("B", 2, 2)
        self._vinculo(a, b)
        # La excepción exacta del índice único, no `Exception`: con `Exception` la prueba
        # pasaba con cualquier error, incluido uno que no tuviera nada que ver con el par.
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self._vinculo(a, b, tipo="ss")

    def test_drawing_in_the_gantt_creates_a_typed_link(self):
        """Una dependencia dibujada en el Gantt (`depend_on_ids`) crea su vínculo
        tipado, para que el CPM la vea."""
        a, b = self._tarea("A", 0, 2), self._tarea("B", 2, 2)
        b.depend_on_ids = [(4, a.id)]
        vinculo = self.env["project.dependency"].search([
            ("predecessor_id", "=", a.id), ("successor_id", "=", b.id)])
        self.assertTrue(vinculo, "arrastrar en el Gantt no creo el vinculo tipado")
        self.assertEqual(vinculo.link_type, "fs")
        self.assertEqual(vinculo.lag_days, 0.0)

    def test_removing_the_arrow_removes_the_plain_link(self):
        a, b = self._tarea("A", 0, 2), self._tarea("B", 2, 2)
        b.depend_on_ids = [(4, a.id)]
        b.depend_on_ids = [(3, a.id)]
        self.assertFalse(self.env["project.dependency"].search([
            ("predecessor_id", "=", a.id), ("successor_id", "=", b.id)]))

    def test_removing_the_arrow_does_not_touch_a_typed_link(self):
        """Un inicio-a-inicio no se dibuja: su ausencia no significa que se quito."""
        a, b = self._tarea("A", 0, 2), self._tarea("B", 0, 2)
        vinculo = self._vinculo(a, b, tipo="ss")
        b.depend_on_ids = [(3, a.id)]
        self.assertTrue(vinculo.exists())

    def test_drawing_it_reaches_the_critical_path(self):
        """La prueba de que el hueco estaba: sin vinculo, no hay red que calcular."""
        a = self._tarea("A", 0, 2)
        b = self._tarea("B", 2, 10)
        c = self._tarea("C", 2, 2)
        d = self._tarea("D", 12, 2)
        for pre, suc in ((a, b), (a, c), (b, d), (c, d)):
            suc.depend_on_ids = [(4, pre.id)]
        for t in (a, b, c, d):
            t.invalidate_recordset()
        self.assertTrue(b.is_critical)
        self.assertFalse(c.is_critical)

    def test_the_action_shows_both_directions(self):
        a, b, c = self._tarea("A", 0, 2), self._tarea("B", 2, 2), self._tarea("C", 4, 2)
        self._vinculo(a, b)
        self._vinculo(b, c)
        accion = b.action_open_dependencies()
        encontrados = self.env["project.dependency"].search(accion["domain"])
        self.assertEqual(len(encontrados), 2, "faltaba una de las dos direcciones")
