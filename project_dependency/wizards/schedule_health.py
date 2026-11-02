# -*- coding: utf-8 -*-
"""La salud del cronograma —la evaluación DCMA de 14 puntos—.

Los catorce chequeos de la Defense Contract Management Agency de EE. UU.,
con las fórmulas y umbrales de su *EVMS Program Analysis Pamphlet* (DCMA-EA PAM
200.1, octubre de 2012). Es la revisión estándar de la industria para decidir
si un cronograma está bien construido ANTES de aprobarlo como línea base.

Cuenta las tareas HOJA no terminadas, sin hitos ni resúmenes, y los vínculos
que entran a ellas. Lee las tareas con los permisos de quien revisa (sin
`sudo()`); los vínculos y la holgura salen del mismo motor que «Calcular»
(`_scheduler_input`, `scheduler.slack`), así que el informe dice lo mismo que
el planificador.

Dos puntos difieren del manual de la DCMA porque el concepto no
existe aquí: «Duración alta» cuenta toda tarea no terminada (no solo la ventana
de detalle), y «Recursos» mira los asignados de la tarea (`user_ids`), no los
costos cargados. La línea base la aporta el módulo del dominio redefiniendo
`project.task._schedule_baseline()`; sin ella, los tres puntos que la
necesitan salen «no aplica».
"""
import copy

import pytz

from odoo import api, fields, models

from ..models.scheduler import schedule, slack

#: Umbrales del manual DCMA (en % salvo CPLI/BEI, que son índices).
MAX_SHARE = 5
MIN_FS_SHARE = 90
MIN_INDEX = 0.95
#: La prueba de la ruta crítica alarga una tarea crítica estos días laborables.
CP_TEST_DAYS = 100
HARD_CONSTRAINTS = ("mso", "mfo", "snlt", "fnlt")


