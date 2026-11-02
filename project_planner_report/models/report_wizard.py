# -*- coding: utf-8 -*-
"""El «Informe» del planificador.

Un asistente con las opciones del informe y un PDF de tabla + Gantt. Las
tareas son las MISMAS que muestra el planificador: se leen con
`project.task.planner_data(domain)`, sin `sudo()`, así que nadie imprime lo
que no puede ver.
"""
import json
from datetime import datetime, timedelta

import pytz
from babel.dates import format_date

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.project_dependency.models.scheduler import calendar_for, working_days

from .gantt_pdf import GanttPdf

FECHA_ISO = "%Y-%m-%dT%H:%M:%S"


class RePlannerReportWizard(models.TransientModel):
    _name = "project.planner.report.wizard"
    _description = "Planner PDF Report"

    domain = fields.Char(default="[]", required=True,
                         help="The tasks of the report, as JSON: the same domain the planner shows.")
    title = fields.Char(string="Title")
    company_name = fields.Char(string="Company", default=lambda self: self.env.company.name)
    author = fields.Char(string="Author", default=lambda self: self.env.user.name)
    paper = fields.Selection(
        [("a4", "A4"), ("a3", "A3"), ("letter", "Letter"), ("tabloid", "Tabloid")],
        string="Paper", default="a3", required=True)
    orientation = fields.Selection(
        [("landscape", "Landscape"), ("portrait", "Portrait")],
        string="Orientation", default="landscape", required=True)
    font_scale = fields.Integer(string="Font Size (%)", default=100, help="Between 50 and 200.")
    bar_colors = fields.Selection(
        [("critical", "Critical path"), ("uniform", "Uniform")],
        string="Bar Colors", default="critical", required=True)
    status_line = fields.Selection(
        [("none", "None"), ("today", "Today")],
        string="Status Line", default="none", required=True)
    follow_view = fields.Boolean(
        string="Follow the View",
        help="Print the date window shown in the planner and hide the collapsed branches.")
    view_date_from = fields.Datetime()
    view_date_to = fields.Datetime()
    collapsed_ids = fields.Char(default="[]")
    # Las columnas del planificador, en su orden (JSON); con «Seguir la
    # vista» el informe imprime esas.
    view_columns = fields.Char(default="[]")
    # Las tareas que el filtro del planificador deja ver (JSON; `null` =
    # sin filtro). Con «Seguir la vista», el informe imprime solo esas.
    filter_ids = fields.Char(default="null")
    fit_to_paper = fields.Boolean(string="Fit to Paper", default=True,
                                  help="Scale the timeline so the whole period fits in the chosen number of pages across.")
    timeline_pages = fields.Integer(string="Timeline Pages", default=1,
                                    help="Pages across for the timeline when it is fitted to the paper.")
    scale = fields.Selection(
        [("day", "Days"), ("week", "Weeks"), ("month", "Months"), ("quarter", "Quarters")],
        string="Timescale", default="week", required=True,
        help="Used when the timeline is not fitted to the paper: the pages across follow from it.")
    repeat_header = fields.Boolean(string="Repeat Header on Every Page", default=True)
    names_on_bars = fields.Boolean(string="Task Names on Bars", default=True)
    show_progress = fields.Boolean(string="Show Progress", default=True)
    show_baseline = fields.Boolean(string="Show Baseline Overlay")
    # Las líneas base que el planificador está comparando (JSON, ids);
    # con «Línea base» se imprimen con la vigente, en la misma franja.
    compare_ids = fields.Char(default="[]")
    show_float = fields.Boolean(string="Show Float", default=True)
    show_links = fields.Boolean(string="Dependencies", default=True)
    workdays_only = fields.Boolean(string="Working Days Only",
                                   help="Non-working days take no room on the timeline.")
    shade_weekends = fields.Boolean(string="Shade Non-working Days", default=True)
    show_legend = fields.Boolean(string="Legend", default=True)

    task_count = fields.Integer(string="Tasks", compute="_compute_summary")
    leaf_count = fields.Integer(string="Leaf Tasks", compute="_compute_summary")
    critical_count = fields.Integer(string="Critical", compute="_compute_summary")
    link_count = fields.Integer(string="Links", compute="_compute_summary")

    @api.depends("domain")
    def _compute_summary(self):
        for wiz in self:
            datos = wiz._planner_data()
            hojas = [t for t in datos["tasks"] if not t["summary"]]
            wiz.task_count = len(datos["tasks"])
            wiz.leaf_count = len(hojas)
            wiz.critical_count = sum(1 for t in hojas if t["critical"])
            wiz.link_count = len(datos["links"])

    def _report_domain(self):
        # JSON, no Python: lo escribe el planificador (`JSON.stringify`).
        try:
            dominio = json.loads(self.domain or "[]")
        except ValueError as error:
            raise UserError(self.env._("The report domain is not valid.")) from error
        return dominio if isinstance(dominio, list) else []

    def _planner_data(self):
        self.ensure_one()
        return self.env["project.task"].planner_data(self._report_domain())

    def action_export(self):
        self.ensure_one()
        if not 50 <= (self.font_scale or 0) <= 200:
            raise UserError(self.env._("The font size must be between 50 and 200 percent."))
        if self.fit_to_paper and not 1 <= (self.timeline_pages or 0) <= 20:
            raise UserError(self.env._("The timeline pages must be between 1 and 20."))
        return {
            "type": "ir.actions.act_url",
            "url": "/project_planner_report/pdf/%d" % self.id,
            "target": "download",
        }

    # ------------------------------------------------------------------ datos
    def _report_values(self):
        """Lo que el dibujo necesita: filas en hora LOCAL del usuario, ya con
        sus textos; el dibujo no consulta nada."""
        self.ensure_one()
        env = self.env
        datos = self._planner_data()
        tz = pytz.timezone(env.user.tz or "UTC")
        lang = env["res.lang"]._get_data(code=env.lang or "en_US")
        formato = lang.date_format or "%m/%d/%Y"
        locale = (env.lang or "en_US")

        def local(valor):
            if not valor:
                return None
            utc = datetime.strptime(valor[:19], FECHA_ISO)
            return pytz.utc.localize(utc).astimezone(tz).replace(tzinfo=None)

        tareas = datos["tasks"]
        ids = [t["id"] for t in tareas]
        holgura = {t.id: t.total_float_days for t in env["project.task"].browse(ids)}
        filas = []
        por_id = {}
        for t in tareas:
            fila = {
                "id": t["id"], "code": t["code"], "name": t["name"], "summary": t["summary"],
                "milestone": t["milestone"], "parent_id": t["parent_id"],
                "start": local(t["start"]), "end": local(t["end"]) or local(t["start"]),
                "progress": t.get("progress"),
                "critical": t["critical"], "float_days": holgura.get(t["id"]) or 0.0,
                # La banda de holgura termina en el fin más TARDÍO.
                "late_finish": local(t.get("late_finish")), "done": bool(t.get("actual_finish")),
                "baseline_start": local(t.get("baseline_start")), "baseline_end": local(t.get("baseline_end")),
                "deadline": local(t.get("deadline")),
                "duration_days": t.get("duration") or 0.0,
            }
            filas.append(fila)
            por_id[fila["id"]] = fila
        # Profundidad y fechas de los resúmenes desde sus hijas, como en el
        # planificador (planner.js `load`).
        for f in filas:
            padre = por_id.get(f["parent_id"])
            f["depth"] = padre["depth"] + 1 if padre else 0
        for f in reversed(filas):
            padre = por_id.get(f["parent_id"])
            if padre and f["start"]:
                padre.setdefault("_hijas", []).append(f)
        for f in reversed(filas):
            hijas = [h for h in f.pop("_hijas", []) if h["start"]]
            if hijas:
                f["start"] = min(h["start"] for h in hijas)
                f["end"] = max(h["end"] for h in hijas)
        if self.follow_view:
            try:
                filtradas = json.loads(self.filter_ids or "null")
            except ValueError:
                filtradas = None
            if isinstance(filtradas, list):
                filtradas = set(filtradas)
                filas = [f for f in filas if f["id"] in filtradas]
            plegadas = set(json.loads(self.collapsed_ids or "[]"))
            ocultas = set()
            for f in filas:
                if f["parent_id"] in plegadas or f["parent_id"] in ocultas:
                    ocultas.add(f["id"])
            filas = [f for f in filas if f["id"] not in ocultas]

        proyectos = env["project.task"].browse(ids).project_id
        cal = proyectos._work_calendar_record() if len(proyectos) == 1 else env.company.resource_calendar_id
        # `calendar_for` recibe FECHAS (date): con datetime, el primer feriado
        # global del calendario truena al compararse.
        hoy = fields.Date.context_today(self)
        work, cal_tz = calendar_for(cal, hoy - timedelta(days=3650), hoy + timedelta(days=3650))
        no_laborables = {d for d in range(7) if not work.turnos.get(d)}
        minutos = proyectos.minutes_per_day if len(proyectos) == 1 else 480

        def dias(n):
            return "%s d" % ("%g" % round(n, 2))

        # El texto de las columnas opcionales, como en el planificador.
        por_tarea = {t["id"]: t for t in tareas}
        codigo = {t["id"]: t["code"] for t in tareas}

        def vinculo(l, otro):
            tipo = "" if l["type"] == "fs" else l["type"].upper()
            desfase = ("%+g%s" % (l["lag"], "dn" if l.get("elapsed") else "d")) if l["lag"] else ""
            return "%s%s%s" % (codigo.get(otro, ""), (tipo or "FS") if (tipo or desfase) else "", desfase)

        def fecha_txt(valor):
            return valor.strftime(formato) if valor else ""

        for f in filas:
            t = por_tarea[f["id"]]
            f["cells"] = {
                "pred": "; ".join(vinculo(l, l["from"]) for l in datos["links"] if l["to"] == f["id"]),
                "succ": "; ".join(vinculo(l, l["to"]) for l in datos["links"] if l["from"] == f["id"]),
                "users": t.get("users") or "",
                "float": dias(f["float_days"]) if f["start"] else "",
                # La holgura libre (los resúmenes no la llevan).
                "free_float": dias(t.get("free_float") or 0.0) if f["start"] and not f["summary"] else "",
                "critical": "✔" if t.get("critical") else "",
                "constraint": ("%s %s" % (t.get("constraint_label") or "", fecha_txt(local(t.get("constraint_date"))))).strip()
                if (t.get("constraint") or "asap") != "asap" else "",
                "deadline": fecha_txt(f["deadline"]),
                "actual_start": fecha_txt(local(t.get("actual_start"))),
                "actual_end": fecha_txt(local(t.get("actual_finish"))),
                "baseline_start": fecha_txt(f["baseline_start"]),
                "baseline_end": fecha_txt(f["baseline_end"]),
            }

        # Las líneas base comparadas, en el orden y los colores del planificador.
        comparadas, nombres = self._report_compared(datos), []
        if comparadas:
            fechas = env["project.task"].planner_baseline_dates(self._report_domain(), [b["id"] for b in comparadas])
            nombres = [b["name"] for b in comparadas]
            for f in filas:
                f["compare"] = [
                    tuple(local(x) for x in fechas.get(str(b["id"]), {}).get(str(f["id"]), (None, None)))
                    for b in comparadas]
        actual = next((b["name"] for b in datos.get("baselines") or [] if b.get("current")), False)

        for i, f in enumerate(filas, 1):
            f["num"] = i
            f["start_label"] = f["start"].strftime(formato) if f["start"] else ""
            f["end_label"] = f["end"].strftime(formato) if f["end"] else ""
            if f["milestone"]:
                f["duration"] = dias(0)
            elif f["summary"] and f["start"]:
                inicio = tz.localize(f["start"]).astimezone(pytz.utc).replace(tzinfo=None)
                fin = tz.localize(f["end"]).astimezone(pytz.utc).replace(tzinfo=None)
                f["duration"] = dias(working_days(work, cal_tz, inicio, fin, False, minutos))
            else:
                f["duration"] = dias(f["duration_days"])
        con_fecha = [f for f in filas if f["start"]]
        if con_fecha:
            inicio = min(f["start"] for f in con_fecha)
            fin = max(f["end"] for f in con_fecha)
        else:
            inicio = fin = datetime.now(tz).replace(tzinfo=None)
        duracion = working_days(
            work, cal_tz, tz.localize(inicio).astimezone(pytz.utc).replace(tzinfo=None),
            tz.localize(fin).astimezone(pytz.utc).replace(tzinfo=None), False, minutos) if con_fecha else 0
        # Rango del eje: el proyecto con un margen, o la ventana del planificador.
        desde, hasta = inicio - timedelta(days=3), fin + timedelta(days=7)
        if self.follow_view and self.view_date_from and self.view_date_to:
            desde = pytz.utc.localize(self.view_date_from).astimezone(tz).replace(tzinfo=None)
            hasta = pytz.utc.localize(self.view_date_to).astimezone(tz).replace(tzinfo=None)
        _ = env._
        return {
            "title": self.title or datos["project"] or _("Schedule"),
            "company": self.company_name, "author": self.author,
            "printed": format_date(datetime.now(tz).date(), "long", locale=locale),
            "project_start": inicio.strftime(formato) if con_fecha else "",
            "project_finish": fin.strftime(formato) if con_fecha else "",
            "project_duration": dias(duracion) if con_fecha else "",
            "rows": filas, "links": datos["links"], "nonworking": no_laborables, "holidays": work.holidays,
            "today": datetime.now(tz).replace(tzinfo=None),
            "compare_names": nombres, "current_baseline": actual,
            "date_from": desde, "date_to": hasta, "locale": locale,
            "labels": {
                "printed": _("Printed"), "start": _("Start"), "finish": _("Finish"),
                "duration": _("Duration"), "author": _("Author"),
                "col_num": "#", "col_code": _("WBS"), "col_name": _("Task Name"),
                "col_duration": _("Duration"), "col_start": _("Start"), "col_end": _("Finish"),
                "col_progress": _("Prog."),
                "col_pred": _("Predecessors"), "col_succ": _("Successors"), "col_users": _("Assignees"),
                "col_float": _("Float"), "col_free_float": _("Free Float"), "col_critical": _("Crit."), "col_constraint": _("Constraint"),
                "col_deadline": _("Deadline"), "col_actual_start": _("Actual Start"),
                "col_actual_end": _("Actual Finish"), "col_baseline_start": _("Baseline Start"),
                "col_baseline_end": _("Baseline Finish"),
                "legend_task": _("Task"), "legend_critical": _("Critical task"),
                "legend_summary": _("Summary"), "legend_milestone": _("Milestone"),
                "legend_progress": _("Progress"), "legend_float": _("Float"),
                "legend_baseline": _("Baseline"), "legend_today": _("Today"),
                "legend_deadline": _("Deadline"),
            },
        }

    def _report_compared(self, datos):
        """Las versiones a comparar que el planificador pasó y que el
        proyecto ofrece de verdad (como máximo dos), en su orden."""
        if not self.show_baseline:
            return []
        try:
            ids = json.loads(self.compare_ids or "[]")
        except ValueError:
            return []
        ofrecidas = {b["id"]: b for b in datos.get("baselines") or [] if not b.get("current")}
        return [ofrecidas[i] for i in ids if i in ofrecidas][:2]

    def _report_columns(self):
        """Con «Seguir la vista», las columnas del planificador (su
        «Duración» se llama `dur` allá y `duration` aquí); si no, las de siempre."""
        if not self.follow_view:
            return None
        try:
            columnas = json.loads(self.view_columns or "[]")
        except ValueError:
            return None
        return [{"dur": "duration"}.get(c, c) for c in columnas if isinstance(c, str)] or None

    def _report_options(self):
        return {"columns": self._report_columns(), **{k: self[k] for k in (
            "paper", "orientation", "font_scale", "bar_colors", "status_line", "fit_to_paper",
            "timeline_pages", "scale", "repeat_header", "names_on_bars", "show_progress",
            "show_baseline", "show_float", "show_links", "workdays_only", "shade_weekends", "show_legend")}}

    def _render_pdf(self):
        """Los bytes del PDF y el nombre del archivo."""
        self.ensure_one()
        valores = self._report_values()
        try:
            pdf = GanttPdf(valores, self._report_options()).render()
        except ValueError as error:
            if str(error) == "timeline_too_narrow":
                raise UserError(self.env._(
                    "The paper is too narrow for the task table and the timeline: choose a larger paper, "
                    "landscape orientation or a smaller font size.")) from error
            raise
        nombre = "%s-planning.pdf" % (valores["title"] or "planner").replace("/", "-")
        return pdf, nombre
