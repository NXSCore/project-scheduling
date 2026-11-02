# -*- coding: utf-8 -*-
"""El planificador a pantalla completa desde la ficha del proyecto."""
from odoo import _, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    def action_open_planner(self):
        """Abre la acción cliente `schedule_planner` con las tareas del proyecto.

        Funciona en Community: no depende de `web_gantt`. El proyecto viaja en
        `params.project_id` y también en `context.active_id`, porque al recargar
        la página Odoo reconstruye la acción cliente desde la URL y solo conserva
        `active_id`; sin él, el planificador perdería el proyecto y mostraría
        todas las tareas.
        """
        self.ensure_one()
        self.check_access("read")
        return {
            "type": "ir.actions.client",
            "tag": "schedule_planner",
            "name": _("Planner: %s", self.name),
            "params": {"project_id": self.id},
            "context": {"active_id": self.id, "active_model": "project.project",
                        "default_project_id": self.id},
        }
