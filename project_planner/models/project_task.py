# -*- coding: utf-8 -*-
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.project_dependency.models.scheduler import calendar_for

#: Flecha nativa sin fila en `project.dependency`: fin-inicio sin desfase.
DEFAULT_LINK = {"type": "fs", "lag": 0.0}

#: Una predecesora escrita como en MS Project: `3`, `1.2.4SS`, `4FF+2d`,
#: `5FS-1,5d`. El desfase va en días; `dn`/`ed` = días naturales.
PRED_TOKEN = re.compile(
    r"^\s*(?P<code>\d+(?:\.\d+)*)\s*(?P<type>FS|SS|FF|SF|FC|CC|CF|FF)?\s*"
    r"(?:(?P<lag>[+-]\s*\d+(?:[.,]\d+)?)\s*(?P<unit>dn|ed|d|días|dias)?)?\s*$", re.IGNORECASE)
#: Las abreviaturas en español de MS Project (Fin-Comienzo…) a las nuestras.
TYPE_ALIASES = {"FC": "fs", "CC": "ss", "CF": "sf"}


class ProjectTask(models.Model):
    _inherit = "project.task"

    @api.model
    def planner_data(self, domain):
        """Todo lo que dibuja el planificador para las tareas de `domain`, en
        una sola llamada y con los permisos de quien lo abre (sin `sudo()`).

        Lo usan las dos entradas: la acción cliente (dominio = un
        cronograma) y la vista `planner` (dominio = la búsqueda). Si un
        filtro deja fuera al padre de una tarea, la tarea sube a raíz en vez
        de desaparecer; los vínculos solo se dibujan entre tareas visibles.
        """
        tareas = self.search(domain or [])
        tareas = tareas.sorted(lambda t: (t.project_id.id or 0, tuple(int(p) for p in (t.wbs_code or "0").split("."))))
        visibles = set(tareas.ids)
        con_hijas = set(tareas.filtered(lambda t: t.child_ids & tareas).ids)
        # Los vínculos tipados son `project.dependency` (motor
        # genérico de project_dependency). Una flecha nativa sin fila —
        # dibujada antes de instalar ese módulo— cuenta como fin-inicio.
        deps = self.env["project.dependency"].search([("successor_id", "in", tareas.ids)])
        attrs = {(d.successor_id.id, d.predecessor_id.id): d for d in deps}
        fecha = lambda d: d and d.isoformat() + "Z"
        etiquetas = dict(self._fields["constraint_type"]._description_selection(self.env))
        filas, vinculos = [], []
        for t in tareas:
            filas.append({
                "id": t.id,
                "code": t.wbs_code or "",
                "sequence": t.sequence,
                "name": t.name,
                "parent_id": t.parent_id.id if t.parent_id.id in visibles else False,
                "summary": t.id in con_hijas,
                "milestone": t.is_milestone,
                "start": fecha(t.planned_date_begin),
                "end": fecha(t.date_deadline),
                "progress": 0.0,
                "critical": bool(t.is_critical),
                "baseline_start": False,
                "baseline_end": False,
                "users": ", ".join(t.user_ids.mapped("name")),
                # La duración laborable guardada (manda sobre las fechas).
                "duration": t.duration_days,
                "manual": t.manually_scheduled,
                "actual": bool(t.actual_start),
                # Para las columnas del planificador.
                "actual_start": t.actual_start and t.actual_start.isoformat() + "Z",
                "actual_finish": t.actual_finish and t.actual_finish.isoformat() + "Z",
                "float": t.total_float_days,
                # La holgura libre, como columna opcional.
                "free_float": t.free_float_days,
                # El fin más TARDÍO del motor, donde termina la banda de
                # holgura (no fin + holgura: la holgura va en días laborables).
                "late_finish": fecha(t.late_finish),
                # La restricción de fecha (ASAP = ninguna).
                "constraint": t.constraint_type or "asap",
                "constraint_label": etiquetas.get(t.constraint_type or "asap"),
                "constraint_date": t.constraint_date and t.constraint_date.isoformat() + "Z",
                # La fecha límite (MS Project `Deadline`), marcada en la barra.
                "deadline": t.finish_deadline and t.finish_deadline.isoformat() + "Z",
                **t._planner_task_extra(),
            })
            preds = t.depend_on_ids | t.predecessor_link_ids.predecessor_id
            for pred in preds:
                if pred.id not in visibles:
                    continue
                link = attrs.get((t.id, pred.id))
                vinculos.append({
                    "from": pred.id, "to": t.id,
                    "type": link.link_type if link else DEFAULT_LINK["type"],
                    "lag": link.lag_days if link else DEFAULT_LINK["lag"],
                    "elapsed": bool(link and link.lag_elapsed),
                })
        proyectos = tareas.project_id
        # Se puede editar si el usuario puede escribir las tareas. Las
        # reglas finas de cada módulo de extensión las sigue
        # aplicando `write()`; esto solo decide si la vista ofrece editar.
        editable = bool(tareas) and tareas[:1].has_access("write")
        return {"baselines": self._planner_baselines(proyectos),
                "project": proyectos.display_name if len(proyectos) == 1 else "",
                "project_id": proyectos.id if len(proyectos) == 1 else False, "tasks": filas,
                "links": vinculos, "editable": editable,
                "calendar": self._planner_calendar(proyectos, tareas)}

    def _planner_calendar(self, proyectos, tareas):
        """El calendario laboral con el que el motor calcula, para que el
        planificador sombree los MISMOS días no laborables y lo muestre. Solo con
        un proyecto: varios proyectos
        pueden tener calendarios distintos."""
        if len(proyectos) != 1:
            return False
        cal = proyectos._work_calendar_record()
        fechas = [d for t in tareas for d in (t.planned_date_begin, t.date_deadline) if d]
        hoy = fields.Date.context_today(self)
        desde = min(fechas).date() if fechas else hoy
        hasta = max(fechas).date() if fechas else hoy
        work, _tz = calendar_for(cal, desde - timedelta(days=400), hasta + timedelta(days=400))
        return {
            "id": cal.id or False,
            "name": cal.name or self.env._("Monday to Friday"),
            # Días de la semana sin turnos, 0 = lunes (como `date.weekday()`).
            "off_weekdays": [d for d in range(7) if not work.turnos.get(d)],
            "holidays": sorted(d.isoformat() for d in work.holidays),
        }

    # ------------------------------------------------ líneas base
    #: Cuántas versiones se comparan además de la vigente.
    MAX_COMPARED_BASELINES = 2

    @api.model
    def _planner_baselines(self, proyectos):
        """Punto de extensión: las líneas base que se pueden comparar en el
        planificador, [{id, name, current}]. El planificador genérico no sabe
        de líneas base; un módulo del dominio lo redefine."""
        return []

    @api.model
    def _planner_baseline_dates(self, baseline_ids, tareas):
        """Punto de extensión: {línea base: {tarea: [inicio, fin] ISO UTC}}."""
        return {}

    @api.model
    def planner_baseline_dates(self, domain, baseline_ids):
        """Las fechas de hasta dos líneas base de comparación para las
        tareas de `domain` que el usuario ve. Solo se aceptan las que
        `_planner_baselines` ofrece para esos proyectos: un id ajeno
        escrito a mano no devuelve nada, aunque el puente lea con `sudo()`."""
        tareas = self.search(domain or [])
        ofrecidas = {b["id"] for b in self._planner_baselines(tareas.project_id)}
        pedidas = [b for b in (baseline_ids or []) if b in ofrecidas][:self.MAX_COMPARED_BASELINES]
        if not pedidas or not tareas:
            return {}
        return {str(b): {str(t): v for t, v in fechas.items()}
                for b, fechas in self._planner_baseline_dates(pedidas, tareas).items()}

    def _planner_task_extra(self):
        """Punto de extensión: lo que un dominio agrega a cada fila (avance,
        línea base…). El planificador genérico no conoce esos campos; un
        módulo puente redefine este método. Claves que entiende el cliente:
        `progress` (0–100), `baseline_start` y `baseline_end` (ISO UTC)."""
        self.ensure_one()
        return {}

    @staticmethod
    def _planner_utc(valor):
        return valor and valor.isoformat() + "Z"

    @api.model
    def planner_set_duration(self, task_id, days):
        """La duración en días laborables; el fin se mueve con el
        calendario del proyecto (el inicio se queda), como en MS Project."""
        tarea = self.browse(task_id).exists()
        if not tarea:
            raise UserError(_("The task no longer exists."))
        tarea.check_access("write")
        tarea._set_planned_duration(float(days))
        return True

    @api.model
    def planner_set_predecessors(self, task_id, text):
        """Las predecesoras de una tarea, escritas como en MS Project
        («1.3.1FS+3d; 1.2»). Reemplaza las que tenía: lo que no se escribe se
        quita, como al editar esa columna en MS Project.

        Escribe con los permisos de quien edita, sin `sudo()`: el vínculo de
        tipado (`project.dependency`); el nativo lo mantiene project_dependency.
        """
        tarea = self.browse(task_id).exists()
        if not tarea:
            raise UserError(_("The task no longer exists."))
        tarea.check_access("write")
        por_codigo = {t.wbs_code: t for t in self.search([("project_id", "=", tarea.project_id.id)]) if t.wbs_code}
        deseadas, errores = {}, []
        for token in filter(None, (p.strip() for p in re.split(r"[;]", text or ""))):
            m = PRED_TOKEN.match(token)
            pred = m and por_codigo.get(m["code"])
            if not m or not pred:
                errores.append(token)
                continue
            if pred == tarea:
                raise UserError(_("A task cannot depend on itself (%s).", token))
            tipo = (m["type"] or "FS").upper()
            lag = float((m["lag"] or "0").replace(" ", "").replace(",", "."))
            deseadas[pred.id] = {
                "link_type": TYPE_ALIASES.get(tipo, tipo.lower()),
                "lag_days": lag,
                "lag_elapsed": (m["unit"] or "").lower() in ("dn", "ed"),
            }
        if errores:
            raise UserError(_("These predecessors were not understood or do not exist in this schedule: %s",
                              ", ".join(errores)))
        # Se escribe el vínculo tipado; el campo nativo lo mantiene
        # project_dependency (solo los fin-inicio sin desfase). Los ciclos
        # los rechaza su propia restricción.
        Dep = self.env["project.dependency"]
        actuales = {d.predecessor_id.id: d for d in tarea.predecessor_link_ids}
        sobran = Dep.browse([d.id for p, d in actuales.items() if p not in deseadas])
        nativas_sueltas = tarea.depend_on_ids.filtered(lambda p: p.id not in deseadas and p.id not in actuales)
        if nativas_sueltas:
            tarea.depend_on_ids = [(3, p.id) for p in nativas_sueltas]
        sobran.unlink()
        nuevos = []
        for pred_id, vals in deseadas.items():
            if pred_id in actuales:
                actuales[pred_id].write(vals)
            else:
                nuevos.append({"successor_id": tarea.id, "predecessor_id": pred_id, **vals})
        Dep.create(nuevos)
        tarea.predecessor_link_ids._sync_native_dependency()
        # Si quitar un vínculo no-FS dejó su flecha nativa, también se va.
        sueltas = tarea.depend_on_ids.filtered(lambda p: p.id not in deseadas)
        if sueltas:
            tarea.depend_on_ids = [(3, p.id) for p in sueltas]
        return True

    # ------------------------------------------------------------ estructura
    def _planner_siblings(self):
        """Las hermanas de esta tarea en el orden del cronograma (el EDT)."""
        self.ensure_one()
        return self.search([("project_id", "=", self.project_id.id), ("parent_id", "=", self.parent_id.id)],
                           order="sequence, id")

    @api.model
    def _planner_resequence(self, tareas):
        """Numera 10, 20, 30… en el orden dado: el código EDT sale de
        `sequence`, así que queda consecutivo y sin huecos."""
        for i, t in enumerate(tareas, 1):
            if t.sequence != i * 10:
                t.sequence = i * 10

    # ------------------------------------------------------------ deshacer
    #: Lo que guarda una foto de una tarea (las claves de `planner_data`) →
    #: el campo que se escribe para volver a ese valor.
    UNDO_FIELDS = {
        "name": "name", "parent_id": "parent_id", "sequence": "sequence",
        "start": "planned_date_begin", "end": "date_deadline", "duration": "duration_days",
        "milestone": "is_milestone", "manual": "manually_scheduled", "constraint": "constraint_type",
        "constraint_date": "constraint_date", "deadline": "finish_deadline",
    }
    UNDO_DATES = {"start", "end", "constraint_date", "deadline"}

    def _undo_value(self, clave, valor):
        """Del formato del planificador (ISO UTC con «Z») al del ORM."""
        if clave in self.UNDO_DATES:
            return fields.Datetime.to_datetime(valor[:19].replace("T", " ")) if valor else False
        return valor

    def _undo_photo(self):
        """El valor ACTUAL de cada clave, en el formato del planificador."""
        self.ensure_one()
        utc = self._planner_utc
        return {
            "name": self.name, "parent_id": self.parent_id.id or False, "sequence": self.sequence,
            "start": utc(self.planned_date_begin), "end": utc(self.date_deadline),
            "duration": self.duration_days, "milestone": self.is_milestone, "manual": self.manually_scheduled,
            "constraint": self.constraint_type or "asap", "constraint_date": utc(self.constraint_date),
            "deadline": utc(self.finish_deadline),
        }

    @staticmethod
    def _undo_same(clave, a, b):
        if clave == "duration":
            return abs((a or 0.0) - (b or 0.0)) < 0.005
        if clave in ProjectTask.UNDO_DATES:
            return (a or "")[:19] == (b or "")[:19]
        return (a or False) == (b or False)

    def _current_links(self, ids):
        """Los vínculos entre `ids`, como los dibuja el planificador:
        (de, a) → {type, lag, elapsed}; una flecha nativa sin fila es FS sin desfase."""
        tareas = self.browse(ids).exists()
        filas = {(d.predecessor_id.id, d.successor_id.id): d for d in self.env["project.dependency"].search(
            [("successor_id", "in", tareas.ids), ("predecessor_id", "in", tareas.ids)])}
        actuales = {}
        for t in tareas:
            for pred in (t.depend_on_ids | t.predecessor_link_ids.predecessor_id) & tareas:
                d = filas.get((pred.id, t.id))
                actuales[(pred.id, t.id)] = {"type": d.link_type, "lag": d.lag_days, "elapsed": d.lag_elapsed} if d \
                    else {"type": DEFAULT_LINK["type"], "lag": DEFAULT_LINK["lag"], "elapsed": False}
        return actuales, filas

    @api.model
    def planner_restore(self, changes, direction="undo"):
        """Deshacer (o rehacer) una acción del planificador.

        `changes` = lo que cambió esa acción, como lo fotografió el cliente:
        `tasks` {id: {before, after}} y `links` {"de-a": {before, after}};
        `None` = no existía. Deshacer lleva cada cosa a `before`; rehacer, a
        `after`. Se escribe con los permisos del usuario, por el `write()` de
        siempre (chatter y reglas incluidos).

        No pisa trabajo ajeno: si lo que hay HOY no es lo que la acción dejó
        (alguien lo cambió después), esa tarea o ese vínculo se SALTA y se
        cuenta en `conflicts`. Una tarea que la acción creó se elimina al
        deshacer; una que ya no existe no se puede recrear (`missing`).
        """
        meta, esperado = ("before", "after") if direction == "undo" else ("after", "before")
        conflictos, faltan = 0, 0
        tareas = changes.get("tasks") or {}
        ids = [int(i) for i in tareas]
        existentes = {t.id: t for t in self.browse(ids).exists()}
        # 1) Tareas que la acción creó y hay que quitar (deshacer un «insertar»).
        borrar = self.browse()
        for sid, par in tareas.items():
            t = existentes.get(int(sid))
            if par.get(meta) is None and t:
                if par.get(esperado) and all(self._undo_same(k, t._undo_photo()[k], par[esperado].get(k))
                                             for k in self.UNDO_FIELDS if k in par[esperado]):
                    borrar |= t
                else:
                    conflictos += 1
        # 2) Tareas que vuelven a un estado: solo las claves que difieren.
        #    Primero el árbol (padre, orden), después las fechas.
        for etapa in (("parent_id", "sequence", "name"), tuple(k for k in self.UNDO_FIELDS
                                                                 if k not in ("parent_id", "sequence", "name"))):
            for sid, par in tareas.items():
                destino, previsto = par.get(meta), par.get(esperado) or {}
                if destino is None:
                    continue
                t = existentes.get(int(sid))
                if not t:
                    faltan += etapa[0] == "parent_id"
                    continue
                hoy = t._undo_photo()
                vals, choque = {}, False
                for k in etapa:
                    if k not in destino or self._undo_same(k, hoy[k], destino[k]):
                        continue
                    if k in previsto and not self._undo_same(k, hoy[k], previsto[k]):
                        choque = True
                        break
                    vals[self.UNDO_FIELDS[k]] = self._undo_value(k, destino[k])
                if choque:
                    conflictos += 1
                    continue
                if vals:
                    if "duration_days" in vals or "planned_date_begin" in vals or "date_deadline" in vals:
                        # La duración viaja con sus fechas: es el dato.
                        vals.setdefault("duration_days", destino.get("duration", t.duration_days))
                        vals.setdefault("planned_date_begin", self._undo_value("start", destino.get("start")))
                        vals.setdefault("date_deadline", self._undo_value("end", destino.get("end")))
                    t.write(vals)
        # 3) Vínculos.
        Dep = self.env["project.dependency"]
        enlaces = changes.get("links") or {}
        if enlaces:
            claves = [tuple(int(x) for x in k.split("-")) for k in enlaces]
            todos = {i for par in claves for i in par}
            actuales, filas = self._current_links(list(todos))
            for k, par in enlaces.items():
                clave = tuple(int(x) for x in k.split("-"))
                destino, previsto, hoy = par.get(meta), par.get(esperado), actuales.get(clave)
                if (hoy or None) == (destino or None) or (hoy and destino and hoy["type"] == destino["type"]
                                                          and abs(hoy["lag"] - destino["lag"]) < 0.005
                                                          and hoy["elapsed"] == destino["elapsed"]):
                    continue
                igual_a_previsto = (hoy is None and previsto is None) or (
                    hoy and previsto and hoy["type"] == previsto["type"] and abs(hoy["lag"] - previsto["lag"]) < 0.005
                    and hoy["elapsed"] == previsto["elapsed"])
                if not igual_a_previsto:
                    conflictos += 1
                    continue
                pred, suc = self.browse(clave[0]).exists(), self.browse(clave[1]).exists()
                if not (pred and suc):
                    faltan += 1
                    continue
                fila = filas.get(clave)
                if destino is None:
                    if fila:
                        fila.unlink()
                    else:
                        suc.depend_on_ids = [(3, pred.id)]
                else:
                    vals = {"link_type": destino["type"], "lag_days": destino["lag"], "lag_elapsed": destino["elapsed"]}
                    if fila:
                        fila.write(vals)
                    else:
                        Dep.create({"predecessor_id": pred.id, "successor_id": suc.id, **vals})._sync_native_dependency()
        if borrar:
            borrar.unlink()
        return {"conflicts": conflictos, "missing": faltan}

    @api.model
    def planner_structure(self, op, task_id):
        """Insertar, eliminar, sangría y orden, como en MS Project.

        - `insert` / `insert_below`: tarea nueva encima o debajo de la
          seleccionada, como su hermana; las siguientes se recorren. Un día de
          duración. `add_child`: subtarea al final. `add_milestone`: hito
          debajo, en el fin de la seleccionada. Devuelven el id nuevo.
        - `toggle_milestone`: hito ⇄ tarea de un día.
        - `delete`: borra la tarea y sus subtareas (lo hace `unlink()` de Odoo,
          project_task.py:1401-1403). Devuelve cuántas se borraron.
        - `indent`: la tarea pasa a ser la última subtarea de la hermana de
          arriba. `outdent`: sube un nivel y queda justo después de su padre.
        - `up` / `down`: cambia de lugar con la hermana de arriba o abajo.

        Con los permisos de quien edita, sin `sudo()`.
        """
        tarea = self.browse(task_id).exists()
        if not tarea:
            raise UserError(_("The task no longer exists."))
        if op in ("insert", "insert_below", "add_child", "add_milestone"):
            tarea.check_access("create")
            hito = op == "add_milestone"
            hija = op == "add_child"
            inicio = tarea.date_deadline if (hito or op == "insert_below") else tarea.planned_date_begin
            inicio = inicio or tarea.planned_date_begin
            nueva = self.create({
                "name": _("New Milestone") if hito else _("New Task"),
                "project_id": tarea.project_id.id,
                "parent_id": tarea.id if hija else (tarea.parent_id.id or False),
                "planned_date_begin": inicio,
                "date_deadline": inicio and (inicio if hito else inicio + timedelta(days=1)),
                "is_milestone": hito,
            })
            if hija:
                hijas = list((tarea.child_ids - nueva).sorted(lambda t: (t.sequence, t.id)))
                self._planner_resequence(hijas + [nueva])
            else:
                hermanas = list(tarea._planner_siblings() - nueva)
                i = hermanas.index(tarea) + (0 if op == "insert" else 1)
                self._planner_resequence(hermanas[:i] + [nueva] + hermanas[i:])
            return nueva.id
        if op == "toggle_milestone":
            tarea.check_access("write")
            if tarea.is_milestone:
                fin = tarea.planned_date_begin and tarea.planned_date_begin + timedelta(days=1)
                tarea.write({"is_milestone": False, "date_deadline": fin or tarea.date_deadline})
            else:
                tarea.write({"is_milestone": True, "date_deadline": tarea.planned_date_begin or tarea.date_deadline})
            return tarea.id
        tarea.check_access("write")
        if op == "delete":
            tarea.check_access("unlink")
            hermanas = tarea._planner_siblings() - tarea
            n = len(tarea | tarea._get_all_subtasks())
            tarea.unlink()
            self._planner_resequence(hermanas)
            return n
        hermanas = list(tarea._planner_siblings())
        i = hermanas.index(tarea)
        if op == "indent":
            if i == 0:
                raise UserError(_("There is no task above at the same level to indent under."))
            nuevo_padre = hermanas[i - 1]
            hijas = list(nuevo_padre.child_ids.sorted(lambda t: (t.sequence, t.id)))
            tarea.parent_id = nuevo_padre
            self._planner_resequence(hijas + [tarea])
            self._planner_resequence(hermanas[:i] + hermanas[i + 1:])
        elif op == "outdent":
            padre = tarea.parent_id
            if not padre:
                raise UserError(_("The task is already at the first level."))
            tios = list(padre._planner_siblings())
            j = tios.index(padre)
            tarea.parent_id = padre.parent_id
            self._planner_resequence(tios[:j + 1] + [tarea] + tios[j + 1:])
            self._planner_resequence(hermanas[:i] + hermanas[i + 1:])
        elif op in ("up", "down"):
            j = i - 1 if op == "up" else i + 1
            if 0 <= j < len(hermanas):
                hermanas[i], hermanas[j] = hermanas[j], hermanas[i]
                self._planner_resequence(hermanas)
        else:
            raise UserError(_("Unknown operation: %s", op))
        return tarea.id
