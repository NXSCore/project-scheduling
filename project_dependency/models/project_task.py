# -*- coding: utf-8 -*-
"""La ruta crítica: el camino sin holgura entre el inicio y el fin.

Calcularla exige saber el TIPO de cada vínculo, y Odoo no lo guarda.

La holgura sale en DÍAS LABORABLES del calendario del proyecto y la
calcula el motor (`scheduler.slack`), como la «Holgura total» de MS Project.
"""
from datetime import timedelta

import pytz

from odoo import _, api, fields, models

from .scheduler import CONSTRAINT_TYPES, calendar_for, schedule, slack, working_days


class ProjectTask(models.Model):
    _inherit = "project.task"

    # Numeración EDT/WBS (1, 1.2, 1.2.1…).
    # Es el «Outline Number» de Microsoft Project, y se GUARDA porque la
    # importación/exportación de MS Project que viene la va a necesitar como
    # dato, no solo como etiqueta. Orden entre hermanas: `sequence` y luego
    # `id` —el orden de captura—, nunca la fecha: en MS Project mover una
    # tarea en el tiempo no la renumera, y aquí tampoco.
    wbs_code = fields.Char(
        string="WBS Code", compute="_compute_wbs_code", store=True, recursive=True, index=True,
        help="Outline number of the task in its project (1, 1.2, 1.2.1...), as Microsoft Project numbers it.")

    # `project_id.tasks.*`: una tarea raíz se numera por su lugar entre las
    # raíces del proyecto, así que cambiar la secuencia o el padre de
    # CUALQUIER tarea del proyecto puede moverla. `tasks` y no `task_ids`:
    # `tasks` es el One2many sin dominio (project_project.py:107).
    @api.depends("project_id", "parent_id", "sequence", "parent_id.wbs_code",
                 "parent_id.child_ids.sequence", "project_id.tasks.sequence", "project_id.tasks.parent_id")
    def _compute_wbs_code(self):
        def clave(t):
            return (t.sequence, t.id or 0)

        proyectos = self.filtered(lambda t: not t.parent_id).project_id
        raices = self.search([("project_id", "in", proyectos.ids), ("parent_id", "=", False)]) if proyectos else self.browse()
        posicion = {}
        for proyecto in proyectos:
            # B023: la lambda se evalúa en esta misma vuelta, no se guarda.
            for i, raiz in enumerate(sorted(raices.filtered(lambda t: t.project_id == proyecto), key=clave), 1):  # noqa: B023
                posicion[raiz.id] = i
        for task in self:
            if not task.project_id:
                task.wbs_code = False
            elif task.parent_id:
                hermanas = sorted(task.parent_id.child_ids, key=clave)
                lugar = hermanas.index(task) + 1 if task in hermanas else len(hermanas) + 1
                task.wbs_code = "%s.%s" % (task.parent_id.wbs_code or "0", lugar)
            else:
                task.wbs_code = str(posicion.get(task.id, len(posicion) + 1))

    # El hito, como en MS Project, Primavera P6 y Open
    # Planner Studio: dura CERO días (inicio = fin) y conserva sus vínculos.
    # Vive aquí, en el núcleo genérico, para que el planificador sea
    # portable a cualquier proyecto de Odoo.
    # «Is a Milestone» y no «Milestone»: así se llama `milestone_id` (el hito de
    # proyecto nativo, otra cosa) y Odoo avisa de la etiqueta repetida al instalar.
    is_milestone = fields.Boolean(
        string="Is a Milestone", copy=False,
        help="A milestone lasts zero days, as in Microsoft Project: its finish is its start.")

    # Restricciones de fecha de MS Project. ASAP («lo antes posible») es
    # el valor por omisión; las demás las aplica el motor (`scheduler.py`).
    constraint_type = fields.Selection(
        CONSTRAINT_TYPES, string="Constraint", default="asap", required=True, copy=False,
        help="Date constraint applied when the schedule is calculated, as in Microsoft Project.")
    constraint_date = fields.Datetime(
        string="Constraint Date", copy=False,
        help="Date the constraint refers to. Not used by As Soon / As Late As Possible.")

    # Programación MANUAL y fechas REALES, como MS Project: el cálculo no
    # mueve una tarea manual ni lo que ya ocurrió (una terminada queda en sus
    # fechas reales; una en curso conserva su inicio real).
    manually_scheduled = fields.Boolean(
        string="Manually Scheduled", copy=False,
        help="The calculation does not move this task; it still constrains its neighbours.")
    actual_start = fields.Datetime(string="Actual Start", copy=False)
    actual_finish = fields.Datetime(string="Actual Finish", copy=False)

    # La duración en días LABORABLES, guardada, como en MS Project. Se
    # recalcula cuando cambian las fechas (con el calendario del proyecto);
    # cambiar el calendario NO la toca —las fechas se ajustan al «Calcular»—.
    # La importación de MS Project la escribe desde `<Duration>`.
    duration_days = fields.Float(
        string="Duration (working days)", digits=(16, 1),
        compute="_compute_duration_days", store=True, readonly=False,
        help="Working days of the task in its project's calendar. Zero for a milestone.")

    @api.depends("planned_date_begin", "date_deadline", "is_milestone", "project_id")
    def _compute_duration_days(self):
        for proyecto, tareas in self.grouped("project_id").items():
            fechas = [d for t in tareas for d in (t.planned_date_begin, t.date_deadline) if d]
            if not fechas:
                for t in tareas:
                    t.duration_days = 0.0
                continue
            registro = proyecto._work_calendar_record() if proyecto else self.env.company.resource_calendar_id
            cal, tz = calendar_for(registro, min(fechas).date() - timedelta(days=2), max(fechas).date() + timedelta(days=2))
            mpd = (proyecto.minutes_per_day if proyecto else 0) or 480
            for t in tareas:
                t.duration_days = working_days(cal, tz, t.planned_date_begin, t.date_deadline, t.is_milestone, mpd)

    def _set_planned_duration(self, days):
        """Cambiar la duración mueve el FIN con el calendario del
        proyecto, minuto a minuto (el inicio se queda), como en MS Project."""
        self.ensure_one()
        if self.is_milestone or not self.planned_date_begin or days <= 0:
            return
        registro = self.project_id._work_calendar_record() if self.project_id else self.env.company.resource_calendar_id
        mpd = (self.project_id.minutes_per_day if self.project_id else 0) or 480
        inicio = self.planned_date_begin
        cal, tz_name = calendar_for(registro, inicio.date() - timedelta(days=2), inicio.date() + timedelta(days=int(days) * 3 + 60))
        tz = pytz.timezone(tz_name)
        s_local = pytz.utc.localize(inicio).astimezone(tz).replace(tzinfo=None)
        fin_local = cal.add(s_local, round(days * mpd))
        fin = tz.localize(fin_local).astimezone(pytz.utc).replace(tzinfo=None)
        self.write({"date_deadline": max(fin, inicio), "duration_days": float(days)})

    # ------------------------------------------------------------ motor
    @api.model
    def scheduler_run(self, domain, apply=False):
        """Calcula el cronograma de las tareas de `domain` (y de sus proyectos
        completos: un vínculo hacia una tarea que el filtro dejó fuera también
        cuenta). Sin `apply` solo DEVUELVE los cambios —vista previa—; con
        `apply`, los escribe con los permisos del usuario, por el `write()` de
        siempre (rastro en el chatter y reglas del cronograma incluidas).
        """
        proyectos = self.search(domain or []).project_id
        if not proyectos:
            return {"changes": [], "conflicts": [], "skipped_links": 0}
        if apply:
            self.check_access("write")
        entrada = self._scheduler_input(proyectos)
        if not entrada["dates"]:
            return {"changes": [], "conflicts": [], "skipped_links": len(entrada["links"])}
        tareas, datos, vinculos = entrada["tasks"], entrada["data"], entrada["links"]
        hijas = entrada["parents"]
        cal, tz, mpd, opciones = entrada["cal"], entrada["tz"], entrada["mpd"], entrada["options"]
        motivos = {}
        nuevas, conflictos, omitidos = schedule(datos, vinculos, cal, tz, mpd, project=opciones, drivers=motivos)
        por_id = {t.id: t for t in tareas}
        cambios = []
        for i, (ini, fin) in nuevas.items():
            t = por_id[i]
            if (ini, fin) != (t.planned_date_begin, t.date_deadline):
                cambios.append({"id": i, "code": t.wbs_code or "", "name": t.name,
                                "old_start": t.planned_date_begin, "old_end": t.date_deadline,
                                "new_start": ini, "new_end": fin, "summary": t.id in hijas,
                                "reason": self._driver_label(motivos.get(i), t.id in hijas,
                                                                t.planned_date_begin == ini)})
        cambios.sort(key=lambda c: tuple(int(x) for x in (c["code"] or "0").split(".")))
        if apply:
            for c in cambios:
                # La duración se escribe junto con las fechas: es el DATO del
                # cálculo, no algo a deducir otra vez de las fechas nuevas.
                vals = {"planned_date_begin": c["new_start"], "date_deadline": c["new_end"]}
                if not c["summary"]:
                    vals["duration_days"] = por_id[c["id"]].duration_days
                por_id[c["id"]].write(vals)
        fmt = lambda d: d and d.isoformat() + "Z"
        etiquetas = dict(CONSTRAINT_TYPES)
        return {
            "changes": [{**c, "old_start": fmt(c["old_start"]), "old_end": fmt(c["old_end"]),
                         "new_start": fmt(c["new_start"]), "new_end": fmt(c["new_end"])} for c in cambios],
            "conflicts": [{"id": c["task"], "code": por_id[c["task"]].wbs_code or "",
                           "name": por_id[c["task"]].name, "constraint": etiquetas[c["constraint"]],
                           "date": c["date"].isoformat()} for c in conflictos],
            "skipped_links": len(omitidos),
            "applied": bool(apply),
        }

    @api.model
    def scheduler_simulate(self, proyecto, cambios):
        """«Vista de Simulación». Mueve en MEMORIA las tareas de `cambios`
        ({id: {"start": datetime UTC, "duration": días}}), recalcula el cronograma y la ruta crítica con el mismo motor
        y devuelve el fin antes y después, las tareas que se mueven y las críticas. No escribe nada: aplicar es la
        reprogramación con su versión y su aprobación."""
        entrada = self._scheduler_input(proyecto)
        if not entrada["dates"]:
            return {"finish_before": False, "finish_after": False, "changes": [], "critical_ids": []}
        datos = {i: dict(d) for i, d in entrada["data"].items()}
        for tarea_id, cambio in cambios.items():
            d = datos.get(tarea_id)
            if not d:
                continue
            if cambio.get("start"):
                # Mover el inicio = «no comenzar antes de» esa fecha, y la tarea deja de ser manual para que el motor la
                # reprograme con sus vínculos.
                d.update(constraint="snet", constraint_date=cambio["start"], manual=False)
            if cambio.get("duration"):
                d["duration"] = cambio["duration"]
        args = (entrada["links"], entrada["cal"], entrada["tz"], entrada["mpd"])
        motivos = {}
        nuevas, _conflictos, _omitidos = schedule(datos, *args, project=entrada["options"], drivers=motivos)
        for tarea_id, (ini, fin) in nuevas.items():
            datos[tarea_id].update(start=ini, end=fin)
        holguras = slack(datos, *args, project=entrada["options"])
        antes = max((d["end"] for d in entrada["data"].values() if d["end"]), default=False)
        despues = max((d["end"] for d in datos.values() if d["end"]), default=False)
        por_id = {t.id: t for t in entrada["tasks"]}
        movidas = [{"task": por_id[i], "old_start": entrada["data"][i]["start"], "old_end": entrada["data"][i]["end"],
                    "new_start": ini, "new_end": fin,
                    # Lo que fija la fecha, con el cambio simulado (una tarea movida a mano es su
                    # restricción «no antes de»).
                    "reason": self._driver_label(motivos.get(i), i in entrada["parents"],
                                                    entrada["data"][i]["start"] == ini)}
                   for i, (ini, fin) in nuevas.items()
                   if (ini, fin) != (entrada["data"][i]["start"], entrada["data"][i]["end"])]
        return {"finish_before": antes, "finish_after": despues, "changes": movidas,
                "critical_ids": [i for i, h in holguras.items() if h.get("critical")]}

    def _schedule_baseline(self):
        """La línea base de `self`, id → (inicio, fin) UTC naive, para la
        salud del cronograma (puntos 8, 11, 13 y 14 de la DCMA). El motor no
        sabe de líneas base: un módulo del dominio que las tenga lo
        redefine. Sin línea base, esos puntos salen «no
        aplica» en vez de inventarse."""
        return {}

    def _schedule_progress(self):
        """El avance de `self`, id → porcentaje (0-100), para los reportes
        del cronograma. El motor solo sabe de fechas reales (terminada = 100,
        iniciada = algo); un dominio que mida el avance de otra forma lo
        redefine (p. ej., con el avance físico)."""
        return {t.id: 100.0 if t.actual_finish else (1.0 if t.actual_start else 0.0) for t in self}

    # ------------------------------------------------- por qué se mueve
    @api.model
    def _driver_label(self, motivo, resumen=False, mismo_inicio=False):
        """El motivo que anotó el motor (`schedule(drivers=…)`), en palabras.

        No se adivina: si el motor no anotó
        nada, se dice que no se pudo establecer. «Su propio inicio» con el
        inicio intacto y el fin movido es su duración o el calendario: el motor
        no guarda el estado anterior para distinguir cuál de los dos.
        """
        _ = self.env._
        if resumen:
            return _("Summary: follows its subtasks")
        if not motivo:
            return _("Reason not established")
        tipo = motivo["kind"]
        if tipo == "predecessor":
            nombres = self.browse(motivo["preds"]).exists().mapped(
                lambda t: " ".join(filter(None, [t.wbs_code, t.name])))
            if len(nombres) > 1:
                return _("Predecessors (%(count)s): %(names)s", count=len(nombres), names=", ".join(nombres))
            return _("Predecessor: %s", ", ".join(nombres))
        if tipo == "constraint":
            etiqueta = dict(self._fields["constraint_type"]._description_selection(self.env)).get(motivo["constraint"])
            return _("Date constraint: %s", etiqueta)
        if tipo == "own_start":
            return _("Its own duration or the calendar") if mismo_inicio else _("Its own start date")
        return {
            "manual": _("Manually scheduled"),
            "actual": _("Actual dates"),
            "progress": _("Progress: it already started"),
            "from_finish": _("Scheduled back from the project finish"),
            "alap": _("As late as possible"),
        }.get(tipo, _("Reason not established"))

    @api.model
    def scheduler_driving_links(self, domain):
        """Los vínculos que MANDAN —los que fijan el inicio de su
        sucesora en el cálculo— entre las tareas de `domain`, como pares
        [predecesora, sucesora]. El planificador los resalta al trazar la ruta.
        Mide el cálculo, no las
        fechas guardadas: si el cronograma no está calculado, dice qué mandaría
        al calcular."""
        tareas = self.search(domain or [])
        if not tareas.project_id:
            return []
        visibles = set(tareas.ids)
        pares = set()
        for proyecto in tareas.project_id:
            entrada = self._scheduler_input(proyecto)
            if not entrada["dates"]:
                continue
            motivos = {}
            schedule(entrada["data"], entrada["links"], entrada["cal"], entrada["tz"], entrada["mpd"],
                     project=entrada["options"], drivers=motivos)
            for motivo in motivos.values():
                pares.update(par for par in motivo.get("links", ()) if set(par) <= visibles)
        return sorted([list(par) for par in pares])

    @api.model
    def _scheduler_input(self, proyectos):
        """Lo que el motor necesita de las tareas de `proyectos`: lo comparten
        «Calcular» (`scheduler_run`) y la ruta crítica."""
        tareas = self.search([("project_id", "in", proyectos.ids)])
        hijas = set(tareas.parent_id.ids)
        datos = {t.id: {
            "start": t.planned_date_begin, "end": t.date_deadline, "milestone": t.is_milestone,
            "summary": t.id in hijas, "parent": t.parent_id.id,
            "constraint": t.constraint_type or "asap", "constraint_date": t.constraint_date,
            "duration": t.duration_days, "manual": t.manually_scheduled,
            "actual_start": t.actual_start, "actual_finish": t.actual_finish,
            "deadline": t.finish_deadline,
        } for t in tareas}
        # sudo(): el cálculo necesita TODOS los vínculos del proyecto —saltarse
        # uno por permisos daría fechas y holguras falsas—; solo alimenta el
        # cálculo. Lo que se escribe, se escribe sin sudo.
        vinculos = [{"pred": v.predecessor_id.id, "succ": v.successor_id.id, "type": v.link_type,
                     "lag": v.lag_days, "elapsed": v.lag_elapsed}
                    for v in self.env["project.dependency"].sudo().search([("successor_id", "in", tareas.ids)])]
        fechas = [d for t in tareas for d in (t.planned_date_begin, t.date_deadline) if d]
        entrada = {"tasks": tareas, "data": datos, "links": vinculos, "parents": hijas, "dates": fechas}
        if not fechas:
            return entrada
        # El calendario del PROYECTO (el de la compañía si no tiene).
        registro = proyectos[:1]._work_calendar_record()
        cal, tz = calendar_for(registro, min(fechas).date() - timedelta(days=400),
                               max(fechas).date() + timedelta(days=4000))
        p0 = proyectos[:1]
        entrada.update({
            "cal": cal, "tz": tz, "mpd": p0.minutes_per_day or 480,
            "options": {"from_start": p0.schedule_from != "finish", "finish": p0.project_finish,
                        "honor_constraints": p0.honor_constraints},
        })
        return entrada

    def _collapse_milestone_dates(self, only_end_moved=False):
        """Un hito dura cero días: inicio = fin. Si solo se movió el fin (p. ej.
        desde el Gantt de Odoo), el inicio lo sigue; en cualquier otro caso el
        fin sigue al inicio."""
        for tarea in self.filtered(lambda t: t.is_milestone and t.planned_date_begin and t.date_deadline
                                   and t.planned_date_begin != t.date_deadline):
            sync = tarea.with_context(milestone_sync=True)
            if only_end_moved:
                sync.planned_date_begin = tarea.date_deadline
            else:
                sync.date_deadline = tarea.planned_date_begin

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("is_milestone") and vals.get("planned_date_begin"):
                vals["date_deadline"] = vals["planned_date_begin"]
        return super().create(vals_list)


    # La FECHA LÍMITE de MS Project (`Deadline`). No es `date_deadline`,
    # que en Odoo es el fin planeado: esta no mueve la tarea, acota su fin
    # tardío, y la holgura negativa que deja la vuelve crítica.
    # La etiqueta NO es «Deadline»: así se llama `date_deadline` (el fin planeado)
    # y en es_MX los dos salían «Fecha límite» en el mismo formulario.
    finish_deadline = fields.Datetime(
        string="Finish Deadline",
        help="Date this task should finish by. It does not move the task; if the task cannot "
             "finish by then, its float turns negative and it joins the critical path.")

    predecessor_link_ids = fields.One2many(
        "project.dependency", "successor_id", string="Predecessors",
    )
    successor_link_ids = fields.One2many(
        "project.dependency", "predecessor_id", string="Successors",
    )
    total_float_days = fields.Float(
        string="Total Float (days)", compute="_compute_critical_path",
        digits=(6, 1),
        help="Working days this task can slip without delaying the project or missing a deadline "
             "(negative: it is already late), as Microsoft Project's Total Slack.",
    )
    # La holgura LIBRE (MS Project «Free Slack»), del mismo cálculo.
    free_float_days = fields.Float(
        string="Free Float (days)", compute="_compute_critical_path",
        digits=(6, 1),
        help="Working days this task can slip without delaying any of its successors. "
             "The part of the total float it does not share with the tasks after it.",
    )
    is_critical = fields.Boolean(
        string="On the Critical Path", compute="_compute_critical_path",
        search="_search_is_critical",
        help="A task with no float: if it slips, the whole project slips.",
    )
    early_finish = fields.Datetime(
        string="Earliest Finish", compute="_compute_critical_path",
    )
    late_finish = fields.Datetime(
        string="Latest Finish", compute="_compute_critical_path",
    )

    def _compute_critical_path(self):
        """Una pasada por PROYECTO, no una por tarea.

        La mide el MOTOR (`scheduler.slack`), en días LABORABLES del
        calendario del proyecto, con fechas tempranas y tardías como MS Project.

        Sin `@api.depends`: la holgura de una tarea depende de las fechas y los
        vínculos de TODA la red, no de campos suyos. Declarar esa dependencia
        obligaría a invalidar el proyecto entero cada vez que alguien toca una
        fecha; se recalcula al leer, que es cuando se mira.
        """
        for proyecto, tareas in self.grouped("project_id").items():
            resultado, mpd = {}, 480
            if proyecto:
                entrada = self.env["project.task"]._scheduler_input(proyecto)
                if entrada["dates"]:
                    mpd = entrada["mpd"]
                    resultado = slack(entrada["data"], entrada["links"], entrada["cal"], entrada["tz"],
                                      mpd, project=entrada["options"])
            for tarea in tareas:
                datos = resultado.get(tarea.id)
                tarea.total_float_days = round(datos["slack"] / mpd, 2) if datos else 0.0
                tarea.free_float_days = round(datos["free"] / mpd, 2) if datos and "free" in datos else 0.0
                tarea.is_critical = bool(datos and datos["critical"])
                tarea.early_finish = datos["ef"] if datos else False
                tarea.late_finish = datos["lf"] if datos else False
                tarea.critical_color = 1 if tarea.is_critical else 10

    # `decoration-warning` NO pinta la barra: dibuja un triangulito de 20x16
    # px en la esquina (`gantt_view.scss:471`). A escala mes, con barras de
    # pocos píxeles de alto, es invisible: no se distingue la ruta crítica
    # de lo demás. Para que se vea hay que cambiar el COLOR de la barra, y el
    # color del Gantt sale de un campo entero.
    #
    # Se deja como campo propio y no se toca `color` de la vista global: la
    # vista de Proyectos colorea por etapa a propósito, y quitárselo sería
    # decidir por un módulo que no es nuestro.
    critical_color = fields.Integer(
        string="Critical Path Color", compute="_compute_critical_path",
        help="Gantt colour index: one value for the critical path, another "
             "for tasks with float.",
    )

    def action_open_dependencies(self):
        """Editar los vínculos de ESTA tarea sin salir del Gantt.

        El conector del Gantt solo sabe expresar fin-a-inicio: es una flecha,
        no tiene dónde poner un tipo ni un desfase. Cambiar eso dentro del
        conector significaría bifurcar un componente OWL de Enterprise.

        Esto resuelve lo mismo por la puerta declarativa: un botón en el
        popover de la barra abre los vínculos de la tarea, editables en línea.
        Dos clics desde el Gantt, cero código de front-end que mantener cuando
        Odoo cambie el suyo.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Dependencies of %(task)s", task=self.display_name),
            "res_model": "project.dependency",
            "view_mode": "list",
            "target": "new",
            "domain": ["|", ("predecessor_id", "=", self.id),
                       ("successor_id", "=", self.id)],
            "context": {"default_successor_id": self.id},
        }

    def write(self, vals):
        """El Gantt dibuja la flecha; aquí se convierte en vínculo tipado.

        `project.dependency` sincroniza HACIA `depend_on_ids`; este `write()`
        cubre el sentido contrario. Sin él, el conector arrastrado en el Gantt
        crearía una dependencia que el CPM no ve.

        Un vínculo nacido del Gantt es fin-a-inicio sin desfase, que es lo único
        que el conector sabe expresar. El tipo se cambia después en la pestaña
        Dependencies.
        """
        anteriores = {t.id: set(t.depend_on_ids.ids) for t in self} if "depend_on_ids" in vals else {}
        resultado = super().write(vals)
        if anteriores:
            self._sync_links_from_native(anteriores)
        if {"is_milestone", "planned_date_begin", "date_deadline"} & set(vals) \
                and not self.env.context.get("milestone_sync"):
            self._collapse_milestone_dates(only_end_moved="date_deadline" in vals and "planned_date_begin" not in vals)
        return resultado

    def _sync_links_from_native(self, anteriores):
        # sudo(): es un espejo del `depend_on_ids` que el usuario ACABA de
        # escribir con sus propios permisos (el `super().write` de arriba); el
        # vínculo tipado no es una decisión nueva.
        Vinculo = self.env["project.dependency"].sudo()
        for tarea in self:
            ahora = set(tarea.depend_on_ids.ids)
            antes = anteriores.get(tarea.id, set())
            for nuevo in ahora - antes:
                if not Vinculo.search_count([("predecessor_id", "=", nuevo),
                                             ("successor_id", "=", tarea.id)]):
                    Vinculo.create({"predecessor_id": nuevo, "successor_id": tarea.id,
                                    "link_type": "fs", "lag_days": 0.0})
            # Quitar la flecha en el Gantt borra el vínculo, pero SOLO si era
            # de los que el Gantt representa. Un inicio-a-inicio no se dibuja,
            # así que su ausencia del campo nativo no significa que se quitó.
            for quitado in antes - ahora:
                Vinculo.search([
                    ("predecessor_id", "=", quitado), ("successor_id", "=", tarea.id),
                    ("link_type", "=", "fs"), ("lag_days", "=", 0.0),
                ]).unlink()

    def _search_is_critical(self, operator, value):
        """Para poder filtrar «solo la ruta crítica» en la vista."""
        criticas = self.search([("project_id", "!=", False)]).filtered("is_critical")
        positivo = (operator in ("=", "in")) == bool(value)
        return [("id", "in" if positivo else "not in", criticas.ids)]
