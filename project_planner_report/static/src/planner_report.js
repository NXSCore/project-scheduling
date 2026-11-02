/** @odoo-module **/
/**
 * Botón «Informe» del planificador. Abre el asistente del PDF con las
 * tareas que se están viendo (`domain`) y, para «Seguir la vista», la ventana
 * de fechas visible y las ramas plegadas.
 */
import { patch } from "@web/core/utils/patch";
import { serializeDateTime } from "@web/core/l10n/dates";
import { PlannerCore } from "@project_planner/planner/planner";

const { DateTime } = luxon;
const DAY_MS = 86400000;

patch(PlannerCore.prototype, {
    openReport() {
        const el = this.scrollerRef.el;
        const context = {
            default_domain: JSON.stringify(this.props.domain || []),
            default_title: this.state.project || false,
            default_collapsed_ids: JSON.stringify([...this.collapsed]),
            // Con «Seguir la vista», el PDF imprime estas columnas.
            default_view_columns: JSON.stringify(this.state.columns || []),
            // Con «Seguir la vista», solo las tareas que deja ver el filtro.
            default_filter_ids: JSON.stringify(this.filterKeep ? [...this.filterKeep] : null),
            // Las líneas base que se están comparando; con la vigente las
            // imprime y activa «Línea base».
            default_compare_ids: JSON.stringify(this.state.compare || []),
            default_show_baseline: Boolean(this.state.compare?.length) || undefined,
        };
        if (el && this.t0) {
            const desde = this.t0 + (el.scrollLeft / this.dayW) * DAY_MS;
            const hasta = desde + (el.clientWidth / this.dayW) * DAY_MS;
            context.default_view_date_from = serializeDateTime(DateTime.fromMillis(desde));
            context.default_view_date_to = serializeDateTime(DateTime.fromMillis(hasta));
        }
        return this.action.doAction("project_planner_report.project_planner_report_wizard_action", {
            additionalContext: context,
        });
    },
});
