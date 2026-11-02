# -*- coding: utf-8 -*-
"""Los campos del cronograma se VEN, con su etiqueta."""
from lxml import etree

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestTaskViews(TransactionCase):

    def _arch(self, xmlid, tipo):
        return etree.fromstring(self.env["project.task"].get_view(self.env.ref(xmlid).id, tipo)["arch"])

    def test_nothing_of_ours_is_glued_to_the_planned_date(self):
        """En Odoo 19 la fecha vive en `div#date_deadline_and_recurring_task`
        (una línea): un campo insertado «después de `date_deadline`» queda
        dentro, pegado al rango de fechas y sin etiqueta. Corre después de instalar todo: cubre a cualquier módulo
        de la suite, no solo a este."""
        bloque = self._arch("project.view_task_form2", "form").xpath("//div[@id='date_deadline_and_recurring_task']")
        self.assertTrue(bloque, "el bloque de la fecha existe (si Odoo lo renombra, esta prueba debe seguirlo)")
        pegados = [f.get("name") for f in bloque[0].iter("field") if (f.get("name") or "").startswith("re_")]
        self.assertEqual(pegados, [])

    def test_the_schedule_page_shows_every_schedule_field(self):
        pagina = self._arch("project.view_task_form2", "form").xpath("//page[@name='dependencies']")
        self.assertTrue(pagina)
        campos = {f.get("name") for f in pagina[0].iter("field")}
        for campo in ("wbs_code", "duration_days", "is_milestone", "manually_scheduled", "constraint_type",
                      "constraint_date", "finish_deadline", "actual_start", "actual_finish",
                      "is_critical", "total_float_days", "predecessor_link_ids", "successor_link_ids"):
            self.assertIn(campo, campos)

    def test_the_task_list_leads_with_the_wbs(self):
        lista = self._arch("project.view_task_tree2", "list")
        nombres = [f.get("name") for f in lista.iter("field") if f.get("column_invisible") not in ("1", "True")]
        self.assertIn("wbs_code", nombres)
        self.assertLess(nombres.index("wbs_code"), nombres.index("name"))
        self.assertIn("duration_days", nombres)
