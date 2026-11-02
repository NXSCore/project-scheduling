# -*- coding: utf-8 -*-
"""La estructura EDT de las tareas y el Gantt en orden EDT, para cualquier proyecto.
"""
from odoo import _, api, fields, models
from odoo.tools import LazyTranslate

_lt = LazyTranslate(__name__)


class ProjectTask(models.Model):
    _inherit = "project.task"

    # El Gantt del cronograma agrupa cada
    # tarea bajo su PAQUETE — la tarea raíz de su rama —, así el paquete y sus
    # subtareas se ven juntos y se pliegan con un clic. Una tarea sin padre es
    # su propio paquete. store=True porque el Gantt agrupa por él (un
    # `read_group` necesita columna) y recursive porque la raíz de una
    # subtarea depende de la de su padre.
    wbs_root_id = fields.Many2one(
        "project.task", string="Package", compute="_compute_wbs_root_id",
        store=True, recursive=True, index=True,
        help="Top task of this task's branch: the schedule Gantt groups by it.")

    @api.depends("parent_id", "parent_id.wbs_root_id")
    def _compute_wbs_root_id(self):
        for task in self:
            task.wbs_root_id = task.parent_id.wbs_root_id if task.parent_id else task

    # Agrupar y plegar en VARIOS niveles. El
    # nivel N agrupa cada tarea del nivel N que TIENE subtareas con toda su
    # rama. Las que no se desglosan —el propio paquete y sus hojas— van
    # al grupo VACÍO del nivel, que el Gantt rotula «Tareas sin desglose»
    # (`falsy_value_label`), para que el encabezado no repita el nombre del
    # paquete.
    wbs_depth = fields.Integer(
        string="Outline Level", compute="_compute_wbs_levels", store=True, recursive=True,
        help="1 for a package, 2 for its subtasks, and so on.")
    wbs_level2_id = fields.Many2one(
        "project.task", string="Group (Level 2)", compute="_compute_wbs_levels",
        store=True, recursive=True, index=True, falsy_value_label=_lt("Tasks without breakdown"),
        help="Second-level group of the schedule Gantt: the subtask that holds this branch.")
    wbs_level3_id = fields.Many2one(
        "project.task", string="Group (Level 3)", compute="_compute_wbs_levels",
        store=True, recursive=True, index=True, falsy_value_label=_lt("Tasks without breakdown"),
        help="Third-level group of the schedule Gantt.")

    @api.depends("parent_id", "child_ids", "parent_id.wbs_depth",
                 "parent_id.wbs_level2_id", "parent_id.wbs_level3_id")
    def _compute_wbs_levels(self):
        for task in self:
            padre = task.parent_id
            profundidad = padre.wbs_depth + 1 if padre else 1
            # Nivel k: por encima de k, sin grupo; en k, la propia tarea si se
            # desglosa (si no, sin grupo); por debajo de k, el de su padre.
            if profundidad < 2:
                nivel2 = False
            elif profundidad == 2:
                nivel2 = task if task.child_ids else False
            else:
                nivel2 = padre.wbs_level2_id
            if profundidad < 3:
                nivel3 = False
            elif profundidad == 3:
                nivel3 = task if task.child_ids else False
            else:
                nivel3 = padre.wbs_level3_id
            task.wbs_depth = profundidad
            task.wbs_level2_id = nivel2
            task.wbs_level3_id = nivel3

    # El código EDT (`wbs_code`) y el hito de 0 días
    # (`is_milestone`) viven en `project_dependency`, el núcleo genérico
    # de programación: el planificador los necesita sin este módulo.

    # El código EDT delante del nombre, SOLO donde se pide —el Gantt del
    # cronograma pone la clave en su contexto—; en el resto de Odoo la tarea
    # se sigue llamando como se llama.
    # Sin `@api.depends` propio: reemplazaría el de `BaseModel` (`_rec_name`)
    # en vez de sumarse. Mismo patrón que hr_timesheet/models/project_task.py:224.
    @api.depends_context("wbs_numbering")
    def _compute_display_name(self):
        super()._compute_display_name()
        if self.env.context.get("wbs_numbering"):
            for task in self.filtered("wbs_code"):
                task.display_name = "%s %s" % (task.wbs_code, task.display_name)

    @api.model
    def get_gantt_data(self, domain, groupby, read_specification, limit=None, offset=0, unavailability_fields=None,
                       progress_bar_fields=None, start_date=None, stop_date=None, scale=None):
        """En el cronograma, grupos y filas en orden EDT.

        Odoo ordena los grupos por el `_order` de `project.task` —prioridad
        primero, ids al revés (project_task.py:104)— y así un paquete «1»
        podía salir debajo del «9». Se reordena el resultado ya armado por
        `web_gantt` (models.py:102-157), sin tocar su JS: los grupos por el
        código de cada nivel, con «Tareas sin desglose» primero, y dentro de
        cada grupo las filas por código. La tarea que se desglosa se marca
        como resumen, que es como MS Project llama a esa fila."""
        res = super().get_gantt_data(
            domain, groupby, read_specification, limit=limit, offset=offset,
            unavailability_fields=unavailability_fields, progress_bar_fields=progress_bar_fields,
            start_date=start_date, stop_date=stop_date, scale=scale)
        if not self.env.context.get("wbs_numbering"):
            return res
        campos = [g.split(":")[0] for g in groupby or []]
        ids = {r["id"] for r in res["records"]}
        for grupo in res["groups"]:
            ids.update(grupo[c][0] for c in campos if c in grupo and grupo[c] and self._fields[c].comodel_name == self._name)
        tareas = self.browse(ids)
        codigos = dict(zip(tareas.ids, tareas.mapped("wbs_code")))
        resumen = set(tareas.filtered("child_ids").ids)

        def orden(tarea_id):
            codigo = codigos.get(tarea_id)
            return tuple(int(p) for p in codigo.split(".")) if codigo else (float("inf"),)

        def orden_grupo(grupo):
            # Grupo vacío (sin desglose) = tupla vacía: va antes que cualquier rama.
            return tuple(orden(grupo[c][0]) if grupo.get(c) else () for c in campos)

        if all(c in self._fields and self._fields[c].comodel_name == self._name for c in campos):
            res["groups"].sort(key=orden_grupo)
        res["records"].sort(key=lambda r: orden(r["id"]))
        for grupo in res["groups"]:
            grupo["__record_ids"] = sorted(grupo.get("__record_ids", []), key=orden)
        for registro in res["records"]:
            if registro["id"] in resumen and "display_name" in registro:
                registro["display_name"] = _("%s (summary)", registro["display_name"])
        return res
