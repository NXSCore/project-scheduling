# -*- coding: utf-8 -*-
"""El Gantt por EDT al alcance de cualquier proyecto."""
from odoo import _, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    def _enable_task_dependencies(self):
        """Enciende el interruptor de dependencias si estaba apagado.

        Se llama al abrir el cronograma, no en una migración de una sola vez:
        un proyecto puede haberse creado por cualquier otro camino —importado,
        duplicado, dado de alta a mano en la app Proyecto— y el cronograma
        seguiría sin flechas. Comprobarlo al abrir cubre todos esos casos y
        cuesta una lectura.
        """
        sin_dependencias = self.filtered(lambda p: not p.allow_task_dependencies)
        if sin_dependencias:
            sin_dependencias.write({"allow_task_dependencies": True})
        # Los hitos del cronograma son los nativos (`project.
        # milestone`), que el Gantt de tareas dibuja como rombos en el
        # encabezado. Mismo interruptor por proyecto y mismo defecto si se deja
        # apagado. Encenderlo también da `project.group_project_milestone` a los
        # usuarios internos (`project.project._inverse_allow_milestones` →
        # `_check_project_group_with_field`): no hace falta tocar perfiles.
        sin_hitos = self.filtered(lambda p: not p.allow_milestones)
        if sin_hitos:
            sin_hitos.write({"allow_milestones": True})

    def action_open_wbs_gantt(self):
        """Las tareas del proyecto en el Gantt por paquete, con el código EDT y en orden EDT."""
        self.ensure_one()
        # Quien no puede VER el proyecto no llega más lejos: el sudo de abajo es
        # solo para los interruptores, no para saltarse el acceso.
        self.check_access("read")
        # sudo(): los dos interruptores (dependencias, hitos) son configuración del
        # proyecto que solo escribe su administrador; sin ellos el Gantt no dibuja
        # flechas ni rombos. El usuario que abre el Gantt no cambia nada más.
        self.sudo()._enable_task_dependencies()
        vista = self.env.ref("project_gantt.project_task_view_gantt_wbs")
        return {
            "type": "ir.actions.act_window",
            "name": _("Schedule: %s", self.name),
            "res_model": "project.task",
            "view_mode": "gantt,list,form",
            "views": [(vista.id, "gantt"), (False, "list"), (False, "form")],
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id, "wbs_numbering": True,
                        "group_by": ["wbs_root_id", "wbs_level2_id"]},
        }
