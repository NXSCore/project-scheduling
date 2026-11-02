# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import content_disposition, request


class PlannerReportController(http.Controller):

    @http.route("/project_planner_report/pdf/<int:wizard_id>", type="http", auth="user")
    def planner_report_pdf(self, wizard_id):
        """El PDF del asistente `wizard_id`. No confía en el id de la URL: la
        regla `project_planner_report_wizard_rule_own` deja ver solo los
        asistentes propios; un id ajeno da 404."""
        wizard = request.env["project.planner.report.wizard"].search([("id", "=", wizard_id)])
        if not wizard:
            raise request.not_found()
        pdf, nombre = wizard._render_pdf()
        return request.make_response(pdf, headers=[
            ("Content-Type", "application/pdf"),
            ("Content-Length", str(len(pdf))),
            ("Content-Disposition", content_disposition(nombre)),
        ])
