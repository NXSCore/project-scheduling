# -*- coding: utf-8 -*-
"""Exportar al XML de MS Project y que lo exportado vuelva sin perder nada."""
import base64

from lxml import etree

from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase

from .test_mspdi_import import MSPDI

#: Orden de los elementos de una tarea en los XML que guardó MS Project
#: MS Project rechaza un elemento fuera de orden.
ORDEN_TAREA = ["UID", "ID", "Name", "Active", "Manual", "Type", "IsNull", "CreateDate", "WBS", "OutlineNumber",
               "OutlineLevel", "Priority", "Start", "Finish", "Duration", "ManualStart", "ManualFinish",
               "ManualDuration", "DurationFormat", "ResumeValid", "EffortDriven", "Recurring", "OverAllocated",
               "Estimated", "Milestone", "Summary", "DisplayAsSummary", "Critical", "IsSubproject",
               "IsSubprojectReadOnly", "ExternalTask", "PercentComplete", "ActualStart", "ActualFinish",
               "ConstraintType", "CalendarUID", "ConstraintDate", "Deadline", "LevelAssignments", "LevelingCanSplit",
               "LevelingDelay", "LevelingDelayFormat", "IgnoreResourceCalendar", "HideBar", "Rollup",
               "PredecessorLink"]
#: Lo que MS Project escribe en TODA tarea: sin los ceros, al abrir el
#: archivo descarta casi todos los vínculos.
SIEMPRE = ["UID", "ID", "Name", "Active", "Manual", "Type", "IsNull", "OutlineLevel", "Priority", "DurationFormat",
           "Estimated", "Milestone", "Summary", "Critical", "ConstraintType", "CalendarUID"]
ORDEN_PROYECTO = ["SaveVersion", "Name", "Title", "Author", "CreationDate", "ScheduleFromStart", "StartDate",
                  "FinishDate", "CriticalSlackLimit", "CalendarUID", "DefaultStartTime", "DefaultFinishTime",
                  "MinutesPerDay", "MinutesPerWeek", "DaysPerMonth", "DurationFormat", "HonorConstraints",
                  "NewTasksAreManual", "Calendars", "Tasks", "Resources", "Assignments"]


class _Base:

    @classmethod
    def _crear(cls):
        cls.company = cls.env.ref("base.main_company")
        grupo = cls.env.ref("project.group_project_manager")
        cls.pm = cls.env["res.users"].create({
            "name": "PM", "login": "pm_sched", "password": "pm_r86x_pw", "tz": "America/Mexico_City",
            "lang": "en_US", "company_id": cls.company.id, "company_ids": [(6, 0, cls.company.ids)],
            "groups_id": [(4, grupo.id)]})
        cls.proyectista = cls.env["res.users"].create({
            "name": "Proyectista", "login": "proyectista_sched", "email": "proyectista.sched@example.com",
            "company_id": cls.company.id, "company_ids": [(6, 0, cls.company.ids)],
            "groups_id": [(4, cls.env.ref("project.group_project_user").id)]})
        cls.origen = cls.env["project.project"].create({"name": "Origen"})

    def _importar(self, proyecto, xml, modo="file"):
        wiz = self.env["project.mspdi.import.wizard"].with_user(self.pm).with_context(lang="en_US").create({
            "project_id": proyecto.id, "file": base64.b64encode(xml if isinstance(xml, bytes) else xml.encode()),
            "filename": "sched.xml", "calendar_mode": modo})
        wiz.action_import()
        return wiz

    def _exportar(self, proyecto):
        proyecto.with_user(self.pm).action_export_mspdi()
        return proyecto.with_user(self.pm)._mspdi_export()


