# -*- coding: utf-8 -*-
"""El Gantt por EDT y los festivos, en un proyecto CUALQUIERA.

Se prueban sobre un `project.project` sin extensiones.
"""
import re

from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestWbsGantt(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Idioma fijo: estas aserciones comparan el TEXTO fuente (inglés) y con es_MX
        # activo en la base salían traducidas; la prueba de i18n va aparte.
        cls.env = cls.env(context=dict(cls.env.context, lang="en_US"))
        cls.proyecto = cls.env["project.project"].create({"name": "Proyecto genérico"})
        cls.Tarea = cls.env["project.task"]

    def _rama(self, sufijo):
        T, p = self.Tarea, self.proyecto.id
        paquete = T.create({"name": "Paquete " + sufijo, "project_id": p})
        hoja = T.create({"name": "Hoja " + sufijo, "project_id": p, "parent_id": paquete.id})
        rama = T.create({"name": "Rama " + sufijo, "project_id": p, "parent_id": paquete.id})
        a = T.create({"name": "A " + sufijo, "project_id": p, "parent_id": rama.id})
        b = T.create({"name": "B " + sufijo, "project_id": p, "parent_id": rama.id})
        return paquete, hoja, rama, a, b

    def test_every_task_knows_its_package_and_level(self):
        paquete, hoja, rama, a, _b = self._rama("(niveles)")
        self.assertEqual((paquete | hoja | rama | a).mapped("wbs_root_id"), paquete)
        self.assertEqual((paquete.wbs_depth, hoja.wbs_depth, a.wbs_depth), (1, 2, 3))
        self.assertFalse(hoja.wbs_level2_id, "lo que no se desglosa va al grupo vacío")
        self.assertEqual((rama.wbs_level2_id, a.wbs_level2_id), (rama, rama))
        campo = self.Tarea.fields_get(["wbs_level2_id"])["wbs_level2_id"]
        self.assertEqual(campo.get("falsy_value_label"), "Tasks without breakdown")

    def test_the_wbs_code_shows_only_where_it_is_asked_for(self):
        _paquete, hoja, *_ = self._rama("(nombre)")
        self.assertEqual(hoja.display_name, "Hoja (nombre)")
        self.assertEqual(hoja.with_context(wbs_numbering=True).display_name, "%s Hoja (nombre)" % hoja.wbs_code)

    def test_the_gantt_comes_in_wbs_order_with_summary_rows(self):
        paquete, hoja, rama, a, b = self._rama("(orden)")
        b.sequence = 1
        datos = self.Tarea.with_context(wbs_numbering=True).get_gantt_data(
            [("wbs_root_id", "=", paquete.id)], ["wbs_root_id", "wbs_level2_id"], {"display_name": {}})
        self.assertEqual(datos["groups"][0]["__record_ids"], [paquete.id, hoja.id])
        self.assertEqual(datos["groups"][1]["__record_ids"], [rama.id, b.id, a.id])
        nombres = {r["id"]: r["display_name"] for r in datos["records"]}
        self.assertIn("(summary)", nombres[rama.id])

    def test_any_project_opens_its_wbs_gantt(self):
        """El botón del proyecto: Gantt por paquete, ruta crítica, escala semana y código EDT."""
        accion = self.proyecto.action_open_wbs_gantt()
        self.assertTrue(self.proyecto.allow_task_dependencies, "sin dependencias no hay flechas")
        vista_id, tipo = accion["views"][0]
        self.assertEqual(tipo, "gantt")
        arch = self.Tarea.get_view(vista_id, "gantt")["arch"]
        etiqueta = re.search(r"<gantt[^>]*>", arch).group(0)
        for atributo in ('default_group_by="wbs_root_id,wbs_level2_id"', 'color="critical_color"',
                         'default_scale="week"'):
            self.assertIn(atributo, etiqueta)
        self.assertIn('name="wbs_code"', arch)
        self.assertTrue(accion["context"]["wbs_numbering"])

    def test_a_project_user_reaches_it_and_an_outsider_does_not(self):
        usuario = new_test_user(self.env, login="sched_user", groups="project.group_project_user")
        self.assertEqual(self.proyecto.with_user(usuario).action_open_wbs_gantt()["res_model"], "project.task")
        portal = new_test_user(self.env, login="sched_portal", groups="base.group_portal")
        with self.assertRaises(AccessError):
            self.proyecto.with_user(portal).action_open_wbs_gantt()

    def test_show_subtasks_starts_on_everywhere(self):
        archivos = [f["url"] for f in self.env["ir.qweb"]._get_asset_bundle("web.assets_backend").files]
        self.assertIn("/project_gantt/static/src/show_subtasks_default.js", archivos)

    def test_it_speaks_spanish(self):
        """Las etiquetas del módulo cargan en es_MX."""
        self.env["res.lang"]._activate_lang("es_MX")
        self.env["ir.module.module"].search([("name", "=", "project_gantt")])._update_translations(["es_MX"])
        campos = self.env["project.task"].with_context(lang="es_MX").fields_get(["wbs_root_id", "wbs_level2_id"])
        self.assertEqual(campos["wbs_root_id"]["string"], "Paquete")
        self.assertEqual(campos["wbs_level2_id"]["falsy_value_label"], "Tareas sin desglose")
