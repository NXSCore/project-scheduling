# -*- coding: utf-8 -*-
"""El español llega al usuario (pertenencia de la clave)."""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools.translate import code_translations


@tagged("post_install", "-at_install")
class TestI18nRuntime(TransactionCase):

    def test_the_subschedule_speaks_spanish(self):
        self.env["res.lang"]._activate_lang("es_MX")
        self.env["ir.module.module"]._load_module_terms(["project_subschedule"], ["es_MX"], overwrite=True)
        es = self.env(context={"lang": "es_MX"})
        self.assertEqual(es["project.task"].fields_get(["effective_phase_id"])["effective_phase_id"]["string"],
                         "Subcronograma de etapa")
        self.assertIn("%s is not part of a stage subschedule.",
                      code_translations.get_python_translations("project_subschedule", "es_MX"))
