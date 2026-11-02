# -*- coding: utf-8 -*-
"""El subcronograma de cada etapa del proyecto, dentro de su cronograma."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

#: Lo que define el plan: cambiarlo en una etapa cerrada es replanear lo que ya se cerró.
FROZEN_FIELDS = frozenset({"name", "planned_date_begin", "date_deadline", "parent_id", "depend_on_ids",
                           "phase_id", "project_id", "active"})


class ProjectTask(models.Model):
    _inherit = "project.task"

    phase_id = fields.Many2one(
        "project.project.stage", string="Project Stage", tracking=True, index=True, ondelete="restrict",
        help="Marks this task as the grouping task of a stage subschedule: its subtasks belong to that stage.")
    # Guardado: el candado y los filtros buscan por él, y la herencia baja por todo el árbol.
    effective_phase_id = fields.Many2one(
        "project.project.stage", string="Stage Subschedule", compute="_compute_effective_phase",
        store=True, recursive=True, index=True,
        help="The stage of this task: its own or the one of its nearest marked grouping task.")

    @api.depends("phase_id", "parent_id.effective_phase_id")
    def _compute_effective_phase(self):
        for tarea in self:
            tarea.effective_phase_id = tarea.phase_id or tarea.parent_id.effective_phase_id

    @api.constrains("phase_id", "parent_id")
    def _check_phase_coherent(self):
        """Una rama es de una sola etapa: la subtarea no declara una etapa distinta a la de su agrupadora."""
        for tarea in self:
            heredada = tarea.parent_id.effective_phase_id
            if tarea.phase_id and heredada and heredada != tarea.phase_id:
                raise ValidationError(_(
                    "%(task)s is inside the %(stage)s subschedule: it cannot belong to another stage.",
                    task=tarea.display_name, stage=heredada.name))

    # ------------------------------------------------------------------ el subcronograma
    def action_open_stage_subschedule(self):
        """El subcronograma de la etapa de esta tarea, en el Gantt EDT del cronograma."""
        self.ensure_one()
        etapa = self.effective_phase_id
        if not etapa:
            raise UserError(_("%s is not part of a stage subschedule.", self.display_name))
        return {
            "type": "ir.actions.act_window", "name": _("%(stage)s Schedule", stage=etapa.name),
            "res_model": "project.task", "view_mode": "gantt,list,form",
            "views": [(self.env.ref("project_gantt.project_task_view_gantt_wbs").id, "gantt"),
                      (False, "list"), (False, "form")],
            "domain": [("project_id", "=", self.project_id.id), ("effective_phase_id", "=", etapa.id)],
            # Subtareas visibles (sin esto el Gantt de Odoo las oculta) y numeración EDT.
            "context": {"default_project_id": self.project_id.id, "subtask_action": True,
                        "wbs_numbering": True, "gantt_start_date": fields.Date.context_today(self)},
        }

    # ------------------------------------------------------------------ el candado
    def _phase_closed(self):
        """Las de `self` cuya etapa ya quedó atrás: el proyecto está en una etapa posterior."""
        cerradas = self.browse()
        for tarea in self.filtered("effective_phase_id"):
            # sudo(): `stage_id` del proyecto es del grupo «etapas de proyecto»; decidir el candado no depende
            # de que quien edita vea la etapa.
            actual = tarea.project_id.sudo().stage_id
            if actual and actual.sequence > tarea.effective_phase_id.sequence:
                cerradas |= tarea
        return cerradas

    def _phase_unlocked(self):
        """Gancho: las de `self` que un permiso de cambio reabre. Aquí, ninguna (un puente lo extiende)."""
        return self.browse()

    def _check_phase_frozen(self):
        if self.env.su:
            return
        congeladas = self._phase_closed()
        congeladas -= congeladas._phase_unlocked()
        if congeladas:
            raise UserError(_(
                "The %(stage)s subschedule is closed: %(tasks)s can only change through an authorized change.",
                stage=congeladas[0].effective_phase_id.name, tasks=", ".join(congeladas.mapped("display_name"))))

    @api.model_create_multi
    def create(self, vals_list):
        padres = self.browse([v["parent_id"] for v in vals_list if v.get("parent_id")]).exists()
        padres._check_phase_frozen()
        return super().create(vals_list)

    def write(self, vals):
        if FROZEN_FIELDS & set(vals):
            self._check_phase_frozen()
        return super().write(vals)

    def unlink(self):
        self._check_phase_frozen()
        return super().unlink()
