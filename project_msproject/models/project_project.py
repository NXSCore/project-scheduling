# -*- coding: utf-8 -*-
"""Exportar el cronograma de un proyecto al XML de MS Project (MSPDI).

Es el camino de regreso del importador: escribe exactamente lo que el
importador lee, para que un proyecto vaya y vuelva sin perder nada —tareas,
jerarquía, EDT, fechas, duración guardada, hitos, manuales, fechas reales,
restricciones, fechas límite, vínculos con tipo y desfase, responsables,
calendario laboral con sus feriados y opciones de programación—.

MS Project es ESTRICTO con el orden de los elementos (sigue su XSD): el
orden de cada lista de abajo se tomó de archivos guardados por MS Project.

Las fechas se escriben en la zona del usuario, igual que el importador las lee.
"""
from datetime import datetime, timedelta

import pytz
from lxml import etree

from odoo import _, models

from odoo.addons.project_dependency.models.scheduler import (
    MSPDI_CONSTRAINTS, calendar_for, holiday_leaves, working_days,
)

NS = "http://schemas.microsoft.com/project"
FMT = "%Y-%m-%dT%H:%M:%S"
#: Inverso de `MSPDI_LINK_TYPES` del importador.
LINK_CODES = {"ff": 0, "fs": 1, "sf": 2, "ss": 3}
CONSTRAINT_CODES = {v: k for k, v in MSPDI_CONSTRAINTS.items()}
#: `<LagFormat>`: 7 = días laborables, 8 = días naturales («edías»).
LAG_DAYS, LAG_ELAPSED_DAYS = 7, 8
#: `<DurationFormat>` 7 = días.
DURATION_DAYS = 7


