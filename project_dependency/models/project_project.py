# -*- coding: utf-8 -*-
from odoo import fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    # Cada proyecto calcula con SU calendario —el de la
    # compañía por omisión—; al importar de MS Project se puede crear uno con
    # la semana laboral y los feriados del archivo.
    schedule_calendar_id = fields.Many2one(
        "resource.calendar", string="Working Calendar",
        default=lambda self: self.env.company.resource_calendar_id,
        help="Working days and holidays used to calculate this project's schedule and task durations. "
             "Empty means the company calendar.")

    def _work_calendar_record(self):
        self.ensure_one()
        return self.schedule_calendar_id or self.company_id.resource_calendar_id or self.env.company.resource_calendar_id

    # Los «minutos por día» de MS Project: cuántos minutos de trabajo es
    # un día de DURACIÓN (480 = 8 h), sin importar el horario del calendario.
    # La importación lo toma de `<MinutesPerDay>`.
    minutes_per_day = fields.Integer(
        string="Minutes per Day", default=480,
        help="Working minutes in one day of task duration, as Microsoft Project's 'Hours per day' (480 = 8 hours).")

    # Opciones de programación de MS Project (se importan del XML).
    schedule_from = fields.Selection(
        [("start", "Project start date"), ("finish", "Project finish date")],
        string="Schedule From", default="start", required=True,
        help="From the finish date, every automatic task goes to its latest dates, "
             "calculated backwards from its successors and the project finish, as in Microsoft Project.")
    project_finish = fields.Datetime(
        string="Project Finish", help="Finish date the schedule is calculated backwards from (Schedule From: finish).")
    honor_constraints = fields.Boolean(
        string="Tasks Always Honor Their Constraints", default=True,
        help="On, a 'no later than' constraint wins over a link; off, the link wins. Both report the conflict.")
