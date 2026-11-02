/** @odoo-module **/
/**
 * Las dos entradas al planificador, que comparten `PlannerCore`.
 *
 * - Acción cliente `schedule_planner`: a pantalla completa, por dominio o
 *   por proyecto (para un botón «Planificador» en cualquier ficha).
 * - Vista `planner`: en el selector de vistas, junto al Gantt de Odoo, con
 *   la barra de búsqueda, filtros y favoritos; los datos salen del dominio de
 *   la búsqueda.
 */
import { Component, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { standardViewProps } from "@web/views/standard_view_props";
import { PlannerCore } from "./planner";

export class PlannerAction extends Component {
    static template = xml`<div class="o_action o_sched_planner_action h-100"><PlannerCore fetch="fetch" domain="domain"/></div>`;
    static components = { PlannerCore };
    static props = ["*"];

    setup() {
        // Genérica. `params.domain` (las tareas a mostrar) o
        // `params.project_id` (un `project.project`); un módulo de
        // extensión solo arma el dominio.
        const orm = useService("orm");
        const params = this.props.action?.params || {};
        const domain = params.domain || (params.project_id ? [["project_id", "=", params.project_id]] : []);
        this.domain = domain;
        this.fetch = () => orm.call("project.task", "planner_data", [domain]);
    }
}
registry.category("actions").add("schedule_planner", PlannerAction);

export class PlannerController extends Component {
    static template = "project_planner.PlannerView";
    static components = { Layout, PlannerCore, SearchBar, CogMenu };
    static props = { ...standardViewProps };

    setup() {
        this.orm = useService("orm");
        this.searchBarToggler = useSearchBarToggler();
    }
    /** Cambia con la búsqueda: `t-key` recrea el núcleo con los datos nuevos. */
    get searchKey() {
        return JSON.stringify(this.props.domain);
    }
    get fetch() {
        const { domain, context } = this.props;
        return () => this.orm.call("project.task", "planner_data", [domain], { context });
    }
}

export const plannerView = {
    type: "planner",
    display_name: _t("Planner"),
    icon: "fa fa-align-left",
    multiRecord: true,
    searchMenuTypes: ["filter", "favorite"],
    Controller: PlannerController,
};
registry.category("views").add("planner", plannerView);
