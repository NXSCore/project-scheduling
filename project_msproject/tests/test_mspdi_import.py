# -*- coding: utf-8 -*-
"""Importar el XML de MS Project a un proyecto de Odoo cualquiera.
"""
import base64

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


# UID 0 es el resumen del proyecto. 1 Paquete > 2 Rama > (3, 4); 5 hito al nivel 1.
# Vínculos: 4 FS de 3 con 1 día laborable (4800 décimas de minuto con 480 min/día);
# 2 SS de 1 sin desfase; 5 FF de 4 con 2 días naturales (LagFormat 8); 5 SF de 3 en %.
MSPDI = """<?xml version="1.0" encoding="UTF-8"?>
<Project xmlns="http://schemas.microsoft.com/project">
  <Name>Prueba</Name><MinutesPerDay>480</MinutesPerDay><CalendarUID>1</CalendarUID>
  <ScheduleFromStart>0</ScheduleFromStart><FinishDate>2026-11-30T17:00:00</FinishDate><HonorConstraints>0</HonorConstraints>
  <Calendars>
    <Calendar><UID>1</UID><Name>Estándar</Name><IsBaseCalendar>1</IsBaseCalendar>
      <WeekDays>
        <WeekDay><DayType>1</DayType><DayWorking>0</DayWorking></WeekDay>
        <WeekDay><DayType>2</DayType><DayWorking>1</DayWorking><WorkingTimes>
          <WorkingTime><FromTime>09:00:00</FromTime><ToTime>13:00:00</ToTime></WorkingTime>
          <WorkingTime><FromTime>15:00:00</FromTime><ToTime>19:00:00</ToTime></WorkingTime></WorkingTimes></WeekDay>
        <WeekDay><DayType>3</DayType><DayWorking>1</DayWorking></WeekDay>
        <WeekDay><DayType>4</DayType><DayWorking>1</DayWorking></WeekDay>
        <WeekDay><DayType>5</DayType><DayWorking>1</DayWorking></WeekDay>
        <WeekDay><DayType>6</DayType><DayWorking>1</DayWorking></WeekDay>
        <WeekDay><DayType>7</DayType><DayWorking>1</DayWorking></WeekDay>
      </WeekDays>
      <Exceptions>
        <Exception><Name>Asueto</Name><DayWorking>0</DayWorking>
          <TimePeriod><FromDate>2026-11-16T00:00:00</FromDate><ToDate>2026-11-16T23:59:00</ToDate></TimePeriod></Exception>
      </Exceptions>
    </Calendar>
  </Calendars>
  <Tasks>
    <Task><UID>0</UID><Name>Resumen</Name><OutlineLevel>0</OutlineLevel></Task>
    <Task><UID>1</UID><Name>Paquete</Name><OutlineLevel>1</OutlineLevel>
      <Start>2026-11-02T08:00:00</Start><Finish>2026-11-20T17:00:00</Finish></Task>
    <Task><UID>2</UID><Name>Rama</Name><OutlineLevel>2</OutlineLevel>
      <Start>2026-11-02T08:00:00</Start><Finish>2026-11-13T17:00:00</Finish>
      <PredecessorLink><PredecessorUID>1</PredecessorUID><Type>3</Type><LinkLag>0</LinkLag><LagFormat>7</LagFormat></PredecessorLink></Task>
    <Task><UID>3</UID><Name>Hoja A</Name><OutlineLevel>3</OutlineLevel>
      <Start>2026-11-02T08:00:00</Start><Finish>2026-11-06T17:00:00</Finish><PercentComplete>40</PercentComplete>
      <Manual>1</Manual><ActualStart>2026-11-02T08:00:00</ActualStart>
      <Duration>PT40H0M0S</Duration></Task>
    <Task><UID>4</UID><Name>Hoja B</Name><OutlineLevel>3</OutlineLevel>
      <Start>2026-11-10T08:00:00</Start><Finish>2026-11-13T17:00:00</Finish>
      <ConstraintType>4</ConstraintType><ConstraintDate>2026-11-10T08:00:00</ConstraintDate>
      <Deadline>2026-11-12T17:00:00</Deadline>
      <PredecessorLink><PredecessorUID>3</PredecessorUID><Type>1</Type><LinkLag>4800</LinkLag><LagFormat>7</LagFormat></PredecessorLink></Task>
    <Task><UID>5</UID><Name>Entrega</Name><OutlineLevel>1</OutlineLevel><Milestone>1</Milestone>
      <Start>2026-11-20T17:00:00</Start><Finish>2026-11-20T17:00:00</Finish>
      <PredecessorLink><PredecessorUID>4</PredecessorUID><Type>0</Type><LinkLag>28800</LinkLag><LagFormat>8</LagFormat></PredecessorLink>
      <PredecessorLink><PredecessorUID>3</PredecessorUID><Type>2</Type><LinkLag>500</LinkLag><LagFormat>19</LagFormat></PredecessorLink></Task>
  </Tasks>
  <Resources>
    <Resource><UID>1</UID><Name>Proyectista</Name></Resource>
    <Resource><UID>2</UID><Name>Nadie Conocido</Name></Resource>
  </Resources>
  <Assignments>
    <Assignment><TaskUID>3</TaskUID><ResourceUID>1</ResourceUID></Assignment>
    <Assignment><TaskUID>4</TaskUID><ResourceUID>2</ResourceUID></Assignment>
  </Assignments>
</Project>"""


