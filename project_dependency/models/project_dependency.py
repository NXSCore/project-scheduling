# -*- coding: utf-8 -*-
"""Vínculos entre tareas con TIPO y DESFASE, que Odoo no tiene.

Odoo 19 trae `project.task.depend_on_ids`: un Many2many pelado, sin tipo y sin
desfase (`project/models/project_task.py:281`). Eso es un fin-a-inicio
implícito y nada más; `project_enterprise` tampoco los añade.

Sin tipos, la ruta crítica se calcula mal: dos ingenierías que arrancan juntas
obligadas a ir en fila alargan el proyecto y ponen en la ruta a quien no está.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

#: Los cuatro de la teoría de redes, con las siglas que usa la industria.
LINK_TYPES = [
    ("fs", "Finish to Start (FS)"),
    ("ss", "Start to Start (SS)"),
    ("ff", "Finish to Finish (FF)"),
    ("sf", "Start to Finish (SF)"),
]


class ReProjectDependency(models.Model):
    _name = "project.dependency"
    _description = "Typed Task Dependency"
    _rec_name = "successor_id"

    predecessor_id = fields.Many2one(
        "project.task", string="Predecessor", required=True,
        index=True, ondelete="cascade",
    )
    successor_id = fields.Many2one(
        "project.task", string="Successor", required=True,
        index=True, ondelete="cascade",
    )
    link_type = fields.Selection(
        LINK_TYPES, string="Type", required=True, default="fs",
    )
    # Negativo a propósito: un desfase de -3 es un ADELANTO, tan real como la
    # espera, y muchos cronogramas de construcción lo usan para solapar.
    lag_days = fields.Float(
        string="Lag (days)", default=0.0, digits=(6, 1),
        help="Days between the two ends. Negative means overlap (lead).",
    )
    # El desfase transcurrido de MS Project («edías»): cuenta días
    # naturales en vez de laborables.
    lag_elapsed = fields.Boolean(
        string="Calendar Days",
        help="The lag counts calendar days instead of working days, as an elapsed lag in Microsoft Project.",
    )
    project_id = fields.Many2one(
        "project.project", string="Project", related="successor_id.project_id",
        store=True, index=True,
    )
    company_id = fields.Many2one(
        "res.company", string="Company", related="successor_id.company_id",
        store=True, index=True,
    )

    _unique_pair = models.Constraint(
        "unique (predecessor_id, successor_id)",
        "These two tasks are already linked.",
    )

    @api.constrains("predecessor_id", "successor_id")
    def _check_not_itself_and_no_cycles(self):
        """Un ciclo no es un cronograma: no tiene inicio ni fin que calcular."""
        for vinculo in self:
            if vinculo.predecessor_id == vinculo.successor_id:
                raise ValidationError(_("A task cannot depend on itself."))
        for proyecto in self.mapped("project_id"):
            if self._has_a_cycle(proyecto):
                raise ValidationError(_(
                    "That link closes a loop: the tasks would wait for each "
                    "other forever and the schedule could not be calculated."))

    @api.model
    def _has_a_cycle(self, project):
        """Recorrido en profundidad sobre TODA la red del proyecto.

        Mirar solo el vínculo que se añade no basta: el ciclo puede cerrarse a
        tres saltos de distancia.
        """
        sucesores = {}
        # sudo(): detectar un ciclo exige ver la red COMPLETA del proyecto;
        # un vínculo que el usuario no alcanza por permisos sigue cerrando el
        # ciclo. Solo se leen ids, nada vuelve al usuario.
        for vinculo in self.sudo().search([("project_id", "=", project.id)]):
            sucesores.setdefault(vinculo.predecessor_id.id, []).append(
                vinculo.successor_id.id)
        VISITANDO, LISTO = 1, 2
        estado = {}

        def hay_ciclo(nodo):
            estado[nodo] = VISITANDO
            for siguiente in sucesores.get(nodo, ()):
                if estado.get(siguiente) == VISITANDO:
                    return True
                if estado.get(siguiente) != LISTO and hay_ciclo(siguiente):
                    return True
            estado[nodo] = LISTO
            return False

        return any(hay_ciclo(n) for n in list(sucesores) if n not in estado)

    def _sync_native_dependency(self):
        """Refleja los fin-a-inicio sin desfase en `depend_on_ids`.

        Así el Gantt de Odoo sigue dibujando la flecha y su lógica de tarea
        bloqueada sigue valiendo. Los otros tipos NO se reflejan: dibujarlos
        como fin-a-inicio diría en pantalla algo distinto de lo que se calcula,
        y un diagrama que miente es peor que uno incompleto.
        """
        for vinculo in self:
            nativo = vinculo.link_type == "fs" and not vinculo.lag_days
            ya_esta = vinculo.predecessor_id in vinculo.successor_id.depend_on_ids
            if nativo and not ya_esta:
                vinculo.successor_id.depend_on_ids = [(4, vinculo.predecessor_id.id)]
            elif not nativo and ya_esta:
                vinculo.successor_id.depend_on_ids = [(3, vinculo.predecessor_id.id)]

    @api.model
    def action_edit_from_gantt(self, master_id, slave_id):
        """Abre el vínculo de esa flecha para editar su tipo y su desfase.

        Si todavía no existe como `project.dependency` se crea al vuelo:
        puede venir de una flecha que alguien dibujó antes de instalar este
        módulo, y contestarle al usuario que no hay nada que editar cuando está
        mirando la flecha sería absurdo. Nace fin-a-inicio, que es lo que esa
        flecha significaba hasta ahora.
        """
        vinculo = self.search([
            ("predecessor_id", "=", master_id), ("successor_id", "=", slave_id),
        ], limit=1)
        if not vinculo:
            vinculo = self.create({
                "predecessor_id": master_id, "successor_id": slave_id,
                "link_type": "fs", "lag_days": 0.0,
            })
        return {
            "type": "ir.actions.act_window",
            "name": _("Dependency type"),
            "res_model": "project.dependency",
            "res_id": vinculo.id,
            "view_mode": "form",
            "views": [(self.env.ref(
                "project_dependency.project_dependency_view_form").id, "form")],
            "target": "new",
        }

    @api.model_create_multi
    def create(self, vals_list):
        vinculos = super().create(vals_list)
        vinculos._sync_native_dependency()
        return vinculos

    def write(self, vals):
        resultado = super().write(vals)
        if "link_type" in vals or "lag_days" in vals:
            self._sync_native_dependency()
        return resultado

    def unlink(self):
        """El vínculo se va con su flecha nativa. Si quedara en
        `depend_on_ids`, al reimportar un cronograma con otra versión de los
        vínculos chocaría con la flecha nueva en sentido contrario («Dos tareas no
        pueden depender la una de la otra»)."""
        pares = [(v.successor_id, v.predecessor_id) for v in self]
        resultado = super().unlink()
        for sucesora, predecesora in pares:
            if sucesora.exists() and predecesora in sucesora.depend_on_ids:
                sucesora.depend_on_ids = [(3, predecesora.id)]
        return resultado
