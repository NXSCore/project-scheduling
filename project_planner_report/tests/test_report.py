# -*- coding: utf-8 -*-
"""El informe PDF del planificador, sobre un proyecto de Odoo cualquiera."""
import io
import json

from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase
from odoo.tools.pdf import PdfFileReader


def _paginas(pdf):
    return PdfFileReader(io.BytesIO(pdf)).pages


class _Base:

    @classmethod
    def _crear(cls):
        env = cls.env
        company = env.ref("base.main_company")
        cls.proyecto = env["project.project"].create({"name": "Proyecto del informe", "allow_task_dependencies": True})
        T = env["project.task"].with_context(lang="en_US")
        pid = cls.proyecto.id
        cls.dominio = [("project_id", "=", pid)]
        cls.paquete = T.create({"name": "Paquete", "project_id": pid, "sequence": 1,
                                "planned_date_begin": "2026-11-02 14:00:00", "date_deadline": "2026-11-20 23:00:00"})
        cls.a = T.create({"name": "A", "project_id": pid, "parent_id": cls.paquete.id, "sequence": 1,
                          "planned_date_begin": "2026-11-02 14:00:00", "date_deadline": "2026-11-06 23:00:00"})
        cls.b = T.create({"name": "B", "project_id": pid, "parent_id": cls.paquete.id, "sequence": 2,
                          "planned_date_begin": "2026-11-09 14:00:00", "date_deadline": "2026-11-13 23:00:00"})
        cls.hito = T.create({"name": "Entrega", "project_id": pid, "sequence": 2, "is_milestone": True,
                             "planned_date_begin": "2026-11-20 23:00:00", "date_deadline": "2026-11-20 23:00:00"})
        env["project.dependency"].create({"successor_id": cls.b.id, "predecessor_id": cls.a.id, "link_type": "fs"})
        env["project.dependency"].create({"successor_id": cls.hito.id, "predecessor_id": cls.b.id, "link_type": "ff"})
        cls.usuario = env["res.users"].create({
            "name": "sched", "login": "sched_user", "password": "sched_user_pw", "company_id": company.id,
            "company_ids": [(6, 0, company.ids)], "tz": "America/Mexico_City",
            "groups_id": [(4, env.ref("project.group_project_user").id)]})
        cls.otro = env["res.users"].create({
            "name": "sched otro", "login": "sched_otro", "password": "sched_otro_pw", "company_id": company.id,
            "company_ids": [(6, 0, company.ids)], "groups_id": [(4, env.ref("project.group_project_user").id)]})

    def _wizard(self, user=None, **vals):
        W = self.env["project.planner.report.wizard"].with_user(user or self.usuario).with_context(lang="en_US")
        return W.create({"domain": json.dumps(self.dominio), **vals})


