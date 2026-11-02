# -*- coding: utf-8 -*-
from datetime import datetime

from psycopg2 import IntegrityError

from odoo.tests import Form, new_test_user, tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestPlannedDates(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Planned dates"})
        cls.user = new_test_user(cls.env, login="pd_user", groups="project.group_project_user")

    def test_a_task_keeps_its_planned_range(self):
        task = self.env["project.task"].create({
            "name": "T", "project_id": self.project.id,
            "planned_date_begin": datetime(2026, 1, 5, 8), "date_deadline": datetime(2026, 1, 9, 17),
        })
        self.assertEqual(task.planned_date_begin, datetime(2026, 1, 5, 8))

    def test_the_start_cannot_come_after_the_end(self):
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.env["project.task"].create({
                    "name": "T", "project_id": self.project.id,
                    "planned_date_begin": datetime(2026, 1, 9), "date_deadline": datetime(2026, 1, 5),
                })

    def test_clearing_the_end_clears_the_start(self):
        task = self.env["project.task"].create({
            "name": "T", "project_id": self.project.id,
            "planned_date_begin": datetime(2026, 1, 5), "date_deadline": datetime(2026, 1, 9),
        })
        with Form(task) as form:
            form.date_deadline = False
        self.assertFalse(task.planned_date_begin)

    def test_a_project_user_can_plan_a_task(self):
        # Escritura real con el usuario, no browse(): comprueba ACL del campo.
        task = self.env["project.task"].with_user(self.user).create({
            "name": "T", "project_id": self.project.id, "user_ids": [(4, self.user.id)],
        })
        task.write({"planned_date_begin": datetime(2026, 2, 2), "date_deadline": datetime(2026, 2, 6)})
        self.assertEqual(task.planned_date_begin, datetime(2026, 2, 2))

    def test_the_form_shows_a_date_range(self):
        arch = self.env["project.task"].get_view(self.env.ref("project.view_task_form2").id, "form")["arch"]
        self.assertIn("start_date_field", arch)
        self.assertIn('name="planned_date_begin"', arch)

    def test_it_speaks_spanish(self):
        """La etiqueta y el mensaje de la restricción cargan del .po de ESTE módulo."""
        self.env["res.lang"]._activate_lang("es_MX")
        self.env["ir.module.module"].search([("name", "=", "project_planned_dates")])._update_translations(["es_MX"])
        campo = self.env["project.task"].with_context(lang="es_MX").fields_get(["planned_date_begin"])
        self.assertEqual(campo["planned_date_begin"]["string"], "Fecha de inicio")
        restriccion = self.env.ref("project_planned_dates.constraint_project_task_planned_dates_check")
        # Pertenencia de la clave del idioma, no «¿cambió el valor?».
        self.assertIn("es_MX", restriccion._fields["message"]._get_stored_translations(restriccion))
