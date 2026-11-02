# -*- coding: utf-8 -*-
"""El planificador genérico, sobre un proyecto de Odoo cualquiera.

Solo requieren la app Proyectos.
"""
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPlannerGeneric(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.ref("base.main_company")
        cls.proyecto = cls.env["project.project"].create({"name": "Proyecto del planificador", "allow_task_dependencies": True})
        T = cls.env["project.task"]
        pid = cls.proyecto.id
        cls.dominio = [("project_id", "=", pid)]
        cls.paquete = T.create({"name": "Paquete", "project_id": pid, "sequence": 1,
                                "planned_date_begin": "2026-11-02 14:00:00", "date_deadline": "2026-11-20 23:00:00"})
        cls.b = T.create({"name": "B", "project_id": pid, "parent_id": cls.paquete.id, "sequence": 2,
                          "planned_date_begin": "2026-11-09 14:00:00", "date_deadline": "2026-11-13 23:00:00"})
        cls.a = T.create({"name": "A", "project_id": pid, "parent_id": cls.paquete.id, "sequence": 1,
                          "planned_date_begin": "2026-11-02 14:00:00", "date_deadline": "2026-11-06 23:00:00"})
        cls.hito = T.create({"name": "Entrega", "project_id": pid, "sequence": 2, "is_milestone": True,
                             "planned_date_begin": "2026-11-20 23:00:00", "date_deadline": "2026-11-20 23:00:00"})
        cls.env["project.dependency"].create({"successor_id": cls.b.id, "predecessor_id": cls.a.id, "link_type": "ss", "lag_days": 2})
        cls.hito.depend_on_ids = [(4, cls.b.id)]  # sin fila: fin-inicio sin desfase
        cls.capturista = cls.env["res.users"].create({
            "name": "sched", "login": "sched_user", "company_id": company.id, "company_ids": [(6, 0, company.ids)],
            "groups_id": [(4, cls.env.ref("project.group_project_user").id)]})

    def _datos(self):
        return self.env["project.task"].planner_data(self.dominio)

    def test_tasks_come_in_wbs_order_with_their_tree(self):
        datos = self._datos()
        self.assertEqual([t["name"] for t in datos["tasks"]], ["Paquete", "A", "B", "Entrega"])
        por_nombre = {t["name"]: t for t in datos["tasks"]}
        self.assertTrue(por_nombre["Paquete"]["summary"])
        self.assertEqual(por_nombre["A"]["parent_id"], self.paquete.id)
        self.assertTrue(por_nombre["Entrega"]["milestone"])
        self.assertTrue(por_nombre["A"]["start"].endswith("Z"), "las fechas viajan en UTC explícito")

    def test_links_carry_type_and_lag_and_default_to_finish_start(self):
        vinculos = {(l["from"], l["to"]): l for l in self._datos()["links"]}
        self.assertEqual((vinculos[(self.a.id, self.b.id)]["type"], vinculos[(self.a.id, self.b.id)]["lag"]), ("ss", 2.0))
        self.assertEqual((vinculos[(self.b.id, self.hito.id)]["type"], vinculos[(self.b.id, self.hito.id)]["lag"]), ("fs", 0.0))

    def test_the_planner_assets_are_in_the_backend(self):
        archivos = [f["url"] for f in self.env["ir.qweb"]._get_asset_bundle("web.assets_backend").files]
        self.assertTrue(any("project_planner/static/src/planner/planner.js" in a for a in archivos))

    def test_the_view_reads_by_search_domain(self):
        """La vista carga por el dominio de la búsqueda; si el filtro deja fuera
        al padre, la tarea sube a raíz en vez de desaparecer."""
        datos = self.env["project.task"].with_user(self.capturista).planner_data(
            self.dominio + [("name", "in", ["A", "B"])])
        self.assertEqual([t["name"] for t in datos["tasks"]], ["A", "B"])
        self.assertFalse(datos["tasks"][0]["parent_id"])
        self.assertEqual(len(datos["links"]), 1)

    # ------------------------------------------------------------ edición
    def _links(self, tarea):
        return {(l.predecessor_id.name, l.link_type, l.lag_days, l.lag_elapsed) for l in tarea.predecessor_link_ids}

    def test_predecessors_are_written_as_in_ms_project(self):
        T = self.env["project.task"].with_user(self.capturista)
        a, b = self.a.wbs_code, self.b.wbs_code
        T.planner_set_predecessors(self.hito.id, f"{a}SS+2; {b}FF-1,5dn")
        self.assertEqual(self._links(self.hito), {("A", "ss", 2.0, False), ("B", "ff", -1.5, True)})
        self.assertFalse(self.hito.depend_on_ids, "SS y FF no son flechas nativas")
        # Las abreviaturas en español de MS Project: CC = comienzo-comienzo.
        T.planner_set_predecessors(self.hito.id, f"{a}CC")
        self.assertEqual(self._links(self.hito), {("A", "ss", 0.0, False)})
        self.assertEqual(self.hito.predecessor_link_ids.predecessor_id, self.a, "lo que no se escribe se quita")
        T.planner_set_predecessors(self.hito.id, f"{a}")
        self.assertEqual(self.hito.depend_on_ids, self.a, "un FS sin desfase sí es flecha nativa")
        T.planner_set_predecessors(self.hito.id, "")
        self.assertFalse(self.hito.depend_on_ids)
        self.assertFalse(self.hito.predecessor_link_ids)

    def test_a_predecessor_that_does_not_exist_is_refused_whole(self):
        from odoo.exceptions import UserError
        T = self.env["project.task"].with_user(self.capturista)
        antes = self.b.predecessor_link_ids
        with self.assertRaises(UserError):
            T.planner_set_predecessors(self.b.id, f"{self.a.wbs_code}; 99.9")
        self.assertEqual(self.b.predecessor_link_ids, antes, "nada a medias")
        with self.assertRaises(UserError):
            T.planner_set_predecessors(self.b.id, self.b.wbs_code)

    def _hijas(self, padre):
        return [(t.wbs_code, t.name) for t in padre.child_ids.sorted(lambda x: tuple(int(p) for p in x.wbs_code.split(".")))]

    def test_insert_above_takes_the_number_and_shifts_the_rest(self):
        """Insertar en 1.x.2 recorre a las siguientes."""
        T = self.env["project.task"].with_user(self.capturista)
        raiz = self.paquete.wbs_code
        nueva = T.browse(T.planner_structure("insert", self.b.id))
        self.assertEqual(self._hijas(self.paquete),
                         [(raiz + ".1", "A"), (raiz + ".2", nueva.name), (raiz + ".3", "B")])
        self.assertEqual(nueva.planned_date_begin, self.b.planned_date_begin)
        debajo = T.browse(T.planner_structure("insert_below", self.a.id))
        self.assertEqual(debajo.wbs_code, raiz + ".2")
        self.assertEqual(nueva.wbs_code, raiz + ".3")

    def test_subtask_and_milestone(self):
        T = self.env["project.task"].with_user(self.capturista)
        hija = T.browse(T.planner_structure("add_child", self.b.id))
        self.assertEqual((hija.parent_id, hija.wbs_code), (self.b, self.b.wbs_code + ".1"))
        hito = T.browse(T.planner_structure("add_milestone", self.a.id))
        self.assertTrue(hito.is_milestone)
        self.assertEqual(hito.planned_date_begin, hito.date_deadline)
        T.planner_structure("toggle_milestone", hito.id)
        self.assertFalse(hito.is_milestone)
        self.assertGreater(hito.date_deadline, hito.planned_date_begin)

    def test_indent_outdent_and_move(self):
        T = self.env["project.task"].with_user(self.capturista)
        raiz = self.paquete.wbs_code
        T.planner_structure("indent", self.b.id)
        self.assertEqual((self.b.parent_id, self.b.wbs_code), (self.a, raiz + ".1.1"))
        T.planner_structure("outdent", self.b.id)
        self.assertEqual((self.b.parent_id, self.b.wbs_code), (self.paquete, raiz + ".2"))
        T.planner_structure("up", self.b.id)
        self.assertEqual((self.b.wbs_code, self.a.wbs_code), (raiz + ".1", raiz + ".2"))
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            T.planner_structure("indent", self.b.id)  # ya es la primera: no hay hermana arriba
        with self.assertRaises(UserError):
            T.planner_structure("outdent", self.paquete.id)

    def test_delete_takes_the_subtasks_and_renumbers(self):
        T = self.env["project.task"].with_user(self.capturista)
        hija = T.browse(T.planner_structure("add_child", self.a.id))
        raiz = self.paquete.wbs_code
        self.assertEqual(T.planner_structure("delete", self.a.id), 2)
        self.assertFalse(hija.exists())
        self.assertEqual(self.b.wbs_code, raiz + ".1")

    def test_the_view_is_in_the_standard_projects_app(self):
        """Portable: el planificador aparece en las tareas de cualquier proyecto."""
        accion = self.env.ref("project.act_project_project_2_project_task_all")
        self.assertIn("planner", accion.view_ids.mapped("view_mode"))

    def test_the_project_form_opens_the_planner(self):
        """Botón «Planificador» en la ficha del proyecto (también en Community):
        acción cliente con el proyecto en `params` y en `active_id`, que es lo
        único que sobrevive a recargar la página."""
        accion = self.proyecto.with_user(self.capturista).action_open_planner()
        self.assertEqual((accion["type"], accion["tag"]), ("ir.actions.client", "schedule_planner"))
        self.assertEqual(accion["params"]["project_id"], self.proyecto.id)
        self.assertEqual(accion["context"]["active_id"], self.proyecto.id)
        vista = self.env.ref("project_planner.project_project_view_form_planner")
        self.assertIn('name="action_open_planner"', vista.arch_db)

    def test_a_private_project_is_not_opened_for_a_non_follower(self):
        """El botón no abre un proyecto que el usuario no puede ver."""
        privado = self.env["project.project"].create({"name": "Privado", "privacy_visibility": "followers"})
        with self.assertRaises(AccessError):
            privado.with_user(self.capturista).action_open_planner()

    def test_a_user_without_project_rights_gets_nothing(self):
        ajeno = self.env["res.users"].create({"name": "sched sin proyecto", "login": "sched_none",
                                              "groups_id": [(6, 0, [self.env.ref("base.group_user").id])]})
        with self.assertRaises(AccessError):
            self.env["project.task"].with_user(ajeno).planner_data(self.dominio)

    def test_duration_is_typed_in_working_days(self):
        """Cinco días de 8 h de trabajo desde el lunes 2-nov a las
        14:00 (calendario 8–12 y 13–17) terminan el lunes 9 a las 14:00 (180 +
        4×480 + 300 minutos): se
        cuentan MINUTOS de trabajo, como en MS Project."""
        self.env.company.resource_calendar_id.tz = "UTC"
        self.env["project.task"].with_user(self.capturista).planner_set_duration(self.a.id, 5)
        self.assertEqual(self.a.duration_days, 5.0)
        self.assertEqual(str(self.a.date_deadline), "2026-11-09 14:00:00")

    def test_the_planner_gets_the_project_calendar(self):
        """El planificador sombrea los días no laborables DEL CALENDARIO
        del proyecto (antes, sábado y domingo fijos) y sus feriados."""
        cal = self.env["resource.calendar"].create({"name": "L-S", "tz": "UTC", "attendance_ids": [(5, 0, 0)] + [
            (0, 0, {"name": "T", "dayofweek": str(d), "hour_from": 8, "hour_to": 16, "day_period": "morning"}) for d in range(6)]})
        self.env["resource.calendar.leaves"].create({
            "name": "Feriado", "calendar_id": cal.id, "resource_id": False,
            "date_from": "2026-11-16 00:00:00", "date_to": "2026-11-16 23:59:00"})
        self.proyecto.schedule_calendar_id = cal
        calendario = self._datos()["calendar"]
        self.assertEqual((calendario["id"], calendario["name"]), (cal.id, "L-S"))
        self.assertEqual(calendario["off_weekdays"], [6], "trabaja sábados: solo el domingo es no laborable")
        self.assertIn("2026-11-16", calendario["holidays"])

    def test_several_projects_have_no_single_calendar(self):
        otro = self.env["project.project"].create({"name": "Otro"})
        self.env["project.task"].create({"name": "X", "project_id": otro.id})
        datos = self.env["project.task"].planner_data([("project_id", "in", [self.proyecto.id, otro.id])])
        self.assertFalse(datos["calendar"])

    def test_the_deadline_travels_to_the_planner(self):
        """La fecha límite se marca en la barra."""
        self.b.finish_deadline = "2026-11-12 23:00:00"
        filas = {t["name"]: t for t in self._datos()["tasks"]}
        self.assertEqual(filas["B"]["deadline"], "2026-11-12T23:00:00Z")
        self.assertFalse(filas["A"]["deadline"])

    def test_the_planner_gets_what_the_extra_columns_show(self):
        """Holgura y fechas reales para las columnas configurables."""
        self.a.write({"actual_start": "2026-11-02 14:00:00"})
        filas = {t["name"]: t for t in self._datos()["tasks"]}
        self.assertEqual(filas["A"]["actual_start"], "2026-11-02T14:00:00Z")
        self.assertFalse(filas["A"]["actual_finish"])
        self.assertIn("float", filas["B"])
