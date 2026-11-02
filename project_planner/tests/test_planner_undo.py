# -*- coding: utf-8 -*-
"""Deshacer y rehacer en el planificador.

Las pruebas arman los cambios como el cliente (`planner.js` `photo()` y
`diffPhotos()`): foto de `planner_data` antes y después de la acción.
"""
import json

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

CLAVES = ("name", "parent_id", "sequence", "start", "end", "duration", "milestone", "manual",
          "constraint", "constraint_date", "deadline")


@tagged("post_install", "-at_install")
class TestPlannerUndo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.proyecto = cls.env["project.project"].create({"name": "Deshacer", "allow_task_dependencies": True})
        T = cls.env["project.task"]
        pid = cls.proyecto.id
        cls.a = T.create({"name": "A", "project_id": pid, "sequence": 10,
                          "planned_date_begin": "2026-11-02 14:00:00", "date_deadline": "2026-11-06 23:00:00"})
        cls.b = T.create({"name": "B", "project_id": pid, "sequence": 20,
                          "planned_date_begin": "2026-11-09 14:00:00", "date_deadline": "2026-11-13 23:00:00"})
        cls.c = T.create({"name": "C", "project_id": pid, "sequence": 30,
                          "planned_date_begin": "2026-11-16 14:00:00", "date_deadline": "2026-11-20 23:00:00"})
        cls.dominio = [("project_id", "=", pid)]

    def _foto(self):
        datos = self.env["project.task"].planner_data(self.dominio)
        tareas = {t["id"]: {k: (t[k] if t[k] is not None else False) for k in CLAVES} for t in datos["tasks"]}
        for f in tareas.values():
            f["parent_id"] = f["parent_id"] or False
            f["constraint"] = f["constraint"] or "asap"
        enlaces = {"%s-%s" % (l["from"], l["to"]): {"type": l["type"], "lag": l["lag"], "elapsed": bool(l["elapsed"])}
                   for l in datos["links"]}
        return tareas, enlaces

    def _accion(self, fn):
        """Ejecuta `fn` y devuelve los cambios como los guarda el cliente."""
        t0, l0 = self._foto()
        fn()
        self.env.invalidate_all()
        t1, l1 = self._foto()
        cambios = {"tasks": {}, "links": {}}
        for k in set(t0) | set(t1):
            x, y = t0.get(k), t1.get(k)
            if json.dumps(x, sort_keys=True) != json.dumps(y, sort_keys=True):
                cambios["tasks"][str(k)] = {"before": x, "after": y}
        for k in set(l0) | set(l1):
            if l0.get(k) != l1.get(k):
                cambios["links"][k] = {"before": l0.get(k), "after": l1.get(k)}
        return cambios

    def _deshacer(self, cambios, direction="undo"):
        res = self.env["project.task"].planner_restore(cambios, direction=direction)
        self.env.invalidate_all()
        return res

    def test_moving_a_bar_is_undone_and_redone(self):
        antes = (self.a.planned_date_begin, self.a.date_deadline, self.a.duration_days)
        cambios = self._accion(lambda: self.a.write({
            "planned_date_begin": "2026-11-03 14:00:00", "date_deadline": "2026-11-09 23:00:00"}))
        despues = (self.a.planned_date_begin, self.a.date_deadline, self.a.duration_days)
        self.assertNotEqual(antes, despues)
        self.assertEqual(self._deshacer(cambios), {"conflicts": 0, "missing": 0})
        self.assertEqual((self.a.planned_date_begin, self.a.date_deadline, self.a.duration_days), antes)
        self._deshacer(cambios, "redo")
        self.assertEqual((self.a.planned_date_begin, self.a.date_deadline, self.a.duration_days), despues)

    def test_links_are_undone_created_changed_and_removed(self):
        Dep = self.env["project.dependency"]
        crear = self._accion(lambda: Dep.create({"predecessor_id": self.a.id, "successor_id": self.b.id,
                                                 "link_type": "ss", "lag_days": 2}))
        self._deshacer(crear)
        self.assertFalse(Dep.search([("successor_id", "=", self.b.id)]))
        self.assertFalse(self.b.depend_on_ids)
        self._deshacer(crear, "redo")
        fila = Dep.search([("successor_id", "=", self.b.id)])
        self.assertEqual((fila.link_type, fila.lag_days), ("ss", 2.0))
        cambiar = self._accion(lambda: fila.write({"link_type": "ff"}))
        self._deshacer(cambiar)
        self.assertEqual(fila.link_type, "ss")

    def test_undoing_an_insert_removes_the_new_task_and_restores_the_order(self):
        orden = [t.name for t in self.env["project.task"].search(self.dominio, order="sequence, id")]
        cambios = self._accion(lambda: self.env["project.task"].planner_structure("insert", self.b.id))
        self.assertEqual(self.env["project.task"].search_count(self.dominio), 4)
        self._deshacer(cambios)
        self.assertEqual(self.env["project.task"].search_count(self.dominio), 3)
        self.assertEqual([t.name for t in self.env["project.task"].search(self.dominio, order="sequence, id")], orden)

    def test_undoing_an_indent_restores_the_parent(self):
        cambios = self._accion(lambda: self.env["project.task"].planner_structure("indent", self.b.id))
        self.assertEqual(self.b.parent_id, self.a)
        self._deshacer(cambios)
        self.assertFalse(self.b.parent_id)

    def test_someone_elses_later_change_is_not_overwritten(self):
        cambios = self._accion(lambda: self.c.write({"name": "C cambiada"}))
        self.c.name = "C de otro usuario"
        res = self._deshacer(cambios)
        self.assertEqual(res["conflicts"], 1)
        self.assertEqual(self.c.name, "C de otro usuario")

    def test_a_deleted_task_is_reported_not_recreated(self):
        cambios = self._accion(lambda: self.a.write({"name": "A2"}))
        self.a.unlink()
        self.assertEqual(self._deshacer(cambios)["missing"], 1)

    def test_undo_respects_the_users_rights(self):
        lector = self.env["res.users"].create({
            "name": "Lector", "login": "lector_sched",
            "group_ids": [(6, 0, self.env.ref("base.group_user").ids)]})
        cambios = self._accion(lambda: self.a.write({"name": "A3"}))
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            self.env["project.task"].with_user(lector).planner_restore(cambios)
