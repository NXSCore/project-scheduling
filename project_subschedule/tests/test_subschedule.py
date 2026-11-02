# -*- coding: utf-8 -*-
"""Subcronograma por etapa, genérico (solo requiere Proyecto)."""
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.project_subschedule.models.project_task import ProjectTask


@tagged("post_install", "-at_install")
class SubscheduleCase(TransactionCase):
    """Montaje sin pruebas: lo reutilizan los puentes."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, lang="en_US"))
        Etapa = cls.env["project.project.stage"]
        cls.diseno = Etapa.create({"name": "Design", "sequence": 10})
        cls.ejecucion = Etapa.create({"name": "Build", "sequence": 20})
        cls.usuario = cls.env["res.users"].create({
            "name": "sched_user", "login": "sched_user", "lang": "en_US",
            "groups_id": [(4, cls.env.ref("project.group_project_manager").id)]})
        cls.proyecto = cls.env["project.project"].create({"name": "Proyecto por etapas",
                                                          "stage_id": cls.diseno.id})
        Tarea = cls.env["project.task"]
        inicio = datetime(2040, 1, 5, 8, 0)
        cls.agrupadora = Tarea.create({"name": "Design", "project_id": cls.proyecto.id, "phase_id": cls.diseno.id,
                                       "planned_date_begin": inicio, "date_deadline": inicio + timedelta(days=30)})
        cls.hija = Tarea.create({"name": "Plans", "project_id": cls.proyecto.id, "parent_id": cls.agrupadora.id,
                                 "planned_date_begin": inicio, "date_deadline": inicio + timedelta(days=10)})
        cls.nieta = Tarea.create({"name": "Facades", "project_id": cls.proyecto.id, "parent_id": cls.hija.id})
        cls.suelta = Tarea.create({"name": "Unmarked", "project_id": cls.proyecto.id})


@tagged("post_install", "-at_install")
class TestSubschedule(SubscheduleCase):

    def test_subtasks_inherit_the_stage_of_their_grouping_task(self):
        self.assertEqual((self.hija.effective_phase_id, self.nieta.effective_phase_id), (self.diseno, self.diseno))
        self.assertFalse(self.suelta.effective_phase_id, "control: lo no marcado no tiene etapa")

    def test_a_subtask_cannot_belong_to_another_stage(self):
        with self.assertRaises(ValidationError):
            self.hija.phase_id = self.ejecucion

    def test_the_stage_button_opens_only_its_subschedule(self):
        accion = self.agrupadora.action_open_stage_subschedule()
        self.assertEqual(self.env["project.task"].search(accion["domain"]), self.agrupadora | self.hija | self.nieta)

    def test_while_the_stage_is_current_its_subschedule_is_free(self):
        self.hija.with_user(self.usuario).write({"date_deadline": datetime(2040, 1, 20, 18, 0)})
        self.env["project.task"].with_user(self.usuario).create({
            "name": "Sections", "project_id": self.proyecto.id, "parent_id": self.hija.id})

    def test_once_the_project_moves_on_the_subschedule_is_frozen(self):
        self.proyecto.stage_id = self.ejecucion
        Tarea = self.env["project.task"].with_user(self.usuario)
        with self.assertRaises(UserError):
            self.hija.with_user(self.usuario).write({"date_deadline": datetime(2040, 1, 25, 18, 0)})
        with self.assertRaises(UserError):
            Tarea.create({"name": "Late addition", "project_id": self.proyecto.id, "parent_id": self.hija.id})
        with self.assertRaises(UserError):
            self.nieta.with_user(self.usuario).unlink()
        # Control: lo no marcado sigue libre, y el sistema (sudo) no se frena.
        self.suelta.with_user(self.usuario).write({"name": "Unmarked, renamed"})
        self.hija.sudo().write({"date_deadline": datetime(2040, 1, 25, 18, 0)})

    def test_the_hook_reopens_it(self):
        self.proyecto.stage_id = self.ejecucion
        with patch.object(ProjectTask, "_phase_unlocked", lambda tareas: tareas):
            self.hija.with_user(self.usuario).write({"date_deadline": datetime(2040, 1, 26, 18, 0)})