def _iso_duration(minutos):
    minutos = max(0, int(round(minutos)))
    return "PT%dH%dM0S" % (minutos // 60, minutos % 60)


def _hora(h):
    """8.5 → «08:30:00»; 24 → «00:00:00» (fin del día, como lo escribe MS)."""
    total = int(round(h * 60)) % (24 * 60)
    return "%02d:%02d:00" % (total // 60, total % 60)


class ProjectProject(models.Model):
    _inherit = "project.project"

    def action_export_mspdi(self):
        """Botón «Exportar a MS Project»: asigna UID a las tareas que no lo
        tienen (si no, reimportar el archivo las duplicaría) y descarga."""
        self.ensure_one()
        self.check_access("read")
        self._assign_ms_uids()
        return {
            "type": "ir.actions.act_url",
            "url": "/project_msproject/export/%d" % self.id,
            "target": "download",
        }

    def _assign_ms_uids(self):
        tareas = self.env["project.task"].search([("project_id", "=", self.id)])
        vistos, repetidas = set(), self.env["project.task"]
        for t in tareas.sorted("id"):
            if t.ms_uid and t.ms_uid not in vistos:
                vistos.add(t.ms_uid)
            else:
                repetidas |= t
        siguiente = max(vistos, default=0) + 1
        for t in repetidas:
            # sudo(): el UID es un identificador de INTERCAMBIO, no un dato del
            # cronograma; quien exporta solo necesita leer el proyecto, y sin
            # el UID guardado una reimportación del mismo archivo duplicaría
            # las tareas en vez de actualizarlas.
            t.sudo().ms_uid = siguiente
            siguiente += 1

    # ------------------------------------------------------------ el archivo
    def _mspdi_export(self):
        """Los bytes del XML MSPDI de este proyecto, con los permisos de quien
        exporta (sin `sudo()`)."""
        self.ensure_one()
        tz = pytz.timezone(self.env.user.tz or "UTC")
        mpd = self.minutes_per_day or 480

        def local(valor):
            return valor and pytz.utc.localize(valor).astimezone(tz).replace(tzinfo=None)

        def fecha(valor):
            return valor.strftime(FMT) if valor else None

        tareas = self.env["project.task"].search([("project_id", "=", self.id)])
        tareas = tareas.sorted(lambda t: tuple(int(p) for p in (t.wbs_code or "0").split(".")))
        ids = set(tareas.ids)
        con_hijas = set(tareas.filtered(lambda t: t.child_ids & tareas).ids)
        uid = {}
        libre = max([t.ms_uid for t in tareas] + [0]) + 1
        for t in tareas:
            if t.ms_uid and t.ms_uid not in uid.values():
                uid[t.id] = t.ms_uid
            else:
                uid[t.id] = libre
                libre += 1

        cal_rec = self._work_calendar_record()
        fechas = [d for t in tareas for d in (t.planned_date_begin, t.date_deadline) if d]
        hoy = datetime.now()
        ini_p = min(fechas) if fechas else hoy
        fin_p = max(fechas) if fechas else hoy
        work, cal_tz = calendar_for(cal_rec, ini_p.date() - timedelta(days=400), fin_p.date() + timedelta(days=4000))

        raiz = etree.Element("{%s}Project" % NS, nsmap={None: NS})

        def sub(padre, tag, valor=None):
            el = etree.SubElement(padre, "{%s}%s" % (NS, tag))
            if valor is not None:
                el.text = str(valor)
            return el

        turnos = [a for a in cal_rec.attendance_ids if not a.display_type and a.day_period != "lunch"] if cal_rec else []
        inicio_dia = min((a.hour_from for a in turnos), default=8.0)
        fin_dia = max((a.hour_to for a in turnos), default=17.0)
        desde_fin = self.schedule_from == "finish" and self.project_finish
        for tag, valor in (
            ("SaveVersion", 14), ("Name", "%s.xml" % self.name), ("Title", self.name),
            ("Author", self.env.user.name), ("CreationDate", fecha(local(datetime.now().replace(microsecond=0)))),
            ("ScheduleFromStart", 0 if desde_fin else 1),
            ("StartDate", fecha(local(ini_p))), ("FinishDate", fecha(local(self.project_finish if desde_fin else fin_p))),
            ("CriticalSlackLimit", 0), ("CalendarUID", 1),
            ("DefaultStartTime", _hora(inicio_dia)), ("DefaultFinishTime", _hora(fin_dia)),
            ("MinutesPerDay", mpd), ("MinutesPerWeek", mpd * 5), ("DaysPerMonth", 20),
            ("DurationFormat", DURATION_DAYS),
            ("HonorConstraints", 1 if self.honor_constraints else 0),
            ("NewTasksAreManual", 0),
        ):
            sub(raiz, tag, valor)

        # --- calendario
        cals = sub(raiz, "Calendars")
        cal = sub(cals, "Calendar")
        sub(cal, "UID", 1)
        sub(cal, "Name", cal_rec.name if cal_rec else _("Standard"))
        sub(cal, "IsBaseCalendar", 1)
        sub(cal, "BaseCalendarUID", -1)
        semana = sub(cal, "WeekDays")
        for ms_dia in range(1, 8):  # MSPDI 1 = domingo … 7 = sábado
            odoo_dia = str((ms_dia + 5) % 7)
            del_dia = sorted((a.hour_from, a.hour_to) for a in turnos if a.dayofweek == odoo_dia)
            wd = sub(semana, "WeekDay")
            sub(wd, "DayType", ms_dia)
            sub(wd, "DayWorking", 1 if del_dia else 0)
            if del_dia:
                horas = sub(wd, "WorkingTimes")
                for h1, h2 in del_dia:
                    w = sub(horas, "WorkingTime")
                    sub(w, "FromTime", _hora(h1))
                    sub(w, "ToTime", _hora(h2))
        # Los mismos feriados que aplica Odoo (y el motor), también los
        # que no tienen calendario.
        feriados = holiday_leaves(cal_rec) if cal_rec else []
        if feriados:
            excepciones = sub(cal, "Exceptions")
            for f in feriados:
                e = sub(excepciones, "Exception")
                sub(e, "EnteredByOccurrence", 0)
                periodo = sub(e, "TimePeriod")
                sub(periodo, "FromDate", fecha(local(f.date_from)))
                sub(periodo, "ToDate", fecha(local(f.date_to)))
                sub(e, "Occurrences", 1)
                sub(e, "Name", f.name or _("Non-working day"))
                sub(e, "Type", 1)
                sub(e, "DayWorking", 0)

        # --- tareas
        nodo_tareas = sub(raiz, "Tasks")
        resumen = sub(nodo_tareas, "Task")
        for tag, valor in (("UID", 0), ("ID", 0), ("Name", self.name), ("Active", 1), ("Manual", 0), ("Type", 0),
                           ("IsNull", 0), ("WBS", 0), ("OutlineNumber", 0), ("OutlineLevel", 0),
                           ("Start", fecha(local(ini_p))), ("Finish", fecha(local(fin_p))),
                           ("Duration", _iso_duration(work.between(local(ini_p), local(fin_p)) if fechas else 0)),
                           ("DurationFormat", DURATION_DAYS), ("Milestone", 0), ("Summary", 1)):
            sub(resumen, tag, valor)
        deps = self.env["project.dependency"].search([("successor_id", "in", tareas.ids)])
        tipados = {(d.successor_id.id, d.predecessor_id.id): d for d in deps}
        preds = {t.id: (t.depend_on_ids | t.predecessor_link_ids.predecessor_id).filtered(lambda x: x.id in ids)
                 for t in tareas}

        def con_predecesoras(t):
            """¿La tarea o alguno de sus resúmenes tiene predecesoras? Entonces
            MS Project la coloca por sus vínculos."""
            while t and t.id in ids:
                if preds[t.id]:
                    return True
                t = t.parent_id
            return False

        creada = fecha(local(datetime.now().replace(microsecond=0)))
        minutos_de = {}
        for n, t in enumerate(tareas, 1):
            el = sub(nodo_tareas, "Task")
            nivel = 1
            p = t.parent_id
            while p and p.id in ids:
                nivel += 1
                p = p.parent_id
            resumen_t = t.id in con_hijas
            if t.is_milestone:
                minutos = 0
            elif not resumen_t and t.duration_days:
                minutos = t.duration_days * mpd
            elif t.planned_date_begin and t.date_deadline:
                minutos = working_days(work, cal_tz, t.planned_date_begin, t.date_deadline, False, mpd) * mpd
            else:
                minutos = mpd
            minutos_de[t.id] = minutos
            restriccion = t.constraint_type or "asap"
            fecha_restriccion = t.constraint_date if restriccion not in ("asap", "alap") else False
            # En MS Project una tarea AUTOMÁTICA «lo antes posible» sin
            # predecesoras (ni ella ni sus resúmenes) se va al INICIO DEL
            # PROYECTO: la fecha del archivo se ignora. Nuestro motor la deja anclada en su
            # fecha, que es lo que MS Project hace cuando alguien la teclea: la
            # convierte en «No comenzar antes del». Se exporta así; el
            # importador lo reconoce y la devuelve como «lo antes posible».
            if (restriccion == "asap" and not t.manually_scheduled and not resumen_t and t.planned_date_begin
                    and not con_predecesoras(t)):
                restriccion, fecha_restriccion = "snet", t.planned_date_begin
            inicio = fecha(local(t.planned_date_begin))
            fin = fecha(local(t.date_deadline or t.planned_date_begin))
            # El juego completo de elementos de programación que MS Project
            # escribe en CADA tarea, en su orden. Si se omiten los ceros, MS
            # Project descarta casi todos los vínculos al abrir el archivo.
            campos = [
                ("UID", uid[t.id]), ("ID", n), ("Name", t.name), ("Active", 1), ("Manual", 1 if t.manually_scheduled else 0),
                ("Type", 0), ("IsNull", 0), ("CreateDate", creada), ("WBS", t.wbs_code),
                ("OutlineNumber", t.wbs_code), ("OutlineLevel", nivel), ("Priority", 500),
                ("Start", inicio), ("Finish", fin), ("Duration", _iso_duration(minutos)),
            ]
            if t.manually_scheduled:
                campos += [("ManualStart", inicio), ("ManualFinish", fin), ("ManualDuration", _iso_duration(minutos))]
            campos += [
                ("DurationFormat", DURATION_DAYS), ("ResumeValid", 0), ("EffortDriven", 0), ("Recurring", 0),
                ("OverAllocated", 0), ("Estimated", 0), ("Milestone", 1 if t.is_milestone else 0),
                ("Summary", 1 if resumen_t else 0), ("DisplayAsSummary", 0), ("Critical", 1 if t.is_critical else 0),
                ("IsSubproject", 0), ("IsSubprojectReadOnly", 0), ("ExternalTask", 0),
                ("PercentComplete", 100 if t.actual_finish else 0),
                ("ActualStart", fecha(local(t.actual_start))), ("ActualFinish", fecha(local(t.actual_finish))),
                ("ConstraintType", CONSTRAINT_CODES.get(restriccion, 0)), ("CalendarUID", -1),
                ("ConstraintDate", fecha(local(fecha_restriccion))), ("Deadline", fecha(local(t.finish_deadline))),
                ("LevelAssignments", 0), ("LevelingCanSplit", 0), ("LevelingDelay", 0), ("LevelingDelayFormat", 8),
                ("IgnoreResourceCalendar", 0), ("HideBar", 0), ("Rollup", 0),
            ]
            for tag, valor in campos:
                # Ojo: `0 in (None, False)` es True en Python; los ceros SÍ van.
                if valor is not None and valor is not False and valor != "":
                    sub(el, tag, valor)
            for pred in preds[t.id].sorted(lambda x: uid.get(x.id, 0)):
                d = tipados.get((t.id, pred.id))
                tipo, dias, natural = (d.link_type, d.lag_days, d.lag_elapsed) if d else ("fs", 0.0, False)
                pl = sub(el, "PredecessorLink")
                sub(pl, "PredecessorUID", uid[pred.id])
                sub(pl, "Type", LINK_CODES.get(tipo, 1))
                sub(pl, "CrossProject", 0)
                sub(pl, "LinkLag", int(round(dias * (1440 if natural else mpd) * 10)))
                sub(pl, "LagFormat", LAG_ELAPSED_DAYS if natural else LAG_DAYS)

        # --- recursos y asignaciones (el importador los empata por correo o nombre)
        usuarios = tareas.user_ids.sorted("id")
        if usuarios:
            nodo_rec = sub(raiz, "Resources")
            ruid = {}
            for n, u in enumerate(usuarios, 1):
                ruid[u.id] = n
                r = sub(nodo_rec, "Resource")
                for tag, valor in (("UID", n), ("ID", n), ("Name", u.name), ("Type", 1), ("IsNull", 0),
                                   ("EmailAddress", u.email or u.login), ("MaxUnits", "1.00")):
                    if valor:
                        sub(r, tag, valor)
            nodo_asg = sub(raiz, "Assignments")
            n = 0
            for t in tareas:
                for u in t.user_ids:
                    n += 1
                    # Con sus fechas y su trabajo. Sin ellos MS Project
                    # suponía la asignación fuera de las fechas de la tarea y
                    # avisa que cambiará su duración.
                    a = sub(nodo_asg, "Assignment")
                    sub(a, "UID", n)
                    sub(a, "TaskUID", uid[t.id])
                    sub(a, "ResourceUID", ruid[u.id])
                    if t.planned_date_begin:
                        sub(a, "Finish", fecha(local(t.date_deadline or t.planned_date_begin)))
                        sub(a, "Start", fecha(local(t.planned_date_begin)))
                    sub(a, "Units", 1)
                    sub(a, "Work", _iso_duration(minutos_de[t.id]))
        return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True, pretty_print=True)
