/** @odoo-module **/
/**
 * Los filtros del planificador. Módulo PURO (sin Odoo ni luxon) para
 * poder probarlo fuera del navegador:
 * `node scripts/herramientas/prueba_filtros_planificador.mjs` (workspace).
 */
// Los filtros del planificador, vacíos.
export const EMPTY_FILTERS = { text: "", user: "", critical: false, late: false, milestones: false, from: "", to: "" };

/**
 * Qué tareas deja ver un filtro. Devuelve el conjunto de ids, o `null`
 * si no hay filtro activo. Como en MS Project, cada tarea que cumple se ve CON
 * sus resúmenes, para no perder el árbol; si el texto coincide con un resumen
 * (un paquete), se ve con todo su contenido.
 * `f.from`/`f.to`: fechas ISO (aaaa-mm-dd), la ventana que la tarea toca.
 */
export function filterTasks(tasks, f, now = Date.now()) {
    const activo = f.text || f.user || f.critical || f.late || f.milestones || f.from || f.to;
    if (!activo) {
        return null;
    }
    const texto = (f.text || "").trim().toLowerCase();
    // Fechas locales del navegador, día completo.
    const desde = f.from ? new Date(`${f.from}T00:00:00`).getTime() : null;
    const hasta = f.to ? new Date(`${f.to}T23:59:59.999`).getTime() : null;
    const cumple = (t) => {
        if (texto && !(t.name || "").toLowerCase().includes(texto) && !(t.code || "").startsWith(texto)) {
            return false;
        }
        if (f.user && !(t.users || "").split(", ").includes(f.user)) {
            return false;
        }
        if (f.critical && !(t.critical && !t.summary)) {
            return false;
        }
        // Atrasada: debía haber terminado y no tiene fin real.
        if (f.late && (t.summary || t.e === null || t.e >= now || t.actual_finish)) {
            return false;
        }
        if (f.milestones && !t.milestone) {
            return false;
        }
        if ((desde !== null || hasta !== null) && t.s === null) {
            return false;
        }
        if (desde !== null && t.e < desde) {
            return false;
        }
        if (hasta !== null && t.s > hasta) {
            return false;
        }
        return true;
    };
    const byId = new Map(tasks.map((t) => [t.id, t]));
    const hijos = new Map();
    for (const t of tasks) {
        if (t.parent_id && byId.has(t.parent_id)) {
            hijos.set(t.parent_id, [...(hijos.get(t.parent_id) || []), t]);
        }
    }
    const keep = new Set();
    const conTodo = (t) => {
        keep.add(t.id);
        for (const h of hijos.get(t.id) || []) {
            conTodo(h);
        }
    };
    for (const t of tasks) {
        if (!cumple(t)) {
            continue;
        }
        if (t.summary && texto) {
            conTodo(t);
        } else {
            keep.add(t.id);
        }
        let p = byId.get(t.parent_id);
        while (p && !keep.has(p.id)) {
            keep.add(p.id);
            p = byId.get(p.parent_id);
        }
    }
    // Un resumen agregado arriba puede haber dejado ancestros sin marcar.
    for (const id of [...keep]) {
        let p = byId.get(byId.get(id)?.parent_id);
        while (p && !keep.has(p.id)) {
            keep.add(p.id);
            p = byId.get(p.parent_id);
        }
    }
    return keep;
}
