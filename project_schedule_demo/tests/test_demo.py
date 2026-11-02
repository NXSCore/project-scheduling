# -*- coding: utf-8 -*-
"""La demo enseña lo que promete: los cuatro tipos de vínculo, hitos y ruta crítica."""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestScheduleDemo(TransactionCase):

    def test_the_demo_shows_every_link_type(self):
        project = self.env.ref("project_schedule_demo.demo_project")
        tipos = set(self.env["project.dependency"].search([("project_id", "=", project.id)]).mapped("link_type"))
        self.assertEqual(tipos, {"fs", "ss", "ff", "sf"})

    def test_the_demo_has_milestones_and_a_critical_path(self):
        project = self.env.ref("project_schedule_demo.demo_project")
        tareas = self.env["project.task"].search([("project_id", "=", project.id)])
        self.assertEqual(len(tareas.filtered("is_milestone")), 2)
        self.assertTrue(tareas.filtered("is_critical"), "la demo debe enseñar una ruta crítica")
        self.assertIn(self.env.ref("project_schedule_demo.t_handover"), tareas.filtered("is_critical"))