@tagged("post_install", "-at_install")
class TestPlannerReport(_Base, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear()

    def test_a_deadline_is_marked_and_explained_in_the_legend(self):
        """La marca de fecha límite y su entrada en la leyenda."""
        texto = _paginas(self._wizard()._render_pdf()[0])[0].extract_text()
        self.assertNotIn("Deadline", texto, "sin fechas límite no hay entrada en la leyenda")
        self.b.finish_deadline = "2026-11-12 23:00:00"
        filas = {f["name"]: f for f in self._wizard()._report_values()["rows"]}
        self.assertTrue(filas["B"]["deadline"])
        texto = _paginas(self._wizard()._render_pdf()[0])[0].extract_text()
        self.assertIn("Deadline", texto)

    def test_holidays_take_no_room_with_working_days_only(self):
        """El feriado del calendario cuenta como no laborable en el eje."""
        from datetime import datetime
        from odoo.addons.project_planner_report.models.gantt_pdf import Axis
        sin = Axis(datetime(2026, 11, 16), datetime(2026, 11, 20), {5, 6}, True)
        con = Axis(datetime(2026, 11, 16), datetime(2026, 11, 20), {5, 6}, True, holidays={datetime(2026, 11, 16).date()})
        self.assertEqual(con.length, sin.length - 1)
        self.assertTrue(con.is_off(datetime(2026, 11, 16).date()))

    def test_a_calendar_with_holidays_prints(self):
        """Un feriado global en el calendario no rompe el PDF."""
        cal = self.env.company.resource_calendar_id
        self.env["resource.calendar.leaves"].create({
            "name": "Feriado r85r2", "calendar_id": cal.id, "resource_id": False,
            "date_from": "2026-11-16 06:00:00", "date_to": "2026-11-17 05:59:59"})
        filas = {f["name"]: f for f in self._wizard()._report_values()["rows"]}
        self.assertTrue(filas["Paquete"]["duration"].endswith(" d"))
        self.assertTrue(self._wizard()._render_pdf()[0].startswith(b"%PDF"))

    def test_the_summary_counts_what_the_planner_shows(self):
        wiz = self._wizard()
        self.assertEqual((wiz.task_count, wiz.leaf_count, wiz.link_count), (4, 3, 2))

    def test_default_report_is_one_a3_landscape_page(self):
        pdf, nombre = self._wizard()._render_pdf()
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(nombre, "Proyecto del informe-planning.pdf")
        paginas = _paginas(pdf)
        self.assertEqual(len(paginas), 1)
        caja = paginas[0].mediabox
        self.assertEqual((round(float(caja.width)), round(float(caja.height))), (1191, 842), "A3 apaisado")

    def test_timeline_pages_multiply_the_pages_across(self):
        pdf, _ = self._wizard(timeline_pages=3)._render_pdf()
        self.assertEqual(len(_paginas(pdf)), 3)

    def test_rows_split_across_pages_downwards(self):
        T = self.env["project.task"]
        T.create([{"name": "Relleno %d" % i, "project_id": self.proyecto.id, "sequence": 10 + i,
                   "planned_date_begin": "2026-11-03 14:00:00", "date_deadline": "2026-11-04 23:00:00"} for i in range(120)])
        wiz = self._wizard(paper="a4")
        pdf, _ = wiz._render_pdf()
        self.assertGreater(len(_paginas(pdf)), 2, "124 filas no caben en una A4")
        self.assertEqual(round(float(_paginas(pdf)[0].mediabox.width)), 842, "A4 apaisado")

    def test_the_task_text_is_in_the_pdf(self):
        pdf, _ = self._wizard(names_on_bars=False)._render_pdf()
        texto = _paginas(pdf)[0].extract_text()
        for esperado in ("Paquete", "Entrega", "Task Name", "1 / 1"):
            self.assertIn(esperado, texto)

    def test_every_option_combination_renders(self):
        """Todas las casillas apagadas, solo días laborables, escala fija, vertical."""
        for vals in (
            {"repeat_header": False, "names_on_bars": False, "show_progress": False, "show_float": False,
             "show_links": False, "shade_weekends": False, "show_legend": False, "bar_colors": "uniform"},
            {"workdays_only": True, "status_line": "today", "show_baseline": True},
            {"fit_to_paper": False, "scale": "day"},
            {"fit_to_paper": False, "scale": "quarter", "paper": "letter", "orientation": "portrait", "font_scale": 60},
        ):
            with self.subTest(vals=vals):
                pdf, _ = self._wizard(**vals)._render_pdf()
                self.assertTrue(pdf.startswith(b"%PDF"))

    def test_fixed_day_scale_adds_pages_across(self):
        pdf, _ = self._wizard(fit_to_paper=False, scale="day", paper="a4")._render_pdf()
        self.assertGreater(len(_paginas(pdf)), 1, "29 días a 16 pt/día no caben en una A4")

    def test_follow_view_hides_collapsed_branches(self):
        wiz = self._wizard(follow_view=True, collapsed_ids=json.dumps([self.paquete.id]))
        filas = wiz._report_values()["rows"]
        self.assertEqual([f["name"] for f in filas], ["Paquete", "Entrega"])

    def test_summary_dates_come_from_children_and_dates_are_local(self):
        filas = {f["name"]: f for f in self._wizard()._report_values()["rows"]}
        # 14:00 UTC = 08:00 en Ciudad de México.
        self.assertEqual(filas["A"]["start"].hour, 8)
        self.assertEqual(filas["Paquete"]["start"], filas["A"]["start"])
        self.assertEqual(filas["Entrega"]["duration"], "0 d")

    def test_too_narrow_paper_is_a_clear_error(self):
        with self.assertRaises(UserError):
            self._wizard(paper="a4", orientation="portrait", font_scale=200)._render_pdf()

    def test_invalid_options_are_refused(self):
        with self.assertRaises(UserError):
            self._wizard(font_scale=10).action_export()
        with self.assertRaises(UserError):
            self._wizard(timeline_pages=0).action_export()

    def test_export_returns_the_download_url(self):
        wiz = self._wizard()
        self.assertEqual(wiz.action_export()["url"], "/project_planner_report/pdf/%d" % wiz.id)

    def test_the_report_speaks_spanish_when_es_mx_is_loaded(self):
        """Pertenencia de la clave del idioma, no «¿cambió el valor?»."""
        self.env["res.lang"]._activate_lang("es_MX")
        self.env["ir.module.module"]._load_module_terms(["project_planner_report"], ["es_MX"], overwrite=True)
        wiz = self._wizard().with_context(lang="es_MX")
        etiquetas = wiz._report_values()["labels"]
        self.assertEqual((etiquetas["printed"], etiquetas["col_progress"]), ("Impreso", "Av."))
        campo = self.env["ir.model.fields"]._get("project.planner.report.wizard", "fit_to_paper")
        self.assertEqual(campo.with_context(lang="es_MX").field_description, "Ajuste automático al papel")
        seleccion = dict(wiz._fields["paper"]._description_selection(wiz.env))
        self.assertEqual(seleccion["letter"], "Carta")

    # ------------------------------------------------------------ permisos
    def test_a_user_without_project_rights_prints_nothing(self):
        """El asistente se abre a usuarios internos (un perfil de solo
        lectura puede no tener el grupo de Proyectos), pero las tareas se
        leen con SUS permisos: quien no puede leer tareas no imprime ninguna."""
        interno = self.env["res.users"].create({
            "name": "sched interno", "login": "sched_interno", "groups_id": [(6, 0, self.env.ref("base.group_user").ids)]})
        wiz = self._wizard(user=interno)
        with self.assertRaises(AccessError):
            wiz._render_pdf()

    def test_a_portal_user_cannot_open_the_report(self):
        portal = self.env["res.users"].create({
            "name": "sched portal", "login": "sched_portal", "groups_id": [(6, 0, self.env.ref("base.group_portal").ids)]})
        with self.assertRaises(AccessError):
            self._wizard(user=portal)

    def test_a_user_only_sees_their_own_wizards(self):
        wiz = self._wizard()
        W = self.env["project.planner.report.wizard"]
        self.assertFalse(W.with_user(self.otro).search([("id", "=", wiz.id)]))
        self.assertEqual(W.with_user(self.usuario).search([("id", "=", wiz.id)]), wiz)

    def test_another_company_prints_none_of_these_tasks(self):
        otra = self.env["res.company"].create({"name": "sched otra compañía"})
        ajeno = self.env["res.users"].create({
            "name": "sched ajeno", "login": "sched_ajeno", "company_id": otra.id, "company_ids": [(6, 0, otra.ids)],
            "groups_id": [(4, self.env.ref("project.group_project_user").id)]})
        self.proyecto.company_id = self.env.ref("base.main_company")
        wiz = self._wizard(user=ajeno)
        self.assertEqual(wiz.task_count, 0)
        self.assertEqual(wiz._report_values()["rows"], [])
        self.assertTrue(wiz._render_pdf()[0].startswith(b"%PDF"), "un informe vacío también se imprime")


@tagged("post_install", "-at_install")
class TestPlannerReportHttp(_Base, HttpCase):
    """El rol previsto llega al PDF por la URL; otro usuario, no."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear()

    def test_the_owner_downloads_and_another_user_gets_404(self):
        wiz = self._wizard()
        url = "/project_planner_report/pdf/%d" % wiz.id
        self.authenticate("sched_user", "sched_user_pw")
        res = self.url_open(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["Content-Type"], "application/pdf")
        self.assertTrue(res.content.startswith(b"%PDF"))
        self.authenticate("sched_otro", "sched_otro_pw")
        self.assertEqual(self.url_open(url).status_code, 404)

    def test_the_report_button_is_in_the_backend_assets(self):
        archivos = [f["url"] for f in self.env["ir.qweb"]._get_asset_bundle("web.assets_backend").files]
        self.assertTrue(any("project_planner_report/static/src/planner_report.js" in a for a in archivos))


@tagged("post_install", "-at_install")
class TestReportColumns(_Base, TransactionCase):
    """Con «Seguir la vista», el PDF imprime las columnas del planificador."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear()

    def test_following_the_view_prints_the_planner_columns(self):
        columnas = ["code", "name", "dur", "pred", "succ", "float", "deadline"]
        self.b.finish_deadline = "2026-11-12 23:00:00"
        wiz = self._wizard(follow_view=True, view_columns=json.dumps(columnas))
        self.assertEqual(wiz._report_options()["columns"], ["code", "name", "duration", "pred", "succ", "float", "deadline"])
        filas = {f["name"]: f for f in wiz._report_values()["rows"]}
        self.assertEqual(filas["B"]["cells"]["pred"], filas["A"]["code"])
        self.assertEqual(filas["A"]["cells"]["succ"], filas["B"]["code"])
        self.assertTrue(filas["B"]["cells"]["deadline"])
        texto = _paginas(wiz._render_pdf()[0])[0].extract_text()
        self.assertIn("Predecessors", texto)
        self.assertIn("Successors", texto)
        self.assertNotIn("Prog.", texto, "el avance no estaba entre las columnas de la vista")

    def test_without_following_the_view_the_usual_columns(self):
        wiz = self._wizard(view_columns=json.dumps(["name", "users"]))
        self.assertIsNone(wiz._report_options()["columns"])
        self.assertIn("Prog.", _paginas(wiz._render_pdf()[0])[0].extract_text())

    def test_following_the_view_prints_only_the_filtered_tasks(self):
        """Con «Seguir la vista», el PDF imprime lo que deja el filtro."""
        ids = [self.paquete.id, self.a.id]
        wiz = self._wizard(follow_view=True, filter_ids=json.dumps(ids))
        self.assertEqual([f["name"] for f in wiz._report_values()["rows"]], ["Paquete", "A"])
        sin_filtro = self._wizard(follow_view=True)
        self.assertEqual(len(sin_filtro._report_values()["rows"]), 4)
