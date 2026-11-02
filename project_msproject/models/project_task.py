# -*- coding: utf-8 -*-
from odoo import fields, models


class ProjectTask(models.Model):
    _inherit = "project.task"

    # El `<UID>` de la tarea en el archivo de MS Project. Con él una
    # segunda importación ACTUALIZA en vez de duplicar, y la exportación que
    # viene podrá devolver el mismo identificador.
    ms_uid = fields.Integer(
        string="MS Project UID", index=True, copy=False,
        help="Unique ID of the task in the Microsoft Project file it was imported from.")