@tagged("post_install", "-at_install")
class TestMspdiImport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.proyecto = cls.env["project.project"].create({"name": "Proyecto importado"})
        grupo = cls.env.ref("project.group_project_manager")
        cls.pm = cls.env["res.users"].create({
            # Idioma fijo: el resumen se compara contra su texto, y con
            # es_MX cargado en la base el usuario nacería en español.
            "name": "PM", "login": "pm_sched", "tz": "America/Mexico_City", "lang": "en_US",
            "company_id": cls.company.id, "company_ids": [(6, 0, cls.company.ids)],
            "group_ids": [(4, grupo.id)]})
        cls.proyectista = cls.env["res.users"].create({
            "name": "Proyectista", "login": "proyectista_sched",
            "company_id": cls.company.id, "company_ids": [(6, 0, cls.company.ids)],
            "group_ids": [(4, cls.env.ref("project.group_project_user").id)]})

    def _importar(self, xml=MSPDI, user=None):
        user = user or self.pm
        # `_()` traduce con el idioma del CONTEXTO, no del usuario: se fija aquí.
        wiz = self.env["project.mspdi.import.wizard"].with_user(user).with_context(lang="en_US").create({
            "project_id": self.proyecto.id, "file": base64.b64encode(xml.encode()), "filename": "sched.xml"})
        wiz.action_import()
        return wiz

    def _tareas(self):
        return {t.ms_uid: t for t in self.env["project.task"].search(
            [("project_id", "=", self.proyecto.id), ("ms_uid", "!=", 0)])}

    def test_hierarchy_order_and_wbs_follow_the_file(self):
        self._importar()
        t = self._tareas()
        self.assertEqual(set(t), {1, 2, 3, 4, 5}, "el resumen del proyecto (UID 0) no se importa")
        self.assertEqual(t[2].parent_id, t[1])
        self.assertEqual((t[3].parent_id, t[4].parent_id), (t[2], t[2]))
        self.assertFalse(t[5].parent_id)
        raiz = t[1].wbs_code
        self.assertEqual([t[2].wbs_code, t[3].wbs_code, t[4].wbs_code],
                         [raiz + ".1", raiz + ".1.1", raiz + ".1.2"])
        self.assertEqual(int(t[5].wbs_code), int(raiz) + 1)

    def test_dates_are_read_in_the_importer_timezone(self):
        self._importar()
        # 08:00 en Ciudad de México (UTC-6) = 14:00 UTC.
        self.assertEqual(str(self._tareas()[3].planned_date_begin), "2026-11-02 14:00:00")

    def test_milestone_and_assignee(self):
        self._importar()
        t = self._tareas()
        self.assertTrue(t[5].is_milestone)
        self.assertFalse(t[3].is_milestone)
        self.assertEqual(t[3].user_ids, self.proyectista)
        self.assertFalse(t[4].user_ids, "un recurso que no es usuario no se inventa")

    def test_links_keep_type_and_lag(self):
        wiz = self._importar()
        t = self._tareas()
        link = lambda s, p: t[s].predecessor_link_ids.filtered(lambda l: l.predecessor_id == t[p])
        self.assertEqual((link(4, 3).link_type, link(4, 3).lag_days, link(4, 3).lag_elapsed), ("fs", 1.0, False))
        self.assertEqual(link(2, 1).link_type, "ss")
        self.assertEqual((link(5, 4).link_type, link(5, 4).lag_days, link(5, 4).lag_elapsed), ("ff", 2.0, True))
        self.assertEqual((link(5, 3).link_type, link(5, 3).lag_days), ("sf", 0.0))
        self.assertNotIn(t[3], t[4].depend_on_ids, "un FS con desfase no se dibuja como flecha nativa")
        self.assertIn("Progress is not imported", wiz.summary)
        self.assertIn("Nadie Conocido", wiz.summary)

    def test_importing_again_updates_instead_of_duplicating(self):
        self._importar()
        antes = self._tareas()
        self._importar(MSPDI.replace("Hoja A", "Hoja A renombrada"))
        despues = self._tareas()
        self.assertEqual(set(antes), set(despues))
        self.assertEqual(antes[3], despues[3])
        self.assertEqual(despues[3].name, "Hoja A renombrada")
        self.assertEqual(len(despues[5].predecessor_link_ids), 2)

    def test_external_entities_are_not_resolved(self):
        xxe = MSPDI.replace('<?xml version="1.0" encoding="UTF-8"?>',
                            '<?xml version="1.0"?><!DOCTYPE p [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                            ).replace("<Name>Paquete</Name>", "<Name>&x;</Name>")
        self._importar(xxe)
        self.assertNotIn("root:", self._tareas()[1].name or "")

    def test_a_file_that_is_not_ms_project_is_refused(self):
        with self.assertRaises(UserError):
            self._importar("<?xml version='1.0'?><Otra/>")

    def test_who_cannot_capture_the_schedule_cannot_import(self):
        lector = self.env["res.users"].create({
            "name": "Lector", "login": "lector_sched", "company_id": self.company.id,
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])]})
        with self.assertRaises(AccessError):
            self._importar(user=lector)

    def test_date_constraints_come_from_the_file(self):
        """`<ConstraintType>4` = «No comenzar antes del» (SNET)."""
        self._importar()
        t = self._tareas()
        self.assertEqual(t[4].constraint_type, "snet")
        self.assertEqual(str(t[4].constraint_date), "2026-11-10 14:00:00")
        self.assertEqual(t[3].constraint_type, "asap")

    def test_a_summary_marked_as_milestone_keeps_its_span(self):
        """En MS Project la marca de hito de un resumen es solo dibujo."""
        xml = MSPDI.replace("<UID>2</UID><Name>Rama</Name><OutlineLevel>2</OutlineLevel>",
                            "<UID>2</UID><Name>Rama</Name><OutlineLevel>2</OutlineLevel>"
                            "<Duration>PT80H0M0S</Duration><Milestone>1</Milestone><Summary>1</Summary>")
        self.assertIn("<Milestone>1</Milestone><Summary>1</Summary>", xml)
        self._importar(xml)
        rama = self._tareas()[2]
        self.assertFalse(rama.is_milestone)
        self.assertEqual(str(rama.date_deadline), "2026-11-13 23:00:00")

    def test_the_deadline_comes_from_the_file(self):
        """`<Deadline>` = fecha límite (acota el fin tardío, no mueve)."""
        self._importar()
        t = self._tareas()
        self.assertEqual(str(t[4].finish_deadline), "2026-11-12 23:00:00")
        self.assertFalse(t[3].finish_deadline)
        self.assertEqual(str(t[4].date_deadline), "2026-11-13 23:00:00", "el fin planeado no se toca")

    def test_the_file_calendar_becomes_the_project_calendar(self):
        """Semana laboral (aquí con sábado) y feriados del archivo."""
        wiz = self._importar()
        cal = self.proyecto.schedule_calendar_id
        self.assertIn("Microsoft Project", cal.name)
        dias = {a.dayofweek for a in cal.attendance_ids}
        self.assertEqual(dias, {"0", "1", "2", "3", "4", "5"}, "lunes a sábado; domingo no")
        lunes = cal.attendance_ids.filtered(lambda a: a.dayofweek == "0")
        self.assertEqual(sorted((a.hour_from, a.hour_to) for a in lunes), [(9.0, 13.0), (15.0, 19.0)])
        self.assertEqual(len(cal.global_leave_ids), 1)
        self.assertIn(cal.name, wiz.summary)

    def test_reimporting_reuses_the_calendar(self):
        """Reimportar no crea otro calendario ni duplica los feriados."""
        self._importar()
        cal = self.proyecto.schedule_calendar_id
        cuantos = self.env["resource.calendar"].search_count([])
        self._importar()
        self.assertEqual(self.proyecto.schedule_calendar_id, cal)
        self.assertEqual(self.env["resource.calendar"].search_count([]), cuantos)
        self.assertEqual(len(cal.global_leave_ids), 1)

    def test_the_duration_comes_from_the_file(self):
        """`<Duration>PT40H` con 480 minutos por día = 5 días laborables."""
        self._importar()
        self.assertEqual(self._tareas()[3].duration_days, 5.0)

    def test_the_company_calendar_can_be_chosen(self):
        wiz = self.env["project.mspdi.import.wizard"].with_user(self.pm).with_context(lang="en_US").create({
            "project_id": self.proyecto.id, "file": base64.b64encode(MSPDI.encode()), "filename": "sched.xml",
            "calendar_mode": "company"})
        wiz.action_import()
        self.assertEqual(self.proyecto.schedule_calendar_id, self.env.company.resource_calendar_id)

    def test_scheduling_options_manual_and_actuals_come_from_the_file(self):
        """Programar desde el fin, respetar restricciones, manual y real."""
        self._importar()
        self.assertEqual((self.proyecto.schedule_from, self.proyecto.honor_constraints), ("finish", False))
        self.assertEqual(str(self.proyecto.project_finish), "2026-11-30 23:00:00")
        t = self._tareas()
        self.assertTrue(t[3].manually_scheduled)
        self.assertEqual(str(t[3].actual_start), "2026-11-02 14:00:00")
        self.assertFalse(t[4].manually_scheduled)

    def test_reimport_replaces_the_links_between_imported_tasks(self):
        """Un vínculo que ya no viene en el archivo se retira, y así
        reimportar con otra versión no cierra ciclos con los vínculos viejos."""
        self._importar()
        t = self._tareas()
        self.env["project.dependency"].create({"predecessor_id": t[4].id, "successor_id": t[1].id})
        wiz = self._importar(MSPDI.replace("<PredecessorUID>3</PredecessorUID><Type>1</Type>", "<PredecessorUID>2</PredecessorUID><Type>1</Type>"))
        deps = {(d.predecessor_id.ms_uid, d.successor_id.ms_uid) for d in t[4].predecessor_link_ids | t[1].predecessor_link_ids}
        self.assertNotIn((4, 1), deps, "el vínculo que no viene en el archivo se retiró")
        self.assertIn((2, 4), deps)
        self.assertIn("removed", wiz.summary)
