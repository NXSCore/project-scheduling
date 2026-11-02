# -*- coding: utf-8 -*-
"""La ruta crítica y los tipos de vínculo, en el Gantt de Enterprise."""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestDependencyGantt(TransactionCase):

    def test_the_gantt_paints_the_critical_path(self):
        """La vista Gantt colorea las tareas de la ruta crítica."""
        arch = self.env["project.task"].get_view(
            self.env.ref("project_enterprise.project_task_view_gantt").id,
            "gantt")["arch"]
        self.assertIn("is_critical", arch)
        self.assertIn("decoration-warning", arch)

    def test_the_gantt_popover_reaches_the_dependencies(self):
        """Dos clics desde la barra, sin bifurcar el componente de Enterprise."""
        arch = self.env["project.task"].get_view(
            self.env.ref("project_enterprise.project_task_view_gantt").id,
            "gantt")["arch"]
        self.assertIn("action_open_dependencies", arch)
