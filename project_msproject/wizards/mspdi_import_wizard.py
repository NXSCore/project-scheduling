# -*- coding: utf-8 -*-
"""`project.mspdi.import.wizard` — importar el XML de MS Project.

MS Project guarda su formato abierto con *Archivo → Guardar como → XML*
(MSPDI, documentado por Microsoft). Se lee aquí en Python, sin dependencias
nuevas: el `.mpp` binario no se lee, porque las librerías que lo hacen corren
sobre Java.

Qué entra y cómo:

- **Jerarquía**: `<OutlineLevel>` y el orden del documento, como lo arma MS
  Project. La tarea `<UID>0` es el resumen del proyecto y no se importa.
- **Orden EDT**: `sequence` sigue el orden del archivo, así que el código EDT
  queda igual al del archivo.
- **Fechas**: `<Start>`/`<Finish>` vienen en hora local sin zona; se leen en la
  zona del usuario que importa y se guardan en UTC, como todo Datetime.
- **Vínculos**: `<PredecessorLink>` con su tipo y desfase (`project.dependency`,
  el modelo de vínculos tipados de `project_dependency`).
  `<LinkLag>` viene en décimas de minuto; `<LagFormat>` dice si son días
  laborables o naturales (4, 6, 8, 10 y 12 son naturales).
- **Responsables**: `<Assignment>` + `<Resource>`, por nombre o correo contra
  los usuarios internos. El recurso que no coincide se reporta, no se inventa.
- **Una segunda importación ACTUALIZA** por `<UID>` (`ms_uid`) en vez de
  duplicar. Nunca borra: una tarea que ya no viene en el archivo se reporta.

Qué NO entra, y se dice en el resumen: el % completado (el avance de este
cronograma solo se registra con evidencia, `PROGRESS_SEAM`), calendarios,
líneas base y desfases en porcentaje. Las restricciones de fecha sí.

Importa a cualquier `project.project`. Las reglas de un dominio (cuándo se
permite importar, a quién avisar) las agrega un módulo de extensión
redefiniendo `_check_can_import()` y `_after_import()`.
"""
import base64
import re
from datetime import datetime

import pytz
from lxml import etree

from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.project_dependency.models.scheduler import MSPDI_CONSTRAINTS


#: Códigos de `<PredecessorLink><Type>` en el XML de MS Project (MSPDI).
MSPDI_LINK_TYPES = {0: "ff", 1: "fs", 2: "sf", 3: "ss"}
#: Tope del archivo. Un cronograma de miles de tareas pesa unos pocos MB.
MAX_FILE_BYTES = 20 * 1024 * 1024
#: `<LagFormat>` de días NATURALES (elapsed) en MSPDI.
ELAPSED_LAG_FORMATS = {4, 6, 8, 10, 12}
#: `<LagFormat>` en porcentaje: no hay dónde guardarlos.
PERCENT_LAG_FORMATS = {19, 20}


def _txt(el, tag):
    hijo = el.find("{*}" + tag)
    return hijo.text.strip() if hijo is not None and hijo.text else ""


def _int(el, tag, default=0):
    valor = _txt(el, tag)
    try:
        return int(valor) if valor else default
    except ValueError:
        return default


def _iso_hours(texto):
    """`PT160H0M0S` → 160.0 horas. MSPDI escribe la duración así."""
    m = re.match(r"^-?P(?:(\d+(?:\.\d+)?)D)?T?(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?$", texto or "")
    if not m:
        return 0.0
    d, h, mi, se = (float(x) if x else 0.0 for x in m.groups())
    return d * 24 + h + mi / 60 + se / 3600


