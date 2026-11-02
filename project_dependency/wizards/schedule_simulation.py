# -*- coding: utf-8 -*-
"""El PM mueve fechas y duraciones en una simulación y ve el impacto antes de reprogramar."""
from markupsafe import Markup

from odoo import api, fields, models
from odoo.tools import format_datetime


class ReScheduleSimulation(models.TransientModel):
    _name = "project.schedule.simulation"
    _description = "Schedule Simulation"

    project_id = fields.Many2one("project.project", string="Schedule", required=True,
                                 default=lambda self: self._default_project())
    line_ids = fields.One2many("project.schedule.simulation.line", "simulation_id", string="Changes to Simulate")
    finish_before = fields.Datetime(string="Current Finish", readonly=True)
    finish_after = fields.Datetime(string="Simulated Finish", readonly=True)
    delay_days = fields.Integer(string="Impact on Finish (days)", readonly=True,
                                help="Calendar days the delivery date moves; negative when it advances.")
    result_html = fields.Html(string="Result", readonly=True, sanitize=False)

    @api.model
    def _default_project(self):
        if self.env.context.get("active_model") == "project.project":
            return self.env.context.get("active_id")
        return False

    def action_simulate(self):
        self.ensure_one()
        cambios = {linea.task_id.id: {"start": linea.new_start, "duration": linea.new_duration}
                   for linea in self.line_ids if linea.task_id}
        resultado = self.env["project.task"].scheduler_simulate(self.project_id, cambios)
        antes, despues = resultado["finish_before"], resultado["finish_after"]
        criticas = set(resultado["critical_ids"])
        filas = Markup("").join(Markup(
            "<tr class='%s'><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>") % (
            "table-danger" if c["task"].id in criticas else "", c["task"].display_name,
            format_datetime(self.env, c["old_end"]) if c["old_end"] else "",
            format_datetime(self.env, c["new_end"]) if c["new_end"] else "",
            c.get("reason") or "",
            self.env._("Critical") if c["task"].id in criticas else "") for c in resultado["changes"])
        nombres = self.env["project.task"].browse(sorted(criticas)).mapped("display_name")
        self.write({
            "finish_before": antes, "finish_after": despues,
            "delay_days": (despues - antes).days if antes and despues else 0,
            "result_html": Markup("<p><strong>%s</strong> %s</p><table class='table table-sm'><thead><tr><th>%s</th>"
                                  "<th>%s</th><th>%s</th><th>%s</th><th></th></tr></thead><tbody>%s</tbody></table>") % (
                self.env._("New critical path:"), ", ".join(nombres) or "—", self.env._("Task"),
                self.env._("Current Finish"), self.env._("Simulated Finish"), self.env._("Why it moves"), filas),
        })
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new", "name": self.env._("Schedule Simulation")}


class ReScheduleSimulationLine(models.TransientModel):
    _name = "project.schedule.simulation.line"
    _description = "Schedule Simulation Change"

    simulation_id = fields.Many2one("project.schedule.simulation", string="Simulation", required=True, ondelete="cascade")
    project_id = fields.Many2one(related="simulation_id.project_id", string="Schedule")
    task_id = fields.Many2one("project.task", string="Task", required=True,
                              domain="[('project_id', '=', project_id)]")
    current_start = fields.Datetime(related="task_id.planned_date_begin", string="Current Start")
    current_duration = fields.Float(related="task_id.duration_days", string="Current Duration (days)")
    new_start = fields.Datetime(string="Simulated Start")
    new_duration = fields.Float(string="Simulated Duration (days)")
