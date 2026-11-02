# -*- coding: utf-8 -*-
"""El avance físico con su evidencia, en un proyecto CUALQUIERA."""
import base64
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

from ..models.project_task import PROGRESS_SEAM


@tagged("post_install", "-at_install")
class TestProgress(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Idioma fijo: estas aserciones comparan el TEXTO fuente (inglés) y con es_MX
        # activo en la base salían traducidas; la prueba de i18n va aparte.
        cls.env = cls.env(context=dict(cls.env.context, lang="en_US"))
        cls.ahora = fields.Datetime.now()
        cls.proyecto = cls.env["project.project"].create({"name": "Proyecto genérico"})
        cls.usuario = new_test_user(cls.env, login="sched_user", groups="project.group_project_user")
        cls.tarea = cls.env["project.task"].create({
            "name": "Actividad", "project_id": cls.proyecto.id, "user_ids": [(6, 0, cls.usuario.ids)],
            "planned_date_begin": cls.ahora - timedelta(days=5), "date_deadline": cls.ahora + timedelta(days=5)})

    def _reportar(self, avance, evidencia=None, usuario=None):
        valores = {"task_id": self.tarea.id, "progress": avance}
        if evidencia:
            valores.update(evidence=base64.b64encode(evidencia), evidence_filename="bitacora.pdf")
        asistente = self.env["project.progress.report.wizard"].with_user(usuario or self.usuario).create(valores)
        asistente.action_report()

    def test_expected_progress_and_gap_follow_the_dates(self):
        self.assertAlmostEqual(self.tarea.expected_progress, 50.0, delta=1.0)
        self.assertAlmostEqual(self.tarea.progress_gap, -50.0, delta=1.0)

    def test_progress_is_written_only_through_the_wizard(self):
        """Ni el formulario ni RPC escriben el avance a secas."""
        with self.assertRaisesRegex(UserError, "Report Progress"):
            self.tarea.with_user(self.usuario).write({"physical_progress": 30.0})
        with self.assertRaises(ValidationError):
            self.tarea.with_context(**{PROGRESS_SEAM: True}).physical_progress = 130.0

    def test_a_report_with_evidence_and_one_without(self):
        self._reportar(40.0, evidencia=b"%PDF bitacora")
        self.assertEqual((self.tarea.physical_progress, self.tarea.progress_without_evidence), (40.0, False))
        self.assertTrue(self.tarea.message_ids[:1].attachment_ids)
        self._reportar(45.0)
        self.assertTrue(self.tarea.progress_without_evidence)
        self.assertIn("WITHOUT supporting evidence", str(self.tarea.message_ids[:1].body))

    def test_stale_progress_is_flagged_and_reminded(self):
        self._reportar(20.0)
        self.tarea.progress_reported_on = self.ahora - timedelta(days=9)
        self.assertTrue(self.tarea.progress_is_stale)
        self.assertIn(self.tarea, self.env["project.task"].search([("progress_is_stale", "=", True)]))
        # Se fija el gancho en «sin filtro»: una extensión instalada lo puede acotar, y
        # aquí se prueba el comportamiento GENÉRICO, con cualquier extensión o sin ninguna.
        with patch.object(self.registry["project.task"], "_progress_reminder_domain", lambda self: []):
            self.env["project.task"]._cron_remind_weekly_progress()
        aviso = self.env["mail.message"].search([("model", "=", "project.task"), ("res_id", "=", self.tarea.id),
                                                 ("subject", "ilike", "Weekly progress due")])
        self.assertTrue(aviso, "sin filtro de extensión, el recordatorio corre en cualquier proyecto")

    def test_an_outsider_cannot_report(self):
        portal = new_test_user(self.env, login="sched_portal", groups="base.group_portal")
        with self.assertRaises(AccessError):
            self._reportar(10.0, usuario=portal)

    def test_it_speaks_spanish(self):
        self.env["res.lang"]._activate_lang("es_MX")
        self.env["ir.module.module"].search([("name", "=", "project_progress")])._update_translations(["es_MX"])
        campos = self.env["project.task"].with_context(lang="es_MX").fields_get(["physical_progress"])
        self.assertEqual(campos["physical_progress"]["string"], "Avance físico")

    def test_the_milestone_shows_the_progress_photos_of_its_tasks(self):
        """Las fotos de avance (no los PDF) de las tareas del hito, a la vista desde el hito."""
        self.proyecto.allow_milestones = True
        hito = self.env["project.milestone"].create({"name": "Losa N3", "project_id": self.proyecto.id})
        self.tarea.milestone_id = hito
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
        asistente = self.env["project.progress.report.wizard"].with_user(self.usuario).create({
            "task_id": self.tarea.id, "progress": 30.0, "evidence": base64.b64encode(png), "evidence_filename": "colado.png"})
        asistente.action_report()
        self._reportar(40.0, evidencia=b"%PDF-1.4 bitacora")
        hito.invalidate_recordset(["progress_photo_ids", "progress_photo_count"])
        self.assertEqual(hito.progress_photo_count, 1, "la foto sí, el PDF no")
        self.assertEqual(hito.progress_photo_ids.name, "colado.png")
        accion = hito.action_open_progress_photos()
        self.assertEqual(self.env["ir.attachment"].search_count(accion["domain"]), 1)
