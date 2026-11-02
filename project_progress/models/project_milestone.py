# -*- coding: utf-8 -*-
"""Las fotos de avance, ligadas a los hitos del cronograma para validarlas a la vista."""
from odoo import _, fields, models


class ProjectMilestone(models.Model):
    _inherit = "project.milestone"

    progress_photo_ids = fields.Many2many("ir.attachment", string="Progress Photos",
                                             compute="_compute_progress_photos",
                                             help="Images attached as progress evidence to the tasks of this milestone.")
    progress_photo_count = fields.Integer(string="Photos", compute="_compute_progress_photos")

    def _photo_domain(self):
        return [("res_model", "=", "project.task"), ("res_id", "in", self.task_ids.ids),
                ("mimetype", "=like", "image/%")]

    def _compute_progress_photos(self):
        """Sin `depends`: la evidencia se busca por el adjunto de cada tarea, no es un campo del hito."""
        for hito in self:
            fotos = self.env["ir.attachment"].search(hito._photo_domain()) if hito.task_ids else \
                self.env["ir.attachment"]
            hito.progress_photo_ids = fotos
            hito.progress_photo_count = len(fotos)

    def action_open_progress_photos(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Progress Photos · %s", self.name),
                "res_model": "ir.attachment", "view_mode": "kanban,list,form", "domain": self._photo_domain(),
                "context": {"create": False}}
