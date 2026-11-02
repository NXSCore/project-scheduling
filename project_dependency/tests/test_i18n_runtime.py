# -*- coding: utf-8 -*-
"""La traducción es_MX llega al usuario (se comprueba corriendo)."""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools.translate import code_translations


@tagged("post_install", "-at_install")
class TestI18nRuntime(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("es_MX")
        cls.env["ir.module.module"]._load_module_terms(["project_dependency"], ["es_MX"], overwrite=True)

    def test_field_labels_and_help(self):
        campos = self.env["project.task"].with_context(lang="es_MX").fields_get(["finish_deadline", "total_float_days"])
        self.assertEqual(campos["finish_deadline"]["string"], "Fecha límite de término")
        self.assertIn("Días laborables", campos["total_float_days"]["help"])

    def test_selection_labels(self):
        etiquetas = dict(self.env["project.dependency"].with_context(lang="es_MX")._fields["link_type"]._description_selection(
            self.env(context={"lang": "es_MX"})))
        self.assertEqual(etiquetas["fs"], "Fin a inicio (FS)")

    def test_driver_and_health_messages(self):
        """Pertenencia de la clave, no «¿cambió el valor?»."""
        codigo = code_translations.get_python_translations("project_dependency", "es_MX")
        for clave in ("Predecessor: %s", "Predecessors (%(count)s): %(names)s", "Date constraint: %s",
                      "Its own start date", "Its own duration or the calendar", "Reason not established",
                      "Summary: follows its subtasks", "Why it moves", "Schedule Health Check",
                      "Logic: tasks missing a predecessor or a successor", "Critical Path Length Index (CPLI)",
                      "Baseline Execution Index (BEI)"):
            self.assertIn(clave, codigo, clave)

    def test_health_model_and_selection(self):
        es = self.env(context={"lang": "es_MX"})
        modelo = es["ir.model"]._get("project.schedule.health")
        self.assertEqual(modelo.with_context(lang="es_MX").name, "Salud del cronograma")
        etiquetas = dict(es["project.schedule.health.line"]._fields["result"]._description_selection(es))
        self.assertEqual(etiquetas["pass"], "Cumple")
        self.assertEqual(etiquetas["na"], "No aplica")