class ReProjectMspdiImportWizard(models.TransientModel):
    _name = "project.mspdi.import.wizard"
    _description = "Import a Microsoft Project XML Schedule"

    project_id = fields.Many2one(
        "project.project", string="Project", required=True, readonly=True)
    file = fields.Binary(string="XML File", required=True)
    filename = fields.Char(string="File Name")
    state = fields.Selection([("draft", "Draft"), ("done", "Done")], default="draft")
    # Qué calendario usa el proyecto para calcular.
    calendar_mode = fields.Selection([
        ("file", "Create a calendar from the file"),
        ("company", "Use the company calendar"),
        ("keep", "Keep the project's current calendar"),
    ], string="Working Calendar", default="file", required=True,
        help="The file brings its working week and holidays. Creating a calendar from it makes "
             "the schedule calculate here as it did in Microsoft Project.")
    summary = fields.Text(string="Result", readonly=True)

    # ------------------------------------------------------------------ lectura
    def _parse(self):
        datos = base64.b64decode(self.file or b"")
        if len(datos) > MAX_FILE_BYTES:
            raise UserError(_("The file is larger than %s MB.", MAX_FILE_BYTES // (1024 * 1024)))
        # Sin entidades ni red: un XML subido por un usuario no debe poder leer
        # archivos del servidor ni hacer peticiones (XXE).
        parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
        try:
            raiz = etree.fromstring(datos, parser=parser)
        except etree.XMLSyntaxError as e:
            raise UserError(_("The file is not valid XML: %s", e)) from e
        if etree.QName(raiz).localname != "Project":
            raise UserError(_(
                "This is not a Microsoft Project XML file. In Microsoft Project use "
                "File > Save As > XML Format (*.xml)."))
        return raiz

    def _read(self, raiz):
        minutos_dia = _int(raiz, "MinutesPerDay", 480) or 480
        tareas, vinculos = [], []
        for el in raiz.iterfind("{*}Tasks/{*}Task"):
            uid = _int(el, "UID", -1)
            if uid <= 0 or _int(el, "IsNull") == 1:
                continue
            tareas.append({
                "uid": uid,
                "name": _txt(el, "Name") or _("Task %s", uid),
                "level": max(_int(el, "OutlineLevel", 1), 1),
                "start": _txt(el, "Start"),
                "finish": _txt(el, "Finish"),
                # En MS Project la marca de hito en un RESUMEN (o en una
                # tarea con duración) solo cambia el dibujo; aquí un hito dura
                # 0 días y colapsaría las fechas de una tarea con duración.
                "milestone": _int(el, "Milestone") == 1 and _int(el, "Summary") != 1
                and not _iso_hours(_txt(el, "Duration")),
                "percent": _int(el, "PercentComplete"),
                # La duración es un DATO en MS Project (`<Duration>`, ISO
                # 8601, en horas de trabajo); aquí se guarda en días laborables.
                "duration_hours": _iso_hours(_txt(el, "Duration")),
                # Manual y fechas reales: el cálculo no mueve ni lo uno ni
                # lo que ya ocurrió.
                "manual": _int(el, "Manual") == 1,
                "actual_start": _txt(el, "ActualStart"),
                "actual_finish": _txt(el, "ActualFinish"),
                # La restricción de fecha (`<ConstraintType>` MSPDI).
                "constraint": MSPDI_CONSTRAINTS.get(_int(el, "ConstraintType", 0), "asap"),
                "constraint_date": _txt(el, "ConstraintDate"),
                # La fecha límite (acota el fin tardío → ruta crítica).
                "deadline": _txt(el, "Deadline"),
            })
            for pl in el.iterfind("{*}PredecessorLink"):
                vinculos.append({
                    "task": uid,
                    "pred": _int(pl, "PredecessorUID", -1),
                    "type": _int(pl, "Type", 1),
                    "lag": _int(pl, "LinkLag", 0),
                    "format": _int(pl, "LagFormat", 7),
                })
        recursos = {}
        for el in raiz.iterfind("{*}Resources/{*}Resource"):
            recursos[_int(el, "UID", -1)] = (_txt(el, "Name"), _txt(el, "EmailAddress"))
        asignaciones = {}
        for el in raiz.iterfind("{*}Assignments/{*}Assignment"):
            asignaciones.setdefault(_int(el, "TaskUID", -1), []).append(_int(el, "ResourceUID", -1))
        return minutos_dia, tareas, vinculos, recursos, asignaciones

    def _to_utc(self, texto):
        """`2026-09-01T08:00:00` en la zona del usuario → Datetime UTC."""
        if not texto:
            return False
        try:
            local = datetime.fromisoformat(texto[:19])
        except ValueError:
            return False
        zona = pytz.timezone(self.env.user.tz or "UTC")
        return zona.localize(local).astimezone(pytz.UTC).replace(tzinfo=None)

    # ------------------------------------------------------------------ escritura
    def action_import(self):
        self.ensure_one()
        self._check_can_import()
        proyecto = self.project_id
        raiz = self._parse()
        minutos_dia, filas, vinculos, recursos, asignaciones = self._read(raiz)
        calendario = self._apply_calendar(raiz)
        # Los «minutos por día» del archivo (cuánto es un día de duración).
        # sudo(): mismo motivo que el calendario (dato derivado del archivo).
        if self.calendar_mode != "keep":
            self.project_id.sudo().minutes_per_day = minutos_dia
        # Opciones de programación del archivo (mismo motivo de sudo()).
        desde_fin = _txt(raiz, "ScheduleFromStart") == "0" and bool(_txt(raiz, "FinishDate"))
        self.project_id.sudo().write({
            "schedule_from": "finish" if desde_fin else "start",
            "project_finish": self._to_utc(_txt(raiz, "FinishDate")) if desde_fin else False,
            "honor_constraints": _txt(raiz, "HonorConstraints") != "0",
        })
        if not filas:
            raise UserError(_("The file has no tasks."))

        Tarea = self.env["project.task"].with_context(
            mail_create_nolog=True, mail_notrack=True, tracking_disable=True,
            mail_auto_subscribe_no_notify=True)
        existentes = {t.ms_uid: t for t in Tarea.search(
            [("project_id", "=", proyecto.id), ("ms_uid", "!=", 0)])}
        usuarios = self._match_users(recursos)

        por_uid, pila, creadas, actualizadas = {}, [], 0, 0
        con_vinculo = {v["task"] for v in vinculos}
        sin_responsable, con_avance = set(), 0
        for orden, fila in enumerate(filas, 1):
            # El padre es la última tarea abierta de nivel inferior.
            while pila and pila[-1][0] >= fila["level"]:
                pila.pop()
            padre = pila[-1][1] if pila else self.env["project.task"]
            restriccion = fila["constraint"]
            # El exportador ancla con «No comenzar antes del» su propia
            # fecha a la tarea automática sin predecesoras (ni ella ni sus
            # resúmenes), porque MS Project la llevaría al inicio del proyecto.
            # Aquí ese ancla ES «lo antes posible»: nuestro motor ya deja esa
            # tarea en su fecha. Se reconoce y se devuelve como tal.
            if (restriccion == "snet" and not fila["manual"] and fila["constraint_date"][:16] == fila["start"][:16]
                    and fila["uid"] not in con_vinculo and not any(u in con_vinculo for _n, _t, u in pila)):
                restriccion = "asap"
            inicio, fin = self._to_utc(fila["start"]), self._to_utc(fila["finish"])
            if inicio and fin and fin < inicio:
                fin = inicio
            responsables = self.env["res.users"]
            for ruid in asignaciones.get(fila["uid"], []):
                if ruid in usuarios:
                    responsables |= usuarios[ruid]
                elif ruid in recursos and recursos[ruid][0]:
                    sin_responsable.add(recursos[ruid][0])
            vals = {
                "name": fila["name"],
                "project_id": proyecto.id,
                "parent_id": padre.id or False,
                "sequence": orden * 10,
                "planned_date_begin": inicio,
                "date_deadline": fin,
                "is_milestone": fila["milestone"],
                "ms_uid": fila["uid"],
                "constraint_type": restriccion,
                "manually_scheduled": fila["manual"],
                "actual_start": self._to_utc(fila["actual_start"]),
                "actual_finish": self._to_utc(fila["actual_finish"]),
                "finish_deadline": self._to_utc(fila["deadline"]),
                "constraint_date": self._to_utc(fila["constraint_date"]) if restriccion not in ("asap", "alap") else False,
                "duration_days": 0.0 if fila["milestone"] else
                    max(1.0, round(fila["duration_hours"] * 60 / minutos_dia, 1)) if fila["duration_hours"] else False,
            }
            # Siempre, aunque vaya vacío: en Odoo 18 `project.task.default_get` asigna la tarea a
            # quien la crea cuando el proyecto llega en los valores y no en el contexto
            # (project/models/project_task.py:975-978, 18.0). Los responsables los dice el archivo.
            vals["user_ids"] = [(6, 0, responsables.ids)]
            if vals["duration_days"] is False:
                del vals["duration_days"]
            con_avance += fila["percent"] > 0
            tarea = existentes.get(fila["uid"])
            if tarea:
                tarea.write(vals)
                actualizadas += 1
            else:
                tarea = Tarea.create(vals)
                creadas += 1
            por_uid[fila["uid"]] = tarea
            pila.append((fila["level"], tarea, fila["uid"]))

        n_vinculos, en_porcentaje, retirados = self._import_links(vinculos, por_uid, minutos_dia)
        no_vienen = Tarea.search([("project_id", "=", proyecto.id), ("id", "not in", [t.id for t in por_uid.values()])])

        lineas = ([_("Working calendar: %s", calendario)] if calendario else []) + (
            [_("Links no longer in the file, removed: %s", retirados)] if retirados else []) + [
            _("Tasks created: %s", creadas),
            _("Tasks updated: %s", actualizadas),
            _("Links imported: %s", n_vinculos),
        ]
        if sin_responsable:
            lineas.append(_("Resources with no matching user (not assigned): %s", ", ".join(sorted(sin_responsable))))
        if con_avance:
            lineas.append(_("Tasks with progress in the file: %s. Progress is not imported: "
                            "it is reported with evidence in each task.", con_avance))
        if en_porcentaje:
            lineas.append(_("Links with a percentage lag imported without lag: %s", en_porcentaje))
        if no_vienen:
            lineas.append(_("Tasks in the schedule that are not in the file (kept): %s", len(no_vienen)))
        lineas.append(_("Not imported: calendars and baselines."))
        self.summary = "\n".join(lineas)
        self.state = "done"
        self._after_import()
        return {
            "type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
            "view_mode": "form", "target": "new", "name": _("Import from Microsoft Project"),
        }

    # ------------------------------------------------------------ extensión
    def _check_can_import(self):
        """Quién puede importar y cuándo. Genérico: quien puede crear y editar
        tareas en el proyecto. Un puente de dominio agrega sus reglas."""
        self.ensure_one()
        self.env["project.task"].check_access("create")
        self.project_id.check_access("read")

    def _after_import(self):
        """Deja el resumen en el chatter del proyecto. Un puente puede avisar
        además donde su dominio lo necesite."""
        self.ensure_one()
        # sudo(): la nota solo DOCUMENTA una importación que el usuario ya hizo
        # con sus propios permisos (crear y editar tareas). Publicar en el
        # chatter de project.project exige escribir el proyecto, que un
        # capturista de tareas no tiene (p. ej. un PM sobre el
        # proyecto del cronograma). El autor sigue siendo el usuario.
        self.project_id.sudo().message_post(
            body=_("Schedule imported from Microsoft Project (%(file)s).\n%(summary)s",
                   file=self.filename or "XML", summary=self.summary),
            author_id=self.env.user.partner_id.id)

    # ------------------------------------------------------------ calendario
    def _file_calendar(self, raiz):
        """El calendario del proyecto en el XML: `<CalendarUID>` del proyecto,
        o el que usan las tareas, o el primero base. MSPDI: `<DayType>` 1 =
        domingo … 7 = sábado; `<Exception>` con `<DayWorking>0` = feriado."""
        calendarios = {_int(c, "UID", -1): c for c in raiz.iterfind("{*}Calendars/{*}Calendar")}
        if not calendarios:
            return None
        uid = _int(raiz, "CalendarUID", -1)
        if uid not in calendarios:
            usados = [_int(t, "CalendarUID", -1) for t in raiz.iterfind("{*}Tasks/{*}Task")]
            usados = [u for u in usados if u in calendarios]
            uid = max(set(usados), key=usados.count) if usados else next(
                (u for u, c in calendarios.items() if _int(c, "IsBaseCalendar") == 1), next(iter(calendarios)))
        return calendarios[uid]

    def _apply_calendar(self, raiz):
        """El calendario del archivo, el de la compañía o el
        que el proyecto ya tiene. Devuelve el nombre para el resumen."""
        # sudo(): el calendario es un DATO DERIVADO del archivo, dentro de una
        # importación que ya pasó `_check_can_import()` con los permisos del
        # usuario. Crear un resource.calendar y asignarlo al proyecto exige
        # derechos que un capturista de tareas no tiene (un PM no siempre
        # puede escribir el proyecto de su cronograma).
        proyecto = self.project_id.sudo()
        if self.calendar_mode == "keep":
            return proyecto.schedule_calendar_id.name
        if self.calendar_mode == "company":
            proyecto.schedule_calendar_id = proyecto.company_id.resource_calendar_id or self.env.company.resource_calendar_id
            return proyecto.schedule_calendar_id.name
        el = self._file_calendar(raiz)
        if el is None:
            return proyecto.schedule_calendar_id.name
        tz = self.env.user.tz or "UTC"
        asistencias = []
        for dia in el.iterfind("{*}WeekDays/{*}WeekDay"):
            tipo = _int(dia, "DayType", 0)
            if not 1 <= tipo <= 7 or _int(dia, "DayWorking") != 1:
                continue
            odoo_dia = str((tipo + 5) % 7)  # MSPDI 1=domingo → Odoo 6; 2=lunes → 0
            turnos = [(_txt(w, "FromTime"), _txt(w, "ToTime")) for w in dia.iterfind("{*}WorkingTimes/{*}WorkingTime")]
            for desde, hasta in turnos or [("09:00:00", "18:00:00")]:
                h1 = int(desde[:2]) + int(desde[3:5]) / 60
                h2 = int(hasta[:2]) + int(hasta[3:5]) / 60 if hasta[:2] != "00" else 24.0
                asistencias.append((0, 0, {
                    "name": _("Working time"), "dayofweek": odoo_dia, "hour_from": h1, "hour_to": h2,
                    "day_period": "morning" if h2 <= 13 else "afternoon"}))
        nombre = _("%(project)s (Microsoft Project)", project=proyecto.name)
        # Al REIMPORTAR se reutiliza el calendario que la importación
        # anterior creó para este proyecto (mismo nombre, y ningún otro
        # proyecto lo usa), para no acumular un calendario por reimportación.
        # El archivo lo define: se
        # reemplazan sus turnos y sus feriados.
        previo = proyecto.schedule_calendar_id
        reutilizable = previo and previo.name == nombre and not self.env["project.project"].sudo().search_count(
            [("schedule_calendar_id", "=", previo.id), ("id", "!=", proyecto.id)])
        if reutilizable:
            cal = previo.sudo()
            cal.write({"tz": tz, "attendance_ids": [(5, 0, 0)] + asistencias})
            cal.leave_ids.filtered(lambda l: not l.resource_id).unlink()
        else:
            cal = self.env["resource.calendar"].sudo().create({
                "name": nombre, "tz": tz, "company_id": proyecto.company_id.id or self.env.company.id,
                "attendance_ids": [(5, 0, 0)] + asistencias,
            })
        feriados = []
        zona = pytz.timezone(tz)
        for exc in el.iterfind("{*}Exceptions/{*}Exception"):
            if _int(exc, "DayWorking") == 1:
                continue  # excepción LABORABLE (un sábado de trabajo): no se modela todavía
            desde, hasta = _txt(exc, "TimePeriod/{*}FromDate") or _txt(exc, "FromDate"), _txt(exc, "TimePeriod/{*}ToDate") or _txt(exc, "ToDate")
            try:
                a, b = datetime.fromisoformat(desde[:19]), datetime.fromisoformat(hasta[:19])
            except ValueError:
                continue
            feriados.append({"name": _txt(exc, "Name") or _("Non-working day"), "calendar_id": cal.id,
                             "date_from": zona.localize(a).astimezone(pytz.UTC).replace(tzinfo=None),
                             "date_to": zona.localize(b).astimezone(pytz.UTC).replace(tzinfo=None)})
        self.env["resource.calendar.leaves"].sudo().create(feriados)
        proyecto.schedule_calendar_id = cal
        return nombre

    def _match_users(self, recursos):
        """Recurso de MS Project → usuario interno, por correo y si no por nombre."""
        internos = self.env["res.users"].search([("share", "=", False)])
        por_correo = {(u.email or "").lower(): u for u in internos if u.email}
        por_correo.update({(u.login or "").lower(): u for u in internos})
        por_nombre = {(u.name or "").strip().lower(): u for u in internos}
        encontrados = {}
        for ruid, (nombre, correo) in recursos.items():
            usuario = por_correo.get(correo.lower()) if correo else None
            usuario = usuario or por_nombre.get(nombre.strip().lower())
            if usuario:
                encontrados[ruid] = usuario
        return encontrados

    def _import_links(self, vinculos, por_uid, minutos_dia):
        Dep = self.env["project.dependency"]
        importadas = {t.id for t in por_uid.values()}
        actuales = {(d.successor_id.id, d.predecessor_id.id): d for d in Dep.search(
            [("successor_id", "in", list(importadas))])}
        # Entre tareas importadas, los vínculos los define EL ARCHIVO. Al
        # reimportar se retiran primero los que ya no vienen; si no, los viejos
        # y los nuevos podían cerrar un ciclo. Los
        # vínculos con tareas que no vienen en el archivo no se tocan.
        del_archivo = {(por_uid[v["task"]].id, por_uid[v["pred"]].id) for v in vinculos
                       if v["task"] in por_uid and v["pred"] in por_uid}
        sobran = [d for (suc, pre), d in actuales.items()
                  if suc in importadas and pre in importadas and (suc, pre) not in del_archivo]
        if sobran:
            Dep.browse([d.id for d in sobran]).unlink()
            actuales = {k: d for k, d in actuales.items() if d.exists()}
        nuevos, n, en_porcentaje = [], 0, 0
        for v in vinculos:
            tarea, pred = por_uid.get(v["task"]), por_uid.get(v["pred"])
            if not tarea or not pred or tarea == pred:
                continue
            if v["format"] in PERCENT_LAG_FORMATS:
                dias, natural = 0.0, False
                en_porcentaje += 1 if v["lag"] else 0
            elif v["format"] in ELAPSED_LAG_FORMATS:
                dias, natural = v["lag"] / 10 / 60 / 24, True
            else:
                dias, natural = v["lag"] / 10 / minutos_dia, False
            vals = {"link_type": MSPDI_LINK_TYPES.get(v["type"], "fs"),
                    "lag_days": round(dias, 2), "lag_elapsed": natural}
            existente = actuales.get((tarea.id, pred.id))
            if existente:
                existente.write(vals)
            else:
                nuevos.append({"successor_id": tarea.id, "predecessor_id": pred.id, **vals})
            n += 1
        # El campo nativo `depend_on_ids` lo mantiene project_dependency:
        # solo los fin-inicio sin desfase, que es lo que el Gantt de Odoo dibuja.
        Dep.create(nuevos)._sync_native_dependency()
        if actuales:
            Dep.browse([d.id for d in actuales.values()])._sync_native_dependency()
        return n, en_porcentaje, len(sobran)