class ReScheduleHealth(models.TransientModel):
    _name = "project.schedule.health"
    _description = "Schedule Health Check"

    project_id = fields.Many2one("project.project", string="Schedule", required=True,
                                 default=lambda self: self._default_project())
    status_date = fields.Datetime(string="Status Date", required=True, default=fields.Datetime.now,
                                  help="The date up to which progress is measured.")
    high_float_days = fields.Integer(string="High Float Above (working days)", default=44, required=True)
    high_duration_days = fields.Integer(string="Long Duration Above (working days)", default=44, required=True)
    line_ids = fields.One2many("project.schedule.health.line", "health_id", string="Checks", readonly=True)
    task_count = fields.Integer(string="Tasks Evaluated", readonly=True,
                                help="Incomplete leaf tasks, without milestones or summary tasks.")
    link_count = fields.Integer(string="Links Evaluated", readonly=True,
                                help="Links into the tasks evaluated.")
    passed_count = fields.Integer(string="Checks Passed", readonly=True)
    failed_count = fields.Integer(string="Checks Failed", readonly=True)

    @api.model
    def _default_project(self):
        if self.env.context.get("active_model") == "project.project":
            return self.env.context.get("active_id")
        return False

    def action_check(self):
        self.ensure_one()
        lineas = self._health_checks()
        self.line_ids.unlink()
        self.write({
            "line_ids": [fields.Command.create(v) for v in lineas],
            "passed_count": sum(1 for v in lineas if v["result"] == "pass"),
            "failed_count": sum(1 for v in lineas if v["result"] == "fail"),
        })
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new", "name": self.env._("Schedule Health Check")}

    # ------------------------------------------------------------------ cálculo
    def _health_checks(self):
        _ = self.env._
        Task = self.env["project.task"]
        entrada = Task._scheduler_input(self.project_id)
        tareas = entrada["tasks"]
        if not entrada["dates"]:
            self.task_count = self.link_count = 0
            return []
        datos, vinculos = entrada["data"], entrada["links"]
        cal, tz, mpd = entrada["cal"], entrada["tz"], entrada["mpd"]
        zona = pytz.timezone(tz)
        local = lambda dt: pytz.utc.localize(dt).astimezone(zona).replace(tzinfo=None)  # noqa: E731

        def dias(a, b):
            """Días laborables firmados de `a` a `b` (UTC naive)."""
            a, b = local(a), local(b)
            return (cal.between(a, b) if b >= a else -cal.between(b, a)) / mpd

        corte = self.status_date
        hojas = [i for i, d in datos.items() if not d["summary"]]
        evaluadas = [i for i in hojas if not datos[i]["milestone"] and not datos[i]["actual_finish"]
                     and datos[i]["start"] and datos[i]["end"]]
        conjunto = set(evaluadas)
        base = Task.browse(hojas)._schedule_baseline()

        # Un vínculo con un RESUMEN vale para sus hijas (como en el motor).
        padre = {i: d["parent"] for i, d in datos.items()}

        def ancestros(i):
            vistos = []
            while padre.get(i) in datos and padre[i] not in vistos:
                i = padre[i]
                vistos.append(i)
            return vistos

        con_pred, con_suc = set(), set()
        for v in vinculos:
            con_pred.add(v["succ"])
            con_suc.add(v["pred"])
        entrantes = [v for v in vinculos if v["succ"] in conjunto]
        self.task_count, self.link_count = len(evaluadas), len(entrantes)
        holgura = slack(datos, vinculos, cal, tz, mpd, project=entrada["options"])

        def pct(n, total):
            return 100.0 * n / total if total else 0.0

        lineas = []

        def linea(code, nombre, valor, umbral, ok, ids=(), na=False):
            lineas.append({
                "sequence": len(lineas) + 1, "code": code, "name": nombre, "value": valor, "threshold": umbral,
                "result": "na" if na else ("pass" if ok else "fail"),
                "task_ids": [fields.Command.set(sorted(set(ids)))],
            })

        def por_share(code, nombre, ids, total, maximo=MAX_SHARE):
            p = pct(len(ids), total)
            linea(code, nombre, "%s / %s (%.1f%%)" % (len(ids), total, p) if total else "—", "≤ %s%%" % maximo,
                  p <= maximo, ids, na=not total)

        def por_cero(code, nombre, ids, total, na=False):
            # Un punto que no aplica no muestra un conteo (se leía como hallazgo).
            no_aplica = na or not total
            linea(code, nombre, "—" if no_aplica else str(len(ids)), "0", not ids, () if no_aplica else ids,
                  na=no_aplica)

        # 1 · Lógica: sin predecesora o sin sucesora (propia o de un resumen ancestro).
        sueltas = [i for i in evaluadas
                   if not ({i, *ancestros(i)} & con_pred) or not ({i, *ancestros(i)} & con_suc)]
        por_share("logic", _("Logic: tasks missing a predecessor or a successor"), sueltas, len(evaluadas))
        # 2 · Adelantos (desfase negativo) · 3 · Desfases · 4 · Tipo de vínculo.
        adelantos = [v["succ"] for v in entrantes if (v["lag"] or 0) < 0]
        por_cero("leads", _("Leads: links with a negative lag"), adelantos, len(entrantes))
        desfases = [v for v in entrantes if (v["lag"] or 0) > 0]
        p = pct(len(desfases), len(entrantes))
        linea("lags", _("Lags: links with a positive lag"),
              "%s / %s (%.1f%%)" % (len(desfases), len(entrantes), p) if entrantes else "—",
              "≤ %s%%" % MAX_SHARE, p <= MAX_SHARE, [v["succ"] for v in desfases], na=not entrantes)
        no_fs = [v for v in entrantes if v["type"] != "fs"]
        p = 100.0 - pct(len(no_fs), len(entrantes))
        linea("link_types", _("Relationship types: share of finish-to-start links"),
              "%.1f%%" % p if entrantes else "—", "≥ %s%%" % MIN_FS_SHARE, p >= MIN_FS_SHARE, [v["succ"] for v in no_fs],
              na=not entrantes)
        # 5 · Restricciones duras.
        duras = [i for i in evaluadas if datos[i]["constraint"] in HARD_CONSTRAINTS]
        por_share("hard_constraints", _("Hard constraints: must start/finish on, start/finish no later than"),
                  duras, len(evaluadas))
        # 6 · Holgura alta · 7 · Holgura negativa (en días laborables, como el motor).
        tf = {i: holgura[i]["slack"] / mpd for i in evaluadas if i in holgura}
        por_share("high_float", _("High float: more than %s working days", self.high_float_days),
                  [i for i, h in tf.items() if h > self.high_float_days], len(evaluadas))
        por_cero("negative_float", _("Negative float"), [i for i, h in tf.items() if h < 0], len(evaluadas))
        # 8 · Duración alta: la de la línea base si la tarea está en ella.

        def duracion(i):
            if i in base:
                return dias(*base[i])
            return datos[i]["duration"] or dias(datos[i]["start"], datos[i]["end"])

        por_share("high_duration", _("High duration: more than %s working days", self.high_duration_days),
                  [i for i in evaluadas if duracion(i) > self.high_duration_days], len(evaluadas))
        # 9 · Fechas inválidas: lo real después del corte, lo pronosticado antes.
        invalidas = []
        for i in hojas:
            d = datos[i]
            real_tarde = (d["actual_start"] and d["actual_start"] > corte) or (
                d["actual_finish"] and d["actual_finish"] > corte)
            pronostico = (not d["actual_start"] and d["start"] and d["start"] < corte) or (
                not d["actual_finish"] and d["end"] and d["end"] < corte)
            if real_tarde or pronostico:
                invalidas.append(i)
        por_cero("invalid_dates", _("Invalid dates: actual dates after the status date or forecast dates before it"),
                 invalidas, len(hojas))
        # 10 · Recursos: solo si el cronograma usa asignados.
        por_id = {t.id: t for t in tareas}
        usa_recursos = any(por_id[i].user_ids for i in hojas)
        por_cero("resources", _("Resources: tasks without an assignee"),
                 [i for i in evaluadas if not por_id[i].user_ids], len(evaluadas), na=not usa_recursos)
        # 11 · Tareas incumplidas · 14 · BEI: necesitan línea base.
        debidas = [i for i in hojas if i in base and base[i][1] <= corte]
        incumplidas = [i for i in debidas
                       if not datos[i]["actual_finish"] or datos[i]["actual_finish"] > base[i][1]]
        p = pct(len(incumplidas), len(debidas))
        linea("missed_tasks", _("Missed tasks: due by the baseline but finished late or not finished"),
              "%s / %s (%.1f%%)" % (len(incumplidas), len(debidas), p) if debidas else "—", "≤ %s%%" % MAX_SHARE,
              p <= MAX_SHARE,
              incumplidas, na=not debidas)
        # 12 · Prueba de la ruta crítica: alargar una crítica debe mover el fin lo mismo.
        self._critical_path_test(linea, entrada, holgura, evaluadas)
        # 13 · CPLI: (largo de la ruta crítica + holgura contra el fin base) / largo.
        fin = max(d["end"] for d in datos.values() if d["end"])
        fin_base = max((b[1] for b in base.values()), default=None)
        largo = dias(corte, fin)
        if fin_base and largo > 0:
            cpli = (largo + dias(fin, fin_base)) / largo
            linea("cpli", _("Critical Path Length Index (CPLI)"), "%.2f" % cpli, "≥ %s" % MIN_INDEX, cpli >= MIN_INDEX)
        else:
            linea("cpli", _("Critical Path Length Index (CPLI)"), "—", "≥ %s" % MIN_INDEX, False, na=True)
        terminadas = [i for i in hojas if datos[i]["actual_finish"] and datos[i]["actual_finish"] <= corte]
        if debidas:
            bei = len(terminadas) / len(debidas)
            linea("bei", _("Baseline Execution Index (BEI)"), "%.2f" % bei, "≥ %s" % MIN_INDEX, bei >= MIN_INDEX,
                  [i for i in debidas if i not in terminadas])
        else:
            linea("bei", _("Baseline Execution Index (BEI)"), "—", "≥ %s" % MIN_INDEX, False, na=True)
        # El orden del manual DCMA: CPLI (13) antes de BEI (14), la prueba de ruta crítica (12) antes.
        orden = ["logic", "leads", "lags", "link_types", "hard_constraints", "high_float", "negative_float",
                 "high_duration", "invalid_dates", "resources", "missed_tasks", "critical_path_test", "cpli", "bei"]
        lineas.sort(key=lambda v: orden.index(v["code"]))
        for n, v in enumerate(lineas, 1):
            v["sequence"] = n
        return lineas

    def _critical_path_test(self, linea, entrada, holgura, evaluadas):
        """Punto 12: en una COPIA, alarga la primera tarea crítica no terminada
        `CP_TEST_DAYS` días laborables y recalcula. Pasa si el fin del proyecto
        se mueve lo mismo: la ruta crítica está unida de verdad (sin
        restricciones ni huecos que absorban el retraso). No escribe nada."""
        _ = self.env._
        nombre = _("Critical path test: delaying a critical task delays the finish as much")
        umbral = _("%s working days", CP_TEST_DAYS)
        datos, mpd = entrada["data"], entrada["mpd"]
        criticas = sorted((i for i in evaluadas if holgura.get(i, {}).get("critical")),
                          key=lambda i: datos[i]["start"])
        desde_fin = not entrada["options"].get("from_start", True)
        if not criticas or desde_fin:
            linea("critical_path_test", nombre, "—", umbral, False, na=True)
            return
        args = (entrada["links"], entrada["cal"], entrada["tz"], mpd)
        antes, _c, _o = schedule(copy.deepcopy(datos), *args, project=entrada["options"])
        prueba = copy.deepcopy(datos)
        objetivo = criticas[0]
        prueba[objetivo]["duration"] = (prueba[objetivo]["duration"] or 0) + CP_TEST_DAYS
        despues, _c, _o = schedule(prueba, *args, project=entrada["options"])
        zona = pytz.timezone(entrada["tz"])
        local = lambda dt: pytz.utc.localize(dt).astimezone(zona).replace(tzinfo=None)  # noqa: E731
        fin_a = local(max(e for _s, e in antes.values()))
        fin_d = local(max(e for _s, e in despues.values()))
        movido = entrada["cal"].between(fin_a, fin_d) / mpd
        # Medio día de tolerancia por el redondeo del cierre del turno.
        linea("critical_path_test", nombre, _("%.1f working days", movido), umbral,
              movido >= CP_TEST_DAYS - 0.5, [objetivo])


class ReScheduleHealthLine(models.TransientModel):
    _name = "project.schedule.health.line"
    _description = "Schedule Health Check Result"
    _order = "sequence"

    health_id = fields.Many2one("project.schedule.health", string="Health Check", required=True, ondelete="cascade")
    sequence = fields.Integer(string="#")
    code = fields.Char(string="Code")
    name = fields.Char(string="Check")
    value = fields.Char(string="Value")
    threshold = fields.Char(string="Threshold")
    result = fields.Selection([("pass", "Pass"), ("fail", "Fail"), ("na", "Not applicable")], string="Result")
    task_ids = fields.Many2many("project.task", string="Tasks")
    task_count = fields.Integer(string="Tasks Found", compute="_compute_task_count")

    @api.depends("task_ids")
    def _compute_task_count(self):
        for linea in self:
            linea.task_count = len(linea.task_ids)

    def action_open_tasks(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": self.name, "res_model": "project.task",
            "view_mode": "list,form", "domain": [("id", "in", self.task_ids.ids)], "target": "current",
        }
