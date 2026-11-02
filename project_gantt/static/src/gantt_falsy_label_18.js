/** @odoo-module **/
// Solo en la rama 18.0. Odoo 19 rotula el grupo vacío de un Many2one con el atributo de campo
// `falsy_value_label` (web_gantt/static/src/gantt_model.js, 19.0); Odoo 18 no lo tiene y escribe
// «Grupo (Nivel 2) indefinido» (`_getFieldFormattedValue`, 18.0). En el Gantt por EDT ese grupo
// junta lo que no se desglosa, así que se rotula igual que en 19: «Tareas sin desglose».
//
// Se parchea GanttModel y no TaskGanttModel: el de tareas resuelve sus propios campos
// (user_ids, project_id) y delega el resto en super (project_enterprise, task_gantt_model.js).
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { GanttModel } from "@web_gantt/gantt_model";

const WBS_GROUPS = ["wbs_level2_id", "wbs_level3_id"];

patch(GanttModel.prototype, {
    _getRowName(metaData, groupedByField, value) {
        if (!value && metaData.resModel === "project.task" && WBS_GROUPS.includes(groupedByField)) {
            return _t("Tasks without breakdown");
        }
        return super._getRowName(...arguments);
    },
});
