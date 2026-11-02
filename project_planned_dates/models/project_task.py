# -*- coding: utf-8 -*-
"""La fecha de inicio planeada de la tarea, en Community.

Cada línea replica la de `project_enterprise/models/project_task.py` (Odoo 18,
líneas 28 y 43-45; en 18 el campo NO lleva copy=False) a propósito: si Enterprise se instala encima, el ORM funde
las dos declaraciones del campo y de la restricción en una sola, y la columna
de la base no cambia.
"""
from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = "project.task"

    planned_date_begin = fields.Datetime("Start date", tracking=True)

    _sql_constraints = [
        ("planned_dates_check", "CHECK ((planned_date_begin <= date_deadline))", "The planned start date must be before the planned end date."),
    ]

    @api.onchange("date_deadline", "planned_date_begin")
    def _onchange_planned_dates(self):
        # Mismo criterio que Enterprise (`_onchange_planned_dates`): un inicio
        # sin fin no es un rango, y el widget de rango lo dejaría a medias.
        if not self.date_deadline:
            self.planned_date_begin = False
