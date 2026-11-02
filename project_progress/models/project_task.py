# -*- coding: utf-8 -*-
"""El avance físico de una tarea, para CUALQUIER proyecto.

El avance reportado, el esperado según las fechas, la brecha, el reporte con su
evidencia —o la constancia de que no la hubo— y el recordatorio semanal. Un
módulo de extensión puede acotar el recordatorio (`_progress_reminder_domain`)
o calcular el avance de otra forma.
"""
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

#: El estado "Finalizada" de Odoo (`project/models/project_task.py:85`).
DONE_STATE = "1_done"
#: Y el de cancelada. Odoo las mete a las dos en `CLOSED_STATES`, pero para
#: el avance no son lo mismo: una terminada cumplió el plan, una cancelada
#: salió de él.
CANCELED_STATE = "1_canceled"

#: Clave de contexto que declara "esta escritura del avance viene por su cauce"
#: —el asistente de reporte—. La define el dueño del CAMPO, no quien la exige.
#: La revisa `project_task_progress_report.write()`, en este mismo módulo.
PROGRESS_SEAM = "progress_with_evidence"

#: La cadencia del recordatorio de avance.
REPORT_EVERY_DAYS = 7


class ProjectTask(models.Model):
    _inherit = "project.task"

    # "Registro de Avance Físico", capturado a mano.
    #
    # Va en la TAREA y no solo en el proyecto: un porcentaje único por proyecto
    # no dice qué parte va atrasada.
    #
    # Se puede escribir con la línea base congelada, a propósito: la línea base
    # congela el PLAN, y el avance real es un HECHO posterior. Prohibirlo haría
    # que congelar el cronograma impidiera reportar cómo va el proyecto.
    physical_progress = fields.Float(
        string="Physical Progress", default=0.0, tracking=True, aggregator="avg",
        help="Reported physical progress of this task, in percent.",
    )
    # El lado PLANIFICADO de la comparativa.
    #
    # Es el avance que la tarea DEBERÍA llevar hoy según sus propias fechas,
    # repartido linealmente. Lineal es una convención, no una medición: no hay
    # una curva de avance definida, y suponer una sería
    # inventar el dato. Queda dicho para que nadie lo lea como un pronóstico.
    expected_progress = fields.Float(
        string="Expected Progress", compute="_compute_progress_gap",
        help="Progress this task should have today according to its planned dates.",
    )
    progress_gap = fields.Float(
        string="Progress Gap", compute="_compute_progress_gap", store=False,
        help="Reported progress minus expected progress. Negative means behind.",
    )

    @api.constrains("physical_progress")
    def _check_physical_progress_range(self):
        for tarea in self:
            if not 0.0 <= tarea.physical_progress <= 100.0:
                raise ValidationError(_(
                    "Physical progress of %(task)s must be between 0 and 100.",
                    task=tarea.display_name,
                ))

    @api.depends("physical_progress", "planned_date_begin", "date_deadline", "state")
    def _compute_progress_gap(self):
        """Avance esperado hoy, y la diferencia contra el reportado.

        Una tarea terminada espera 100: si ya terminó, lo planeado era
        terminarla. Una CANCELADA no: salió del plan, y exigirle 100 la
        contaría como atrasada para siempre.

        Sin fechas no hay plan contra el que medir y la comparativa se deja
        vacía en vez de suponer cero, que leería como "atrasada".
        """
        ahora = fields.Datetime.now()
        for tarea in self:
            if tarea.state == DONE_STATE:
                esperado = 100.0
            elif (tarea.state == CANCELED_STATE
                  or not tarea.planned_date_begin or not tarea.date_deadline):
                tarea.expected_progress = 0.0
                tarea.progress_gap = 0.0
                continue
            else:
                total = (tarea.date_deadline - tarea.planned_date_begin).total_seconds()
                if total <= 0:
                    # Una tarea que empieza y acaba a la vez es un hito: o pasó
                    # su fecha y se esperaba entera, o no y se esperaba nada.
                    esperado = 100.0 if ahora >= tarea.date_deadline else 0.0
                else:
                    transcurrido = (ahora - tarea.planned_date_begin).total_seconds()
                    esperado = max(0.0, min(100.0, transcurrido / total * 100.0))
            tarea.expected_progress = esperado
            tarea.progress_gap = tarea.physical_progress - esperado

    progress_reported_on = fields.Datetime(
        string="Progress Reported On", readonly=True, copy=False,
        help="When the physical progress of this task was last reported.",
    )
    # El avance se puede reportar SIN evidencia, pero no
    # en silencio. La marca queda en la tarea —no solo en el chatter— para que
    # el PM pueda filtrar las tareas cuyo último avance no tiene respaldo.
    progress_without_evidence = fields.Boolean(
        string="Last Report Without Evidence", readonly=True, copy=False,
        help="The last physical progress report of this task was made without "
             "a supporting document.",
    )
    progress_is_stale = fields.Boolean(
        string="Progress Out of Date", compute="_compute_progress_is_stale",
        search="_search_progress_is_stale",
    )

    @api.depends("progress_reported_on")
    def _compute_progress_is_stale(self):
        limite = fields.Datetime.now() - timedelta(days=REPORT_EVERY_DAYS)
        for tarea in self:
            tarea.progress_is_stale = bool(
                tarea.progress_reported_on
                and tarea.progress_reported_on < limite)

    def _search_progress_is_stale(self, operator, value):
        limite = fields.Datetime.now() - timedelta(days=REPORT_EVERY_DAYS)
        dominio = [("progress_reported_on", "<", limite)]
        if (operator in ("=", "in")) == bool(value):
            return dominio
        return ["!"] + dominio

    def write(self, vals):
        """Capturar avance exige pasar por el asistente, que trae la evidencia
        o deja constancia de que no la hubo.

        El candado va aquí y no en un botón porque el formulario, la lista y
        RPC son tres caminos distintos al mismo campo. Y no en un
        `@api.constrains` porque en Odoo 19 corren con `sudo()` y no pueden
        leer el contexto que dice si hubo evidencia.
        """
        if "physical_progress" in vals and not self.env.context.get(PROGRESS_SEAM):
            raise UserError(_(
                "Physical progress is reported with the document that backs it. "
                "Use the Report Progress button."))
        if "physical_progress" in vals:
            vals.setdefault("progress_reported_on", fields.Datetime.now())
        return super().write(vals)

    def action_open_progress_report(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Report Progress — %(task)s", task=self.display_name),
            "res_model": "project.progress.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_task_id": self.id,
                        "default_progress": self.physical_progress},
        }

    @api.model
    def _progress_reminder_domain(self):
        """Gancho: qué tareas entran al recordatorio semanal. Aquí, todas; una
        extensión lo acota."""
        return []

    @api.model
    def _cron_remind_weekly_progress(self):
        """Recuerda a quien tiene la tarea que le toca reportar.

        Se recuerda a QUIEN LA TIENE y no al PM: el PM no puede reportar el
        avance de una ingeniería que no ejecuta, y mandárselo a él solo
        convierte el recordatorio en trabajo de reenvío.

        Solo tareas ya empezadas y no cerradas: pedir avance de algo que no ha
        arrancado es ruido garantizado.
        """
        ahora = fields.Datetime.now()
        candidatas = self.search([
            ("planned_date_begin", "<=", ahora),
            ("state", "not in", ("1_done", "1_canceled")),
        ] + self._progress_reminder_domain())
        for tarea in candidatas:
            reportado = tarea.progress_reported_on
            if reportado and (ahora - reportado).days < REPORT_EVERY_DAYS:
                continue
            destinatarios = tarea.user_ids.partner_id
            if not destinatarios:
                continue
            tarea.sudo().message_notify(
                partner_ids=destinatarios.ids,
                subject=_("Weekly progress due: %(task)s", task=tarea.name),
                body=Markup("<p>%s</p>") % _(
                    "The physical progress of %(task)s has not been reported "
                    "for a week. Report it with its evidence.", task=tarea.display_name),
            )
