# -*- coding: utf-8 -*-
"""Reportar avance con su evidencia, en un solo acto.

El asistente existe porque el reporte pide DOS cosas a la vez —el porcentaje y
el documento que lo respalda— y un campo suelto en el formulario
solo puede pedir una.

La evidencia no es obligatoria para GUARDAR: se permite el reporte sin
archivo dejando constancia. El trabajo no se detiene porque falte un PDF, pero el hueco queda a la vista del PM en el
chatter y en la tarea (`progress_without_evidence`).
"""
from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..models.project_task import PROGRESS_SEAM as CTX_WITH_EVIDENCE


class ReProgressReportWizard(models.TransientModel):
    _name = "project.progress.report.wizard"
    _description = "Report physical progress with its evidence"

    task_id = fields.Many2one(
        "project.task", string="Task", required=True,
        default=lambda self: self.env.context.get("default_task_id"),
    )
    previous_progress = fields.Float(
        string="Reported So Far", related="task_id.physical_progress",
        readonly=True,
    )
    progress = fields.Float(string="Progress (%)", required=True)
    evidence = fields.Binary(string="Evidence", attachment=True)
    evidence_filename = fields.Char(string="File Name")
    note = fields.Text(string="Note")

    def action_report(self):
        self.ensure_one()
        if not 0.0 <= self.progress <= 100.0:
            raise UserError(_("Progress must be between 0 and 100."))
        # Retroceder es legítimo —una revisión puede echar atrás trabajo dado
        # por bueno— pero no en silencio: se dice en el chatter para que quien
        # lea el histórico no crea que fue un error de dedo.
        retrocede = self.progress < self.previous_progress
        adjunto = self.env["ir.attachment"]
        if self.evidence:
            adjunto = adjunto.create({
                "name": self.evidence_filename or _("Progress evidence"),
                "datas": self.evidence,
                "res_model": "project.task",
                "res_id": self.task_id.id,
            })
        cuerpo = Markup("<p>%s</p>") % _(
            "Physical progress reported: %(before)s%% → %(after)s%%.",
            before=round(self.previous_progress, 1), after=round(self.progress, 1))
        if retrocede:
            cuerpo += Markup("<p><b>%s</b></p>") % _(
                "This report LOWERS the progress previously recorded.")
        if not adjunto:
            # Sin evidencia se permite, pero se dice en voz alta.
            cuerpo += Markup("<p><b>%s</b></p>") % _(
                "Reported WITHOUT supporting evidence.")
        if self.note:
            cuerpo += Markup("<p>%s</p>") % self.note
        self.task_id.with_context(**{CTX_WITH_EVIDENCE: True}).write({
            "physical_progress": self.progress,
            "progress_reported_on": fields.Datetime.now(),
            "progress_without_evidence": not adjunto,
        })
        self.task_id.message_post(body=cuerpo, attachment_ids=adjunto.ids)
        return {"type": "ir.actions.act_window_close"}
