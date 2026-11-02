/** @odoo-module **/
/**
 * Un selector de tipo DENTRO del conector del Gantt.
 *
 * El conector nativo de Odoo trae un solo botón —quitar— y crea siempre un
 * fin-a-inicio, porque `depend_on_ids` no sabe expresar otra cosa. Esto
 * permite elegir el tipo sin salir del Gantt.
 *
 * Esto extiende dos componentes de Enterprise por `patch()`, sin copiarlos.
 * El precio está dicho en voz alta: si Odoo cambia la forma de `GanttConnector`
 * o del renderer, esto se rompe y hay que revisarlo en la actualización. Se
 * extiende lo MÍNIMO —un prop y un manejador por componente— justo para que
 * ese día la revisión sea corta.
 */
import { patch } from "@web/core/utils/patch";
import { GanttConnector } from "@web_gantt/gantt_connector";
import { GanttRenderer } from "@web_gantt/gantt_renderer";

patch(GanttConnector.prototype, {
    onEditButtonClick() {
        if (this.props.onEditButtonClick) {
            this.props.onEditButtonClick();
        }
    },
});

// El prop es opcional: cualquier otro Gantt del sistema que no lo pase sigue
// funcionando igual. Sin `optional`, la validación de OWL tumbaría el Gantt de
// planificación, el de field service y todos los demás.
GanttConnector.props = {
    ...GanttConnector.props,
    onEditButtonClick: { type: Function, optional: true },
};

patch(GanttRenderer.prototype, {
    /**
     * Abre el vínculo tipado de esa flecha. Si todavía no existe como
     * `project.dependency` —porque lo dibujó el Gantt antes de que este
     * módulo estuviera— se crea al vuelo en el servidor: el usuario pidió
     * editarlo, no le vamos a contestar que no hay nada que editar.
     */
    async onEditButtonClick(connectorId) {
        const { masterId, slaveId } = this.getRecordIds(connectorId);
        if (!masterId || !slaveId) {
            return;
        }
        const action = await this.env.services.orm.call(
            "project.dependency",
            "action_edit_from_gantt",
            [masterId, slaveId]
        );
        await this.env.services.action.doAction(action, {
            onClose: () => this.model.fetchData(),
        });
    },
});
