# -*- coding: utf-8 -*-
"""Dos reportes de tabla del cronograma.

- **Pronóstico a corto plazo** (*Look-ahead*): lo que corre o arranca en el
  periodo, la lista de la junta semanal. Entran las tareas no terminadas que
  tocan el periodo, más las vencidas de antes del día de referencia, mientras
  el periodo no termine antes de ese día.
- **Críticas y casi críticas**: las que fijan el fin del proyecto y las que
  están a punto de hacerlo (holgura mayor que 0 y hasta el umbral, en días
  laborables), ordenadas por holgura y por inicio.

El estado de cada fila es siempre contra el día de referencia: «Vencida» (sin
terminar y su fin ya pasó), «Debió empezar» (sin empezar y su inicio ya pasó),
«En curso» o «Por empezar». Lo que la tarea lleva lo da
`project.task._schedule_progress()`, que un módulo de extensión puede redefinir.

Lee las tareas con los permisos de quien lo pide (sin `sudo()`); la holgura
sale del mismo motor que el planificador. No escribe nada.
"""
from dateutil.relativedelta import relativedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.scheduler import slack

#: Semanas de los periodos «siguientes N semanas»: 1, 2, 4, 6, 8 y 12.
PERIODS = [("next_1w", "Next week"), ("next_2w", "Next 2 weeks"), ("next_4w", "Next 4 weeks"),
           ("next_6w", "Next 6 weeks"), ("next_8w", "Next 8 weeks"), ("next_12w", "Next 12 weeks"),
           ("next_month", "Next month"), ("custom", "Custom")]
STATUSES = [("overdue", "Overdue"), ("should_have_started", "Should have started"),
            ("in_progress", "In progress"), ("starting", "Starting")]