@tagged("post_install", "-at_install")
class TestMspdiExport(_Base, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear()

    def setUp(self):
        super().setUp()
        self._importar(self.origen, MSPDI)

    @staticmethod
    def _foto(proyecto):
        """Todo lo que el intercambio debe conservar, por nombre de tarea."""
        foto = {}
        for t in proyecto.env["project.task"].search([("project_id", "=", proyecto.id)]):
            links = sorted((d.predecessor_id.name, d.link_type, d.lag_days, d.lag_elapsed) for d in t.predecessor_link_ids)
            foto[t.name] = {
                "wbs": t.wbs_code, "parent": t.parent_id.name, "start": t.planned_date_begin, "end": t.date_deadline,
                "milestone": t.is_milestone, "duration": t.duration_days, "manual": t.manually_scheduled,
                "actual": (t.actual_start, t.actual_finish), "constraint": (t.constraint_type, t.constraint_date),
                "deadline": t.finish_deadline, "links": links, "users": sorted(t.user_ids.mapped("login")),
            }
        return foto

    def test_round_trip_into_a_new_project_keeps_everything(self):
        destino = self.env["project.project"].create({"name": "Destino"})
        self._importar(destino, self._exportar(self.origen))
        self.assertEqual(self._foto(destino), self._foto(self.origen))
        for campo in ("minutes_per_day", "schedule_from", "project_finish", "honor_constraints"):
            self.assertEqual(destino[campo], self.origen[campo], campo)
        cal_o, cal_d = self.origen.schedule_calendar_id, destino.schedule_calendar_id
        turnos = lambda c: sorted((a.dayofweek, a.hour_from, a.hour_to) for a in c.attendance_ids if not a.display_type)
        self.assertEqual(turnos(cal_d), turnos(cal_o))
        feriados = lambda c: sorted((l.name, l.date_from, l.date_to) for l in c.leave_ids if not l.resource_id)
        self.assertEqual(feriados(cal_d), feriados(cal_o))

    def test_reimporting_the_export_into_the_same_project_changes_nothing(self):
        antes = self._foto(self.origen)
        self._importar(self.origen, self._exportar(self.origen), modo="keep")
        self.assertEqual(self._foto(self.origen), antes)

    def test_tasks_created_in_odoo_get_a_uid_and_are_not_duplicated(self):
        nueva = self.env["project.task"].create({
            "name": "Creada en Odoo", "project_id": self.origen.id,
            "planned_date_begin": "2026-11-23 14:00:00", "date_deadline": "2026-11-24 23:00:00"})
        xml = self._exportar(self.origen)
        self.assertTrue(nueva.ms_uid)
        self.assertNotIn(nueva.ms_uid, {1, 2, 3, 4, 5})
        cuantas = self.env["project.task"].search_count([("project_id", "=", self.origen.id)])
        self._importar(self.origen, xml, modo="keep")
        self.assertEqual(self.env["project.task"].search_count([("project_id", "=", self.origen.id)]), cuantas)

    def test_elements_follow_microsoft_project_order(self):
        raiz = etree.fromstring(self._exportar(self.origen))
        nombre = lambda e: etree.QName(e).localname
        hijos = [nombre(c) for c in raiz]
        self.assertEqual(hijos, [x for x in ORDEN_PROYECTO if x in hijos])
        tareas = raiz.findall("{*}Tasks/{*}Task")
        self.assertEqual(tareas[0].findtext("{*}UID"), "0", "la primera tarea es el resumen del proyecto")
        for t in tareas:
            orden = [nombre(c) for c in t]
            self.assertEqual(orden, sorted(orden, key=ORDEN_TAREA.index), t.findtext("{*}Name"))

    def test_every_task_carries_the_scheduling_flags_even_when_zero(self):
        raiz = etree.fromstring(self._exportar(self.origen))
        for t in raiz.findall("{*}Tasks/{*}Task")[1:]:
            faltan = [x for x in SIEMPRE if t.find("{*}" + x) is None]
            self.assertEqual(faltan, [], t.findtext("{*}Name"))

    def test_a_task_without_predecessors_is_anchored_and_comes_back_asap(self):
        """MS Project lleva al inicio del proyecto la tarea automática sin
        predecesoras; se exporta con «No comenzar antes del» su fecha, y al
        reimportar vuelve a ser «lo antes posible»."""
        suelta = self.env["project.task"].create({
            "name": "Suelta", "project_id": self.origen.id,
            "planned_date_begin": "2026-12-01 15:00:00", "date_deadline": "2026-12-03 23:00:00"})
        raiz = etree.fromstring(self._exportar(self.origen))
        por_nombre = {t.findtext("{*}Name"): t for t in raiz.iterfind("{*}Tasks/{*}Task")}
        t = por_nombre["Suelta"]
        self.assertEqual(t.findtext("{*}ConstraintType"), "4")
        self.assertEqual(t.findtext("{*}ConstraintDate"), t.findtext("{*}Start"))
        self.assertEqual(por_nombre["Hoja B"].findtext("{*}ConstraintDate"), "2026-11-10T08:00:00",
                         "una restricción real se exporta tal cual")
        self.assertEqual(por_nombre["Entrega"].findtext("{*}ConstraintType"), "0", "con predecesoras no se ancla")
        destino = self.env["project.project"].create({"name": "Destino anclas"})
        self._importar(destino, etree.tostring(raiz))
        nueva = self.env["project.task"].search([("project_id", "=", destino.id), ("name", "=", "Suelta")])
        self.assertEqual(nueva.constraint_type, "asap")
        self.assertFalse(nueva.constraint_date)
        self.assertEqual(nueva.planned_date_begin, suelta.planned_date_begin)

    def test_assignments_carry_dates_and_work(self):
        raiz = etree.fromstring(self._exportar(self.origen))
        asg = raiz.find("{*}Assignments/{*}Assignment")
        self.assertIsNotNone(asg)
        for tag in ("Start", "Finish", "Units", "Work"):
            self.assertTrue(asg.findtext("{*}" + tag), tag)
        tarea = next(t for t in raiz.iterfind("{*}Tasks/{*}Task") if t.findtext("{*}UID") == asg.findtext("{*}TaskUID"))
        self.assertEqual(asg.findtext("{*}Work"), tarea.findtext("{*}Duration"), "una unidad: trabajo = duración")
        self.assertEqual(asg.findtext("{*}Start"), tarea.findtext("{*}Start"))

    def test_links_carry_microsoft_project_codes(self):
        raiz = etree.fromstring(self._exportar(self.origen))
        por_uid = {t.findtext("{*}UID"): t for t in raiz.iterfind("{*}Tasks/{*}Task")}
        enlaces = {(pl.findtext("{*}PredecessorUID"), pl.findtext("{*}Type"), pl.findtext("{*}LinkLag"), pl.findtext("{*}LagFormat"))
                   for pl in por_uid["5"].iterfind("{*}PredecessorLink")}
        # FF de 4 con 2 días naturales; SF de 3 (el % no se importa: sin desfase).
        self.assertEqual(enlaces, {("4", "0", "28800", "8"), ("3", "2", "0", "7")})
        pl = por_uid["4"].find("{*}PredecessorLink")
        self.assertEqual((pl.findtext("{*}Type"), pl.findtext("{*}LinkLag"), pl.findtext("{*}LagFormat")), ("1", "4800", "7"))


@tagged("post_install", "-at_install")
class TestMspdiExportHttp(_Base, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear()

    def test_the_download_respects_project_access(self):
        self._importar(self.origen, MSPDI)
        privado = self.env["project.project"].create({"name": "Privado", "privacy_visibility": "followers"})
        self.authenticate("pm_sched", "pm_r86x_pw")
        res = self.url_open("/project_msproject/export/%d" % self.origen.id)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"<Project", res.content)
        self.assertIn(b"Hoja A", res.content)
        externo = self.env["res.users"].create({
            "name": "Interno", "login": "interno_sched", "password": "interno_r86x_pw",
            "groups_id": [(6, 0, self.env.ref("base.group_user").ids)]})
        self.assertTrue(externo)
        self.authenticate("interno_sched", "interno_r86x_pw")
        self.assertEqual(self.url_open("/project_msproject/export/%d" % privado.id).status_code, 404)
