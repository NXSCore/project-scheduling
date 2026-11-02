# -*- coding: utf-8 -*-
from odoo import fields, models


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    # El planificador como tipo de vista de Odoo (selector de vistas,
    # búsqueda, filtros y favoritos), igual que `map` en web_map.
    type = fields.Selection(selection_add=[("planner", "Planner")], ondelete={"planner": "cascade"})

    def _get_view_info(self):
        return {"planner": {"icon": "fa fa-align-left"}} | super()._get_view_info()


class IrActionsActWindowView(models.Model):
    _inherit = "ir.actions.act_window.view"

    view_mode = fields.Selection(selection_add=[("planner", "Planner")], ondelete={"planner": "cascade"})