class ReScheduleReport(models.TransientModel):
    _name = "project.schedule.report"
    _description = "Schedule Report"

    project_id = fields.Many2one("project.project", string="Schedule", required=True,
                                 default=lambda self: self._default_project())
    report_type = fields.Selection([("lookahead", "Look-ahead"), ("critical", "Critical and near-critical")],
                                   string="Report", required=True, default="lookahead")
    reference_date = fields.Date(string="Reference Day", required=True, default=fields.Date.context_today,
                                 help="The day the status of each task is measured against, usually the status date.")
    period = fields.Selection(PERIODS, string="Period", required=True, default="next_month")
    date_from = fields.Date(string="From")
    date_to = fields.Date(string="To")
    near_critical_days = fields.Float(string="Near-critical Up To (working days)", default=5.0, required=True,
                                      help="A task with more than 0 and at most this float is near-critical.")
    line_ids = fields.One2many("project.schedule.report.line", "report_id", string="Tasks", readonly=True)
    activity_count = fields.Integer(string="Activities", readonly=True)
    overdue_count = fields.Integer(string="Overdue", readonly=True)
    should_have_started_count = fields.Integer(string="Should Have Started", readonly=True)
    in_progress_count = fields.Integer(string="In Progress", readonly=True)
    starting_count = fields.Integer(string="Starting", readonly=True)
    critical_count = fields.Integer(string="Critical", readonly=True)
    near_critical_count = fields.Integer(string="Near-critical", readonly=True)
    computed = fields.Boolean(readonly=True)

    @api.model
    def _default_project(self):
        if self.env.context.get("active_model") == "project.project":
            return self.env.context.get("active_id")
        return False

    def _window(self):
        """El periodo: N semanas de 7 días desde el día de referencia
        (los dos cuentan), o un mes calendario hasta el día anterior."""
        ref = self.reference_date
        if self.period == "custom":
            if not (self.date_from and self.date_to):
                raise UserError(self.env._("Fill in both dates."))
            if self.date_to < self.date_from:
                raise UserError(self.env._("The end date is before the start date."))
            return self.date_from, self.date_to
        if self.period == "next_month":
            return ref, ref + relativedelta(months=1, days=-1)
        semanas = int(self.period[len("next_"):-1])
        return ref, ref + relativedelta(days=7 * semanas - 1)

    def action_run(self):
        self.ensure_one()
        desde, hasta = self._window()
        filas = self._rows(desde, hasta)
        self.line_ids.unlink()
        cuenta = lambda estado: sum(1 for f in filas if f["status"] == estado)  # noqa: E731
        self.write({
            "date_from": desde, "date_to": hasta, "computed": True,
            "line_ids": [fields.Command.create(f) for f in filas],
            "activity_count": len(filas), "overdue_count": cuenta("overdue"),
            "should_have_started_count": cuenta("should_have_started"), "in_progress_count": cuenta("in_progress"),
            "starting_count": cuenta("starting"),
            "critical_count": sum(1 for f in filas if f["critical"]),
            "near_critical_count": sum(1 for f in filas if f["near_critical"]),
        })
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new", "name": dict(self._fields["report_type"]._description_selection(self.env))[
                    self.report_type]}

    def action_print(self):
        self.ensure_one()
        if not self.computed:
            self.action_run()
        return self.env.ref("project_dependency.project_schedule_report_pdf").report_action(self)

    def action_open_tasks(self):
        """Las mismas tareas en la lista de Odoo, para exportarlas a Excel."""
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": self.env._("Tasks of the Report"), "res_model": "project.task",
                "view_mode": "list,form", "domain": [("id", "in", self.line_ids.task_id.ids)], "target": "current"}

    # ------------------------------------------------------------------ cálculo
    def _rows(self, desde, hasta):
        Task = self.env["project.task"]
        entrada = Task._scheduler_input(self.project_id)
        if not entrada["dates"]:
            return []
        datos, mpd = entrada["data"], entrada["mpd"]
        zona = pytz.timezone(entrada["tz"])
        local = lambda dt: pytz.utc.localize(dt).astimezone(zona).replace(tzinfo=None)  # noqa: E731
        holgura = slack(datos, entrada["links"], entrada["cal"], entrada["tz"], mpd, project=entrada["options"])
        hojas = entrada["tasks"].filtered(lambda t: not datos[t.id]["summary"] and t.planned_date_begin
                                          and t.date_deadline)
        avance = hojas._schedule_progress()
        ref = self.reference_date
        umbral = self.near_critical_days
        filas = []
        for t in hojas:
            pct = avance.get(t.id, 0.0)
            if pct >= 100:
                continue
            inicio, fin = local(t.planned_date_begin).date(), local(t.date_deadline).date()
            h = holgura.get(t.id) or {}
            tf = (h.get("slack") or 0.0) / mpd
            critica = bool(h.get("critical"))
            casi = not critica and 0 < tf <= umbral
            if pct > 0:
                estado = "overdue" if fin < ref else "in_progress"
            elif fin < ref:
                estado = "overdue"
            elif inicio < ref:
                estado = "should_have_started"
            else:
                estado = "starting"
            if self.report_type == "lookahead":
                toca = inicio <= hasta and fin >= desde
                vencida = fin < ref and hasta >= ref
                if not (toca or vencida):
                    continue
            elif not (critica or casi):
                continue
            filas.append({
                "task_id": t.id, "wbs": t.wbs_code or "", "name": t.name,
                "date_start": t.planned_date_begin, "date_end": t.date_deadline,
                "remaining_days": round((t.duration_days or 0.0) * (100 - pct) / 100, 1),
                "progress": pct, "total_float": round(tf, 1), "critical": critica, "near_critical": casi,
                # La holgura libre («FF»).
                "free_float": round((h.get("free") or 0.0) / mpd, 1),
                "assignees": ", ".join(t.user_ids.mapped("name")), "status": estado,
            })
        if self.report_type == "critical":
            filas.sort(key=lambda f: (not f["critical"], f["total_float"], f["date_start"]))
        else:
            filas.sort(key=lambda f: (f["date_start"], f["wbs"]))
        for n, f in enumerate(filas, 1):
            f["sequence"] = n
        return filas


class ReScheduleReportLine(models.TransientModel):
    _name = "project.schedule.report.line"
    _description = "Schedule Report Line"
    _order = "sequence"

    report_id = fields.Many2one("project.schedule.report", string="Report", required=True, ondelete="cascade")
    sequence = fields.Integer(string="#")
    task_id = fields.Many2one("project.task", string="Task Record")
    wbs = fields.Char(string="WBS")
    name = fields.Char(string="Task")
    date_start = fields.Datetime(string="Start")
    date_end = fields.Datetime(string="Finish")
    remaining_days = fields.Float(string="Remaining (working days)", digits=(16, 1))
    progress = fields.Float(string="Progress (%)", digits=(16, 1))
    total_float = fields.Float(string="Total Float (working days)", digits=(16, 1))
    free_float = fields.Float(string="Free Float (working days)", digits=(16, 1))
    critical = fields.Boolean(string="Critical")
    near_critical = fields.Boolean(string="Near-critical")
    assignees = fields.Char(string="Assignees")
    status = fields.Selection(STATUSES, string="Status")
