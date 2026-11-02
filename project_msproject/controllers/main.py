# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import content_disposition, request


class MspdiExportController(http.Controller):

    @http.route("/project_msproject/export/<int:project_id>", type="http", auth="user")
    def mspdi_export(self, project_id):
        """El XML MSPDI del proyecto. Solo LEE: busca el proyecto con los
        permisos de quien pide (un id ajeno o sin acceso da 404) y las tareas
        salen igual, sin `sudo()`. Los UID nuevos los asigna antes el botón."""
        proyecto = request.env["project.project"].search([("id", "=", project_id)])
        if not proyecto:
            raise request.not_found()
        xml = proyecto._mspdi_export()
        return request.make_response(xml, headers=[
            ("Content-Type", "application/xml; charset=utf-8"),
            ("Content-Length", str(len(xml))),
            ("Content-Disposition", content_disposition("%s.xml" % proyecto.name.replace("/", "-"))),
        ])
