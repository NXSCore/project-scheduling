/** @odoo-module **/
/**
 * Vista de planificación del cronograma, al estilo de MS Project.
 *
 * Diseño pensado para que el scroll NO dependa del número de tareas (el Gantt
 * de Odoo re-renderiza una rejilla CSS completa cada vez que cambia el rango
 * visible):
 *
 * - todas las filas miden lo mismo (`ROW_H`), así que la fila visible se
 *   calcula con una división;
 * - la tabla solo tiene en el DOM las filas visibles (unas 40);
 * - la línea de tiempo es UN `<canvas>` del tamaño de la ventana, que se
 *   redibuja en `requestAnimationFrame` con solo lo visible;
 * - el scroll lo da un `div` con un espaciador del tamaño total; el canvas se
 *   queda fijo encima (`position: sticky`).
 */
import { Component, onMounted, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { SIZES } from "@web/core/ui/ui_service";
import { _t } from "@web/core/l10n/translation";
import { formatDate, parseDate } from "@web/core/l10n/dates";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { EMPTY_FILTERS, filterTasks } from "./filters";

const { DateTime } = luxon;

// Cuántas acciones se pueden deshacer en la sesión.
const UNDO_LIMIT = 50;
export const ROW_H = 28;
const HEADER_H = 48;
const DAY_MS = 86400000;
export const ZOOMS = { day: 34, week: 13, month: 3.2, quarter: 1.1, semester: 0.55, year: 0.28 };
const TABLE_W_KEY = "schedule_planner_table_width";
// Las columnas que cada usuario eligió (en su navegador).
const COLUMNS_KEY = "project_planner_columns";
export const DEFAULT_COLUMNS = ["code", "name", "dur", "start", "end", "pred"];
// Ancho mínimo del nombre; con más columnas, la tabla se desplaza en horizontal.
const NAME_MIN_W = 220;
// Los anchos que cada usuario dio a mano a las columnas (en su navegador).
const COLUMN_WIDTHS_KEY = "project_planner_column_widths";
const COLUMN_MIN_W = 36;
//: Mostrar u ocultar la banda de holgura, por usuario.
const FLOAT_BAND_KEY = "project_planner_float_band";
//: Las líneas base comparadas, por proyecto.
const COMPARE_KEY = "project_planner_compare_";
//: Colores de las dos líneas base de comparación (la vigente usa COLORS.baseline).
export const COMPARE_COLORS = ["#0284c7", "#c026d3"];
const COLORS = {
    bar: "#2f6fde",
    barProgress: "#1d4ea8",
    critical: "#d93a3a",
    criticalProgress: "#a32424",
    milestone: "#7c3aed",
    baseline: "#9aa3ae",
    link: "#8a94a3",
    today: "#f08a24",
    weekend: "rgba(128,128,128,0.08)",
    holiday: "rgba(240,136,62,0.14)",
    deadline: "#16a34a",
    deadlineMissed: "#dc2626",
    select: "rgba(47,111,222,0.12)",
    linkOk: "#16a34a",
    linkZone: "rgba(22,163,74,0.22)",
    // La banda de holgura.
    float: "#059669",
};

/** Árbol plano: las filas visibles según lo plegado, en el orden del servidor. */
export { EMPTY_FILTERS, filterTasks } from "./filters";

export function visibleRows(tasks, collapsed) {
    const out = [];
    let hideBelow = null; // profundidad desde la que se oculta
    for (const t of tasks) {
        if (hideBelow !== null && t.depth > hideBelow) {
            continue;
        }
        hideBelow = null;
        out.push(t);
        if (t.summary && collapsed.has(t.id)) {
            hideBelow = t.depth;
        }
    }
    return out;
}

/** Puntos del codo de un vínculo (s/t: {x, y}; lados según el tipo). */
export function linkPath(type, s, t, rowH = ROW_H) {
    const fromEnd = type === "fs" || type === "ff";
    const toStart = type === "fs" || type === "ss";
    const a = { x: s.x + (fromEnd ? 6 : -6), y: s.y };
    const b = { x: t.x + (toStart ? -6 : 6), y: t.y };
    const directo = toStart ? b.x >= a.x : b.x <= a.x;
    if (directo) {
        return [s, a, { x: a.x, y: t.y }, t];
    }
    const my = t.y + (t.y > s.y ? -rowH / 2 : rowH / 2);
    return [s, a, { x: a.x, y: my }, { x: b.x, y: my }, b, t];
}

/**
 * El núcleo: tabla + línea de tiempo. Recibe `fetch`, una función que trae
 * los datos; así lo usan igual la acción cliente y la vista
 * `planner`, sin duplicar nada.
 */
const HANDLE_R = 4;
const HANDLE_GAP = 3;

export const CONSTRAINT_TYPES = [
    ["asap", _t("As Soon As Possible")],
    ["alap", _t("As Late As Possible")],
    ["snet", _t("Start No Earlier Than")],
    ["snlt", _t("Start No Later Than")],
    ["fnet", _t("Finish No Earlier Than")],
    ["fnlt", _t("Finish No Later Than")],
    ["mso", _t("Must Start On")],
    ["mfo", _t("Must Finish On")],
];

export const LINK_LABELS = {
    fs: _t("Finish to Start (FS)"),
    ss: _t("Start to Start (SS)"),
    ff: _t("Finish to Finish (FF)"),
    sf: _t("Start to Finish (SF)"),
};

export function distToSegment(px, py, a, b) {
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len = dx * dx + dy * dy;
    const t = len ? Math.max(0, Math.min(1, ((px - a.x) * dx + (py - a.y) * dy) / len)) : 0;
    return Math.hypot(px - (a.x + t * dx), py - (a.y + t * dy));
}

export class PlannerCore extends Component {
    static template = "project_planner.Planner";
    // `domain`: las tareas que se muestran. El planificador no lo usa; lo
    // ofrece para que un módulo que lo extiende (el informe PDF) trabaje
    // sobre las mismas tareas.
    static props = { fetch: Function, domain: { type: Array, optional: true } };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        // Celular y tableta: barra compacta y tabla acotada al ancho disponible.
        this.ui = useState(useService("ui"));
        this.bodyRef = useRef("body");
        this.scrollerRef = useRef("scroller");
        this.canvasRef = useRef("canvas");
        this.headerRef = useRef("header");
        this.rowsRef = useRef("rows");
        this.cellInputRef = useRef("cellInput");
        this.menuRef = useRef("menu");
        this.linkEditorRef = useRef("linkEditor");
        this.constraintEditorRef = useRef("constraintEditor");
        this.deadlineEditorRef = useRef("deadlineEditor");
        // Un menú abierto cerca del borde se acomoda para verse completo.
        useEffect(
            () => {
                for (const ref of [this.menuRef, this.linkEditorRef, this.constraintEditorRef, this.deadlineEditorRef]) {
                    const el = ref.el;
                    if (!el) {
                        continue;
                    }
                    const r = el.getBoundingClientRect();
                    const margen = 8;
                    if (r.bottom > window.innerHeight - margen) {
                        el.style.top = `${Math.max(margen, window.innerHeight - r.height - margen)}px`;
                    }
                    if (r.right > window.innerWidth - margen) {
                        el.style.left = `${Math.max(margen, window.innerWidth - r.width - margen)}px`;
                    }
                }
            },
            () => [this.state.menu, this.state.linkEdit, this.state.constraintEdit, this.state.deadlineEdit]
        );
        // La celda que se edita recibe el foco con su texto seleccionado.
        useEffect(
            (clave) => {
                if (clave && this.cellInputRef.el) {
                    this.cellInputRef.el.focus();
                    this.cellInputRef.el.select();
                }
            },
            () => [this.state.editing ? `${this.state.editing.id}:${this.state.editing.field}` : null]
        );
        this.collapsed = new Set();
        this.undoStack = [];
        this.redoStack = [];
        this.state = useState({
            loading: true, zoom: "week", dayW: ZOOMS.week, first: 0, count: 40, selected: null, version: 0, project: "", projectId: false,
            tableW: this.savedTableWidth(), level: 0,
            editable: false, editing: null, dragTip: null, saving: false, linkEdit: null,
            menu: null, pickLink: null, trace: null, moreScales: false,
            preview: null, constraintEdit: null, calendar: null, deadlineEdit: null, canUndo: false, canRedo: false,
            columns: this.savedColumns(), columnsMenu: false, colWidths: this.savedColumnWidths(),
            filters: { ...EMPTY_FILTERS }, filtersMenu: false,
            showFloat: this.savedFloatBand(), baselines: [], compare: [], baselinesMenu: false,
            bodyW: 0, toolsOpen: false,
        });
        this.drag = null;
        this.frame = null;
        onWillStart(() => this.load());
        onMounted(() => {
            this.resizeObserver = new ResizeObserver(() => this.resize());
            this.resizeObserver.observe(this.scrollerRef.el);
            // El ancho del cuerpo acota el de la tabla (ver `tableWidth`).
            if (this.bodyRef.el) {
                this.resizeObserver.observe(this.bodyRef.el);
            }
            this.resize();
            this.scrollToDate(this.firstStart ?? Date.now());
        });
        onWillUnmount(() => {
            this.resizeObserver?.disconnect();
            cancelAnimationFrame(this.frame);
        });
    }

    /** El calendario laboral del proyecto (solo lectura salvo para
     *  quien puede editar calendarios). */
    openCalendar() {
        const cal = this.state.calendar;
        if (cal?.id) {
            this.action.doAction({
                type: "ir.actions.act_window", res_model: "resource.calendar", res_id: cal.id,
                views: [[false, "form"]], target: "new", name: cal.name,
            });
        }
    }

    // ------------------------------------------------------------------ datos
    async load() {
        const data = await this.props.fetch();
        const byId = new Map();
        for (const t of data.tasks) {
            const start = t.start ? DateTime.fromISO(t.start) : null;
            const end = t.end ? DateTime.fromISO(t.end) : start;
            Object.assign(t, {
                startDt: start, endDt: end,
                s: start ? start.toMillis() : null, e: end ? end.toMillis() : null,
                bs: t.baseline_start ? DateTime.fromISO(t.baseline_start).toMillis() : null,
                dl: t.deadline ? DateTime.fromISO(t.deadline).toMillis() : null,
                be: t.baseline_end ? DateTime.fromISO(t.baseline_end).toMillis() : null,
                lf: t.late_finish ? DateTime.fromISO(t.late_finish).toMillis() : null,
                preds: [],
            });
            byId.set(t.id, t);
        }
        for (const t of data.tasks) {
            t.depth = t.parent_id && byId.has(t.parent_id) ? byId.get(t.parent_id).depth + 1 : 0;
        }
        // Resumen como en MS Project: inicio y fin salen de sus hijas. Se
        // recorre al revés (hijas antes que padres, por el orden EDT) para que
        // un resumen de resúmenes también se calcule.
        const rango = new Map();
        for (const t of [...data.tasks].reverse()) {
            const r = rango.get(t.id);
            if (t.summary && r) {
                t.s = r.s;
                t.e = r.e;
                t.startDt = DateTime.fromMillis(r.s);
                t.endDt = DateTime.fromMillis(r.e);
            }
            if (t.parent_id && t.s !== null) {
                const p = rango.get(t.parent_id) || { s: t.s, e: t.e };
                rango.set(t.parent_id, { s: Math.min(p.s, t.s), e: Math.max(p.e, t.e) });
            }
        }
        for (const l of data.links) {
            const to = byId.get(l.to);
            const from = byId.get(l.from);
            if (to && from) {
                to.preds.push(l);
            }
        }
        this.tasks = data.tasks;
        this.links = data.links;
        this.byId = byId;
        const conFecha = data.tasks.filter((t) => t.s !== null);
        this.firstStart = conFecha.length ? conFecha[0].s : null;
        const min = conFecha.length ? Math.min(...conFecha.map((t) => t.s)) : Date.now();
        const max = conFecha.length ? Math.max(...conFecha.map((t) => t.e)) : Date.now();
        this.t0 = DateTime.fromMillis(min).startOf("month").minus({ days: 7 }).toMillis();
        this.t1 = DateTime.fromMillis(max).endOf("month").plus({ days: 14 }).toMillis();
        this.state.project = data.project;
        // Con un solo proyecto, el botón «Salud» lo revisa.
        this.state.projectId = data.project_id || false;
        // El calendario del proyecto (el mismo con el que calcula el motor).
        this.state.calendar = data.calendar || null;
        // Las versiones que se pueden comparar y la elección guardada.
        this.state.baselines = data.baselines || [];
        this.state.compare = this.savedCompare();
        await this.loadCompare();
        this.offWeekdays = new Set((data.calendar?.off_weekdays ?? [5, 6]).map((d) => d + 1));
        this.holidays = new Set(data.calendar?.holidays || []);
        this.state.editable = Boolean(data.editable);
        this.refreshRows();
        this.state.loading = false;
    }

    refreshRows() {
        // Primero el filtro (con sus resúmenes), después lo plegado.
        this.filterKeep = filterTasks(this.tasks || [], this.state.filters);
        const base = this.filterKeep ? this.tasks.filter((t) => this.filterKeep.has(t.id)) : this.tasks;
        this.rows = visibleRows(base, this.collapsed);
        this.rowIndex = new Map(this.rows.map((t, i) => [t.id, i]));
        this.state.version++;
    }

    // ------------------------------------------------------------- geometría
    get dayW() {
        return this.state.dayW;
    }
    /** La escala del encabezado sale del ancho del día, no del botón. */
    get scale() {
        const w = this.state.dayW;
        return w >= 20 ? "day" : w >= 6 ? "week" : w >= 2 ? "month" : w >= 0.8 ? "quarter" : w >= 0.4 ? "semester" : "year";
    }
    get totalWidth() {
        return Math.ceil(((this.t1 - this.t0) / DAY_MS) * this.dayW);
    }
    get totalHeight() {
        return (this.rows?.length || 0) * ROW_H;
    }
    x(ms) {
        return ((ms - this.t0) / DAY_MS) * this.dayW;
    }

    get visibleSlice() {
        void this.state.version;
        const first = this.state.first;
        return (this.rows || []).slice(first, first + this.state.count).map((t, i) => ({ t, i: first + i }));
    }

    // -------------------------------------------------------------- columnas
    duration(t) {
        if (t.milestone || t.s === null) {
            return t.milestone ? _t("0 d") : "";
        }
        // La duración laborable guardada; si falta, días naturales.
        const dias = t.duration || Math.max(1, Math.round((t.e - t.s) / DAY_MS));
        return _t("%s d", Math.round(dias * 10) / 10);
    }
    fmt(dt) {
        return dt ? formatDate(dt) : "";
    }
    predecessors(t) {
        return t.preds
            .map((l) => {
                const p = this.byId.get(l.from);
                const tipo = l.type === "fs" ? "" : l.type.toUpperCase();
                const lag = l.lag ? `${l.lag > 0 ? "+" : ""}${l.lag}${l.elapsed ? "dn" : "d"}` : "";
                return `${p.code}${tipo || lag ? (tipo || "FS") : ""}${lag}`;
            })
            .join("; ");
    }

    // ---- columnas configurables
    /** Las columnas disponibles. «Nombre» siempre está. `edit` = la celda que
     *  se edita con doble clic (las mismas de antes). */
    get columnDefs() {
        return [
            { key: "code", label: _t("WBS"), width: 64 },
            { key: "name", label: _t("Task Name"), width: 0, fixed: true },
            { key: "dur", label: _t("Duration"), width: 56, edit: "dur", align: "end" },
            { key: "start", label: _t("Start"), width: 88, edit: "start" },
            { key: "end", label: _t("Finish"), width: 88, edit: "end" },
            { key: "pred", label: _t("Predecessors"), width: 92, edit: "pred", muted: true },
            { key: "succ", label: _t("Successors"), width: 92, muted: true },
            { key: "users", label: _t("Assignees"), width: 120 },
            { key: "progress", label: _t("Progress"), width: 64, align: "end" },
            { key: "float", label: _t("Total Float"), width: 72, align: "end" },
            { key: "free_float", label: _t("Free Float"), width: 72, align: "end" },
            { key: "critical", label: _t("Critical"), width: 56, align: "center" },
            { key: "constraint", label: _t("Constraint"), width: 150 },
            { key: "deadline", label: _t("Deadline"), width: 88 },
            { key: "actual_start", label: _t("Actual Start"), width: 88 },
            { key: "actual_end", label: _t("Actual Finish"), width: 88 },
            { key: "baseline_start", label: _t("Baseline Start"), width: 88 },
            { key: "baseline_end", label: _t("Baseline Finish"), width: 88 },
        ];
    }
    get visibleColumns() {
        const defs = new Map(this.columnDefs.map((c) => [c.key, c]));
        const anchos = this.state.colWidths || {};
        // El ancho que el usuario le dio a mano manda sobre el de fábrica.
        return this.state.columns.map((k) => defs.get(k)).filter(Boolean)
            .map((c) => (anchos[c.key] ? { ...c, width: anchos[c.key], custom: true } : c));
    }
    /** El `style` de una celda: ancho fijo; el nombre, flexible salvo que el
     *  usuario lo haya fijado. */
    colStyle(col) {
        if (col.key === "name" && !col.custom) {
            return "";
        }
        return `flex:0 0 ${col.width}px;width:${col.width}px;min-width:${col.width}px`;
    }
    savedColumnWidths() {
        try {
            const w = JSON.parse(window.localStorage.getItem(COLUMN_WIDTHS_KEY) || "{}");
            return w && typeof w === "object" ? w : {};
        } catch {
            return {};
        }
    }
    saveColumnWidths() {
        try {
            window.localStorage.setItem(COLUMN_WIDTHS_KEY, JSON.stringify(this.state.colWidths));
        } catch {
            // sin almacenamiento: vale para esta sesión
        }
    }
    onColResizeDown(ev, col) {
        ev.preventDefault();
        ev.stopPropagation();
        const x0 = ev.clientX;
        const w0 = ev.target.parentElement.getBoundingClientRect().width;
        const move = (e) => {
            this.state.colWidths = { ...this.state.colWidths, [col.key]: Math.round(Math.max(COLUMN_MIN_W, w0 + e.clientX - x0)) };
        };
        const up = () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", up);
            this.saveColumnWidths();
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    }
    resetColumnWidth(key) {
        const w = { ...this.state.colWidths };
        delete w[key];
        this.state.colWidths = w;
        this.saveColumnWidths();
    }
    savedColumns() {
        try {
            const guardadas = JSON.parse(window.localStorage.getItem(COLUMNS_KEY) || "null");
            if (Array.isArray(guardadas) && guardadas.includes("name")) {
                return guardadas;
            }
        } catch {
            // sin almacenamiento o valor dañado: las de siempre
        }
        return [...DEFAULT_COLUMNS];
    }
    setColumns(cols) {
        this.state.columns = cols;
        try {
            window.localStorage.setItem(COLUMNS_KEY, JSON.stringify(cols));
        } catch {
            // sin almacenamiento: vale para esta sesión
        }
    }
    toggleColumn(key) {
        const cols = [...this.state.columns];
        const i = cols.indexOf(key);
        if (i >= 0) {
            cols.splice(i, 1);
        } else {
            // El panel NO crece: si las columnas no caben, la tabla tiene
            // su propia barra horizontal y el Gantt conserva su espacio.
            cols.push(key);
        }
        this.setColumns(cols);
    }
    moveColumn(key, delta) {
        const cols = [...this.state.columns];
        const i = cols.indexOf(key);
        const j = i + delta;
        if (i < 0 || j < 0 || j >= cols.length) {
            return;
        }
        [cols[i], cols[j]] = [cols[j], cols[i]];
        this.setColumns(cols);
    }
    resetColumns() {
        this.setColumns([...DEFAULT_COLUMNS]);
        this.state.colWidths = {};
        this.saveColumnWidths();
    }
    successors(t) {
        return (this.links || [])
            .filter((l) => l.from === t.id && this.byId.has(l.to))
            .map((l) => {
                const s = this.byId.get(l.to);
                const tipo = l.type === "fs" ? "" : l.type.toUpperCase();
                const lag = l.lag ? `${l.lag > 0 ? "+" : ""}${l.lag}${l.elapsed ? "dn" : "d"}` : "";
                return `${s.code}${tipo || lag ? (tipo || "FS") : ""}${lag}`;
            })
            .join("; ");
    }
    cellText(t, key) {
        const iso = (v) => (v ? formatDate(DateTime.fromISO(v)) : "");
        const ms = (v) => (v !== null && v !== undefined ? formatDate(DateTime.fromMillis(v)) : "");
        switch (key) {
            case "dur": return this.duration(t);
            case "start": return this.fmt(t.startDt);
            case "end": return this.fmt(t.endDt);
            case "pred": return this.predecessors(t);
            case "succ": return this.successors(t);
            case "users": return t.users || "";
            case "progress": return t.progress ? `${Math.round(t.progress)} %` : "";
            case "float": return t.s === null || t.float === undefined ? "" : _t("%s d", Math.round(t.float * 10) / 10);
            case "free_float":
                return t.s === null || t.summary || t.free_float === undefined ? "" : _t("%s d", Math.round(t.free_float * 10) / 10);
            case "critical": return t.critical ? "✔" : "";
            case "constraint":
                return t.constraint && t.constraint !== "asap"
                    ? `${t.constraint_label}${t.constraint_date ? " " + iso(t.constraint_date) : ""}` : "";
            case "deadline": return ms(t.dl);
            case "actual_start": return iso(t.actual_start);
            case "actual_end": return iso(t.actual_finish);
            case "baseline_start": return ms(t.bs);
            case "baseline_end": return ms(t.be);
        }
        return "";
    }
    onCellDblClick(t, col) {
        if (col.edit) {
            this.startEdit(t, col.edit);
        } else if (this.state.editable && !t.summary && col.key === "constraint") {
            this.openConstraintEditor(t);
        } else if (this.state.editable && col.key === "deadline") {
            this.openDeadlineEditor(t);
        }
    }

    // ------------------------------------------------------------ eventos UI
    onScroll() {
        const el = this.scrollerRef.el;
        const first = Math.floor(el.scrollTop / ROW_H);
        if (first !== this.state.first) {
            this.state.first = first;
        }
        if (this.rowsRef.el) {
            this.rowsRef.el.style.transform = `translateY(${-(el.scrollTop - first * ROW_H)}px)`;
        }
        this.schedule();
    }
    onTableWheel(ev) {
        // El desplazamiento HORIZONTAL (Mayús + rueda, o el touchpad) es
        // de la tabla, que ahora tiene su barra; el vertical mueve las filas.
        if (ev.shiftKey || Math.abs(ev.deltaX) > Math.abs(ev.deltaY)) {
            return;
        }
        this.scrollerRef.el.scrollTop += ev.deltaY;
        ev.preventDefault();
    }
    /** Lo que miden las columnas; con «Nombre» en su mínimo. */
    get tableContentWidth() {
        return this.visibleColumns.reduce((suma, c) => suma + (c.key === "name" && !c.custom ? NAME_MIN_W : c.width), 0);
    }
    toggle(t, ev) {
        ev?.stopPropagation();
        if (!t.summary) {
            return;
        }
        this.collapsed.has(t.id) ? this.collapsed.delete(t.id) : this.collapsed.add(t.id);
        this.refreshRows();
        this.schedule();
    }
    expandAll() {
        this.collapsed.clear();
        this.refreshRows();
        this.schedule();
    }
    collapseAll() {
        for (const t of this.tasks) {
            if (t.summary) {
                this.collapsed.add(t.id);
            }
        }
        this.refreshRows();
        this.schedule();
    }
    /** Seleccionar una fila lleva la línea de tiempo a su barra si no se
     * ve, como «Desplazarse a la tarea» de MS Project. */
    select(t) {
        if (this.state.pickLink) {
            this.pickLinkTarget(t);
            return;
        }
        this.state.selected = t.id;
        const el = this.scrollerRef.el;
        if (t.s !== null && el) {
            const x0 = this.x(t.s);
            const x1 = this.x(t.e);
            if (x1 < el.scrollLeft || x0 > el.scrollLeft + el.clientWidth) {
                this.scrollToDate(t.s);
            }
        }
        this.schedule();
    }
    openTask(t) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "project.task", res_id: t.id,
            views: [[false, "form"]], target: "current",
        });
    }
    // ================================================================ edición
    /** Recarga sin perder plegado, selección ni la fecha que se ve. */
    async reload() {
        const el = this.scrollerRef.el;
        const fechaIzq = el ? this.t0 + (el.scrollLeft / this.dayW) * DAY_MS : null;
        await this.load();
        if (el && fechaIzq !== null) {
            requestAnimationFrame(() => {
                el.scrollLeft = Math.max(0, this.x(fechaIzq));
                this.schedule();
            });
        }
    }
    /** Guarda con los permisos del usuario; si una regla lo impide, avisa y
     * recarga para que la vista vuelva a mostrar lo que de verdad hay. */
    async save(fn, { undoable = true } = {}) {
        this.state.saving = true;
        // Foto antes y después; se guarda solo lo que la acción cambió.
        const antes = undoable ? this.photo() : null;
        let ok = true;
        try {
            await fn();
        } catch (e) {
            ok = false;
            const msg = e?.data?.message || e?.message || String(e);
            this.notification.add(msg, { type: "danger", title: _t("Not saved") });
        } finally {
            await this.reload();
            if (antes && ok) {
                const cambio = this.diffPhotos(antes, this.photo());
                if (cambio.size) {
                    this.undoStack.push(cambio);
                    if (this.undoStack.length > UNDO_LIMIT) {
                        this.undoStack.shift();
                    }
                    this.redoStack = [];
                }
            }
            this.syncUndoState();
            this.state.saving = false;
        }
    }

    // ================================================== deshacer / rehacer
    /** Lo que el planificador sabe de cada tarea y vínculo, para comparar. */
    photo() {
        const tasks = new Map();
        for (const t of this.tasks || []) {
            tasks.set(t.id, {
                name: t.name, parent_id: t.parent_id || false, sequence: t.sequence,
                start: t.start || false, end: t.end || false, duration: t.duration,
                milestone: Boolean(t.milestone), manual: Boolean(t.manual), constraint: t.constraint || "asap",
                constraint_date: t.constraint_date || false, deadline: t.deadline || false,
            });
        }
        const links = new Map();
        for (const l of this.links || []) {
            links.set(`${l.from}-${l.to}`, { type: l.type, lag: l.lag, elapsed: Boolean(l.elapsed) });
        }
        return { tasks, links };
    }
    diffPhotos(a, b) {
        const out = { tasks: {}, links: {}, size: 0, creates: false };
        for (const [mapa, destino] of [["tasks", out.tasks], ["links", out.links]]) {
            const claves = new Set([...a[mapa].keys(), ...b[mapa].keys()]);
            for (const k of claves) {
                const x = a[mapa].get(k) ?? null;
                const y = b[mapa].get(k) ?? null;
                if (JSON.stringify(x) !== JSON.stringify(y)) {
                    destino[k] = { before: x, after: y };
                    out.size++;
                    if (mapa === "tasks" && x === null) {
                        out.creates = true;
                    }
                }
            }
        }
        return out;
    }
    syncUndoState() {
        this.state.canUndo = this.undoStack.length > 0;
        this.state.canRedo = this.redoStack.length > 0;
    }
    async undo() {
        if (!this.undoStack.length || this.state.saving) {
            return;
        }
        const e = this.undoStack.pop();
        await this.restore(e, "undo");
        // Una tarea creada y luego quitada no puede volver con el mismo id:
        // esa acción no se rehace.
        if (!e.creates) {
            this.redoStack.push(e);
        }
        this.syncUndoState();
    }
    async redo() {
        if (!this.redoStack.length || this.state.saving) {
            return;
        }
        const e = this.redoStack.pop();
        await this.restore(e, "redo");
        this.undoStack.push(e);
        this.syncUndoState();
    }
    async restore(e, direction) {
        this.state.saving = true;
        try {
            const res = await this.orm.call("project.task", "planner_restore", [{ tasks: e.tasks, links: e.links }], { direction });
            if (res.conflicts) {
                this.notification.add(
                    _t("%s change(s) were left as they are: someone changed them afterwards.", res.conflicts), { type: "warning" });
            }
            if (res.missing) {
                this.notification.add(_t("%s task(s) no longer exist and could not be restored.", res.missing), { type: "warning" });
            }
        } catch (err) {
            const msg = err?.data?.message || err?.message || String(err);
            this.notification.add(msg, { type: "danger", title: direction === "undo" ? _t("Not undone") : _t("Not redone") });
        } finally {
            await this.reload();
            this.state.saving = false;
        }
    }
    utc(ms) {
        return DateTime.fromMillis(ms, { zone: "utc" }).toFormat("yyyy-MM-dd HH:mm:ss");
    }
    canEditDates(t) {
        return this.state.editable && !t.summary && t.s !== null;
    }

    // ---- celdas
    isEditing(t, field) {
        const ed = this.state.editing;
        return Boolean(ed && ed.id === t.id && ed.field === field);
    }
    startEdit(t, field) {
        if (!this.state.editable || (field !== "name" && field !== "pred" && !this.canEditDates(t))) {
            return;
        }
        if (t.milestone && (field === "end" || field === "dur")) {
            // Un hito dura cero días: se mueve con su inicio.
            return;
        }
        const valor = {
            name: t.name,
            start: this.fmt(t.startDt),
            end: this.fmt(t.endDt),
            dur: t.milestone ? "0" : String(t.duration || Math.max(1, Math.round((t.e - t.s) / DAY_MS))),
            pred: this.predecessors(t),
        }[field];
        this.state.editing = { id: t.id, field, value: valor };
    }
    onEditKey(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.commitEdit();
        } else if (ev.key === "Escape") {
            this.state.editing = null;
        }
        ev.stopPropagation();
    }
    async commitEdit() {
        const ed = this.state.editing;
        if (!ed) {
            return;
        }
        this.state.editing = null;
        const t = this.byId.get(ed.id);
        const valor = (ed.value || "").trim();
        if (ed.field === "name") {
            if (valor && valor !== t.name) {
                await this.save(() => this.orm.write("project.task", [t.id], { name: valor }));
            }
        } else if (ed.field === "pred") {
            if (valor !== this.predecessors(t)) {
                await this.save(() => this.orm.call("project.task", "planner_set_predecessors", [t.id, valor]));
            }
        } else if (ed.field === "dur") {
            const dias = Number(valor.replace(",", "."));
            if (Number.isFinite(dias) && dias >= 1) {
                // El servidor mueve el fin con el calendario laboral del proyecto.
                await this.save(() => this.orm.call("project.task", "planner_set_duration", [t.id, dias]));
            }
        } else {
            const fecha = parseDate(valor);
            if (!fecha?.isValid) {
                this.notification.add(_t("Not a valid date: %s", valor), { type: "warning" });
                return;
            }
            // Conserva la hora del día de la tarea: solo cambia el día.
            const base = ed.field === "start" ? t.startDt : t.endDt;
            const nueva = fecha.set({ hour: base.hour, minute: base.minute, second: base.second }).toMillis();
            if (ed.field === "start") {
                // Como en MS Project: cambiar el inicio MUEVE la tarea; la duración se queda.
                await this.writeDates(t, nueva, nueva + (t.e - t.s));
            } else {
                await this.writeDates(t, t.s, Math.max(nueva, t.s));
            }
        }
    }
    /** Texto de predecesoras de `t` con el vínculo desde `fromId` cambiado
     * (`link`) o quitado (`null`). Lo interpreta el servidor. */
    predsWith(t, fromId, link) {
        const tokens = t.preds
            .filter((l) => l.from !== fromId)
            .map((l) => this.token(this.byId.get(l.from).code, l));
        if (link) {
            tokens.push(this.token(this.byId.get(fromId).code, link));
        }
        return tokens.join("; ");
    }
    token(code, l) {
        const lag = l.lag ? `${l.lag > 0 ? "+" : ""}${l.lag}${l.elapsed ? "dn" : "d"}` : "";
        return `${code}${l.type.toUpperCase()}${lag}`;
    }
    setLink(t, fromId, link) {
        return this.save(() =>
            this.orm.call("project.task", "planner_set_predecessors", [t.id, this.predsWith(t, fromId, link)])
        );
    }
    // ---- clic en una flecha: editor de tipo, desfase y borrado
    hitLink(ev) {
        const rect = this.canvasRef.el.getBoundingClientRect();
        const px = ev.clientX - rect.left;
        const py = ev.clientY - rect.top;
        for (const h of this.linkHits || []) {
            for (let k = 1; k < h.pts.length; k++) {
                if (distToSegment(px, py, h.pts[k - 1], h.pts[k]) <= 4) {
                    return h.l;
                }
            }
        }
        return null;
    }
    openLinkEditor(l, ev) {
        this.state.linkEdit = {
            from: l.from, to: l.to, type: l.type, lag: String(l.lag || 0), elapsed: Boolean(l.elapsed),
            x: ev.clientX, y: ev.clientY,
            label: `${this.byId.get(l.from).code} → ${this.byId.get(l.to).code}`,
            milestone: Boolean(this.byId.get(l.from)?.milestone || this.byId.get(l.to)?.milestone),
            allowed: this.allowedLinkTypes(this.byId.get(l.from), this.byId.get(l.to)),
        };
    }
    /** Un hito es un solo instante: su lado del vínculo no elige
     * entre inicio y fin. Hito destino → FS o SS; hito origen → FS o FF;
     * entre dos hitos, solo FS. */
    allowedLinkTypes(from, to) {
        const desde = from?.milestone ? ["f"] : ["f", "s"];
        const hacia = to?.milestone ? ["s"] : ["s", "f"];
        return Object.keys(LINK_LABELS).filter((k) => desde.includes(k[0]) && hacia.includes(k[1]));
    }
    async saveLinkEdit(remove = false) {
        const le = this.state.linkEdit;
        this.state.linkEdit = null;
        const t = this.byId.get(le.to);
        const lag = Number(String(le.lag).replace(",", ".")) || 0;
        await this.setLink(t, le.from, remove ? null : { type: le.type, lag, elapsed: le.elapsed });
    }

    // ================================================================ estructura
    /** Operación de estructura en el servidor; si crea una tarea, la deja
     * seleccionada y con el nombre listo para escribir, como MS Project. */
    async structure(op, t = this.byId?.get(this.state.selected)) {
        this.state.menu = null;
        if (!t || !this.state.editable) {
            return;
        }
        if (op === "delete") {
            return this.confirmDelete(t);
        }
        let nuevo = null;
        await this.save(async () => {
            nuevo = await this.orm.call("project.task", "planner_structure", [op, t.id]);
        });
        const crea = ["insert", "insert_below", "add_child", "add_milestone"].includes(op);
        const id = crea ? nuevo : t.id;
        const fila = id && this.byId.get(id);
        if (fila) {
            if (fila.parent_id && this.collapsed.has(fila.parent_id)) {
                this.collapsed.delete(fila.parent_id);
                this.refreshRows();
            }
            this.state.selected = id;
            this.ensureRowVisible(this.rowIndex.get(id));
            if (crea) {
                this.startEdit(fila, "name");
            }
            this.schedule();
        }
    }
    confirmDelete(t) {
        const hijas = this.descendants(t).length;
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete task"),
            body: hijas
                ? _t("Delete “%(name)s” and its %(count)s subtask(s)?", { name: t.name, count: hijas })
                : _t("Delete “%(name)s”?", { name: t.name }),
            confirmLabel: _t("Delete"),
            // Borrar no se deshace (la tarea volvería con otro id, sin su historial).
            confirm: () => this.save(() => this.orm.call("project.task", "planner_structure", ["delete", t.id]), { undoable: false }),
            cancel: () => {},
        });
    }
    descendants(t) {
        const out = [];
        const i = this.tasks.indexOf(t);
        for (let k = i + 1; k < this.tasks.length && this.tasks[k].depth > t.depth; k++) {
            out.push(this.tasks[k]);
        }
        return out;
    }

    // ---- menú contextual (clic derecho)
    openMenu(t, ev) {
        ev.preventDefault();
        this.select(t);
        this.state.menu = { id: t.id, x: ev.clientX, y: ev.clientY, milestone: t.milestone, manual: t.manual };
    }
    onCanvasContextMenu(ev) {
        const t = this.rowAt(ev);
        if (t) {
            this.openMenu(t, ev);
        }
    }
    menuAction(action) {
        const t = this.byId.get(this.state.menu?.id);
        this.state.menu = null;
        if (!t) {
            return;
        }
        if (action === "open") {
            this.openTask(t);
        } else if (action === "link") {
            this.state.pickLink = t.id;
        } else if (action === "trace") {
            this.traceRoute(t);
        } else if (action === "constraint") {
            this.openConstraintEditor(t);
        } else if (action === "deadline") {
            this.openDeadlineEditor(t);
        } else if (action === "manual") {
            // Programación manual ⇄ automática, como MS Project.
            this.save(() => this.orm.write("project.task", [t.id], { manually_scheduled: !t.manual }));
        } else {
            this.structure(action, t);
        }
    }
    // ================================================================ motor
    /** «Calcular», como en MS Project: el servidor calcula las fechas con el
     * calendario laboral, los vínculos y las restricciones, y primero se
     * MUESTRA qué cambiaría; solo «Aplicar» escribe. */
    async calculate() {
        const dominio = [["id", "in", this.tasks.map((t) => t.id)]];
        const res = await this.orm.call("project.task", "scheduler_run", [dominio], { apply: false });
        if (!res.changes.length && !res.conflicts.length) {
            this.notification.add(_t("The schedule is already calculated: nothing moves."), { type: "success" });
            return;
        }
        this.state.preview = res;
    }
    // ---- banda de holgura
    savedFloatBand() {
        try {
            return window.localStorage.getItem(FLOAT_BAND_KEY) !== "0";
        } catch {
            return true;
        }
    }
    toggleFloatBand() {
        this.state.showFloat = !this.state.showFloat;
        try {
            window.localStorage.setItem(FLOAT_BAND_KEY, this.state.showFloat ? "1" : "0");
        } catch {
            // sin almacenamiento del navegador, la elección dura la sesión
        }
        this.schedule();
    }
    // ---- comparar líneas base
    get comparable() {
        return this.state.baselines.filter((b) => !b.current);
    }
    get currentBaseline() {
        return this.state.baselines.find((b) => b.current) || null;
    }
    savedCompare() {
        const validas = new Set(this.comparable.map((b) => b.id));
        try {
            const guardadas = JSON.parse(window.localStorage.getItem(COMPARE_KEY + this.state.projectId) || "[]");
            return guardadas.filter((id) => validas.has(id)).slice(0, COMPARE_COLORS.length);
        } catch {
            return [];
        }
    }
    get baselineColor() {
        return COLORS.baseline;
    }
    baselineName(id) {
        return this.state.baselines.find((b) => b.id === id)?.name || "";
    }
    compareColor(id) {
        return COMPARE_COLORS[this.state.compare.indexOf(id)];
    }
    async toggleCompare(id) {
        const actual = this.state.compare;
        if (actual.includes(id)) {
            this.state.compare = actual.filter((x) => x !== id);
        } else if (actual.length < COMPARE_COLORS.length) {
            this.state.compare = [...actual, id];
        } else {
            return;
        }
        try {
            window.localStorage.setItem(COMPARE_KEY + this.state.projectId, JSON.stringify(this.state.compare));
        } catch {
            // sin almacenamiento del navegador, la elección dura la sesión
        }
        await this.loadCompare();
        this.schedule();
    }
    /** Las fechas congeladas de las versiones elegidas: Map(línea base → Map(tarea → {s, e})). */
    async loadCompare() {
        this.compareDates = new Map();
        if (!this.state.compare.length) {
            return;
        }
        const dominio = [["id", "in", this.tasks.map((t) => t.id)]];
        const res = await this.orm.call("project.task", "planner_baseline_dates", [dominio, this.state.compare]);
        for (const [bid, fechas] of Object.entries(res)) {
            const porTarea = new Map();
            for (const [tid, [s, e]] of Object.entries(fechas)) {
                porTarea.set(Number(tid), { s: DateTime.fromISO(s).toMillis(), e: DateTime.fromISO(e).toMillis() });
            }
            this.compareDates.set(Number(bid), porTarea);
        }
    }
    /** El pronóstico a corto plazo y las críticas y casi críticas. */
    openLookahead() {
        return this.action.doAction("project_dependency.project_schedule_report_action", {
            additionalContext: { active_model: "project.project", active_id: this.state.projectId },
        });
    }
    /** La salud del cronograma (DCMA 14 puntos) del proyecto abierto. */
    openHealth() {
        return this.action.doAction("project_dependency.project_schedule_health_action", {
            additionalContext: { active_model: "project.project", active_id: this.state.projectId },
        });
    }
    async applyPreview() {
        this.state.preview = null;
        const dominio = [["id", "in", this.tasks.map((t) => t.id)]];
        await this.save(() => this.orm.call("project.task", "scheduler_run", [dominio], { apply: true }));
    }
    fmtIso(iso) {
        return iso ? formatDate(DateTime.fromISO(iso)) : "";
    }
    // ---- restricciones de fecha
    openConstraintEditor(t) {
        this.state.constraintEdit = {
            id: t.id, label: `${t.code} ${t.name}`, type: t.constraint || "asap",
            date: t.constraint_date ? formatDate(DateTime.fromISO(t.constraint_date)) : "",
        };
    }
    get constraintTypes() {
        return CONSTRAINT_TYPES;
    }
    needsConstraintDate(type) {
        return !["asap", "alap"].includes(type);
    }
    async saveConstraint() {
        const ce = this.state.constraintEdit;
        const vals = { constraint_type: ce.type, constraint_date: false };
        if (this.needsConstraintDate(ce.type)) {
            const fecha = parseDate(ce.date || "");
            if (!fecha?.isValid) {
                this.notification.add(_t("This constraint needs a date."), { type: "warning" });
                return;
            }
            // Mediodía local: el motor solo mira el DÍA, y así ningún huso horario lo corre.
            vals.constraint_date = this.utc(fecha.set({ hour: 12, minute: 0, second: 0 }).toMillis());
        }
        this.state.constraintEdit = null;
        await this.save(() => this.orm.write("project.task", [ce.id], vals));
    }

    // ---- fecha límite
    openDeadlineEditor(t) {
        this.state.deadlineEdit = {
            id: t.id, label: `${t.code} ${t.name}`,
            date: t.dl !== null ? formatDate(DateTime.fromMillis(t.dl)) : "",
        };
    }
    async saveDeadline(clear = false) {
        const de = this.state.deadlineEdit;
        let valor = false;
        if (!clear) {
            const fecha = parseDate(de.date || "");
            if (!fecha?.isValid) {
                this.notification.add(_t("Enter a date, or remove the deadline."), { type: "warning" });
                return;
            }
            // Fin del día local: «terminar a más tardar ese día», como MS Project.
            valor = this.utc(fecha.set({ hour: 23, minute: 59, second: 0 }).toMillis());
        }
        this.state.deadlineEdit = null;
        await this.save(() => this.orm.write("project.task", [de.id], { finish_deadline: valor }));
    }
    /** La tarea cuya marca de fecha límite está bajo el puntero (±5 px). */
    hitDeadline(ev) {
        const t = this.rowAt(ev);
        if (!t || t.dl === null) {
            return null;
        }
        const rect = this.canvasRef.el.getBoundingClientRect();
        const px = ev.clientX - rect.left + this.scrollerRef.el.scrollLeft;
        return Math.abs(px - this.x(t.dl)) <= 5 ? t : null;
    }
    deadlineTip(t) {
        let texto = _t("Deadline: %s", formatDate(DateTime.fromMillis(t.dl)));
        if (t.e !== null && t.e > t.dl) {
            texto += " · " + _t("finishes after it");
        }
        return texto;
    }

    /** «Añadir relación»: el siguiente clic en una tarea crea fin-inicio. */
    async pickLinkTarget(t) {
        const origen = this.state.pickLink;
        this.state.pickLink = null;
        if (t && t.id !== origen && !t.summary) {
            await this.setLink(t, origen, { type: "fs", lag: 0, elapsed: false });
        }
    }
    /** «Trazar ruta»: toda la cadena de predecesoras y sucesoras de la tarea. */
    traceRoute(t) {
        if (this.state.trace?.root === t.id) {
            this.state.trace = null;
            this.schedule();
            return;
        }
        const ids = new Set([t.id]);
        const recorrer = (inicio, campoDe, campoA) => {
            const pila = [inicio];
            while (pila.length) {
                const actual = pila.pop();
                for (const l of this.links) {
                    if (l[campoDe] === actual && !ids.has(l[campoA])) {
                        ids.add(l[campoA]);
                        pila.push(l[campoA]);
                    }
                }
            }
        };
        recorrer(t.id, "to", "from"); // hacia atrás: predecesoras
        recorrer(t.id, "from", "to"); // hacia adelante: sucesoras
        this.state.trace = { root: t.id, ids, driving: null };
        this.schedule();
        this.loadDrivingLinks(t.id);
    }
    /** Qué vínculos de la ruta MANDAN (fijan el inicio de su sucesora
     * en el cálculo). Se
     * piden al motor al trazar; mientras llegan, la ruta se ve como antes. */
    async loadDrivingLinks(root) {
        const dominio = [["id", "in", this.tasks.map((t) => t.id)]];
        const pares = await this.orm.call("project.task", "scheduler_driving_links", [dominio]);
        if (this.state.trace?.root === root) {
            this.state.trace.driving = new Set(pares.map(([a, b]) => `${a}-${b}`));
            this.schedule();
        }
    }
    inTrace(t) {
        return !this.state.trace || this.state.trace.ids.has(t.id);
    }

    writeDates(t, s, e) {
        if (s === t.s && e === t.e) {
            return;
        }
        return this.save(() =>
            this.orm.write("project.task", [t.id], { planned_date_begin: this.utc(s), date_deadline: this.utc(e) })
        );
    }

    // ---- arrastre en la línea de tiempo
    /** Qué hay bajo el puntero: la tarea y la zona (mover, estirar el fin). */
    hitBar(ev) {
        const t = this.rowAt(ev);
        if (!t || t.s === null) {
            return null;
        }
        const rect = this.canvasRef.el.getBoundingClientRect();
        const px = ev.clientX - rect.left + this.scrollerRef.el.scrollLeft;
        const x0 = this.x(t.s);
        const x1 = Math.max(this.x(t.e), x0 + 2);
        // Asas de vínculo, un círculo a cada lado de la barra. Un hito
        // tiene UN solo punto: inicio y fin son el mismo instante.
        if (!t.summary && !t.milestone && px >= x0 - HANDLE_GAP - HANDLE_R * 2 && px < x0 - 1) {
            return { t, zone: "link-start", px };
        }
        const xr = t.milestone ? x0 + 7 : x1;
        if (!t.summary && px > xr + 1 && px <= xr + HANDLE_GAP + HANDLE_R * 2) {
            return { t, zone: "link-finish", px };
        }
        if (t.milestone) {
            return Math.abs(px - x0) <= 8 ? { t, zone: "move", px } : null;
        }
        if (px < x0 || px > x1) {
            return null;
        }
        return { t, zone: !t.summary && px >= x1 - 6 ? "end" : "move", px };
    }
    onCanvasPointerMove(ev) {
        if (this.drag) {
            this.onDragMove(ev);
            return;
        }
        // El valor de la fecha límite, al pasar sobre su marca (también
        // para quien solo consulta).
        const marca = this.hitDeadline(ev);
        if (marca) {
            this.deadlineTipShown = true;
            this.state.dragTip = this.deadlineTip(marca);
            this.state.dragTipPos = { x: ev.clientX, y: ev.clientY };
        } else if (this.deadlineTipShown) {
            this.deadlineTipShown = false;
            this.state.dragTip = null;
        }
        if (!this.state.editable) {
            return;
        }
        const hit = this.hitBar(ev);
        const antes = this.hover;
        this.hover = hit ? hit.t.id : null;
        if (antes !== this.hover) {
            this.schedule();
        }
        this.canvasRef.el.style.cursor = hit
            ? hit.t.summary ? "" : hit.zone === "end" ? "ew-resize" : hit.zone.startsWith("link") ? "crosshair" : "grab"
            : this.hitLink(ev) ? "pointer" : "";
    }
    onCanvasPointerDown(ev) {
        if (ev.button !== 0) {
            return;
        }
        if (this.state.pickLink) {
            const t = this.rowAt(ev);
            if (t) {
                this.pickLinkTarget(t);
            }
            return;
        }
        this.state.menu = null;
        const hit = this.hitBar(ev);
        if (!hit) {
            const link = this.state.editable && this.hitLink(ev);
            if (link) {
                this.openLinkEditor(link, ev);
            }
            return;
        }
        this.select(hit.t);
        if (!this.state.editable || hit.t.summary) {
            return;
        }
        this.canvasRef.el.setPointerCapture(ev.pointerId);
        this.drag = {
            t: hit.t, zone: hit.zone, x0: ev.clientX, y0: ev.clientY,
            s: hit.t.s, e: hit.t.e, mode: hit.zone.startsWith("link") ? "link" : null, target: null,
            // De qué lado sale el vínculo: el asa lo dice; si se cambia a
            // vínculo a medio arrastre, sale del fin (lo más común, FS).
            fromFinish: hit.zone !== "link-start" || hit.t.milestone,
        };
    }
    onDragMove(ev) {
        const d = this.drag;
        if (d.cancelled) {
            return;
        }
        const dx = ev.clientX - d.x0;
        const dy = ev.clientY - d.y0;
        if (!d.mode) {
            if (Math.abs(dx) < 4 && Math.abs(dy) < 4) {
                return;
            }
            d.mode = d.zone;
        }
        // Salirse más de una fila hacia arriba o abajo mientras se mueve
        // convierte el gesto en vínculo y devuelve la barra a su lugar.
        if ((d.mode === "move" || d.mode === "end") && Math.abs(dy) > ROW_H) {
            d.t.s = d.s;
            d.t.e = d.e;
            d.mode = "link";
        }
        if (d.mode === "link") {
            d.pointer = { x: ev.clientX, y: ev.clientY };
            const destino = this.rowAt(ev);
            d.target = destino && destino.id !== d.t.id && !destino.summary && destino.s !== null ? destino : null;
            if (d.target) {
                // Soltar en la mitad izquierda de la tarea = su inicio; derecha = su fin.
                const rect = this.canvasRef.el.getBoundingClientRect();
                const px = ev.clientX - rect.left + this.scrollerRef.el.scrollLeft;
                const toStart = d.target.milestone || px < (this.x(d.target.s) + this.x(d.target.e)) / 2;
                d.toStart = toStart;
                d.type = (d.fromFinish ? "f" : "s") + (toStart ? "s" : "f");
            }
            this.state.dragTip = d.target
                ? _t("Link %(from)s → %(to)s: %(type)s", { from: d.t.code, to: d.target.code, type: LINK_LABELS[d.type] })
                : _t("Drop on the start or the finish of the task that follows");
        } else {
            const dias = Math.round(dx / this.dayW);
            if (d.mode === "move") {
                d.t.s = d.s + dias * DAY_MS;
                d.t.e = d.e + dias * DAY_MS;
            } else {
                d.t.e = Math.max(d.s, d.e + dias * DAY_MS);
            }
            this.state.dragTip = `${formatDate(DateTime.fromMillis(d.t.s))} → ${formatDate(DateTime.fromMillis(d.t.e))}`;
        }
        this.state.dragTipPos = { x: ev.clientX, y: ev.clientY };
        this.schedule();
    }
    /** Con el dedo, el navegador se queda el gesto para desplazar y manda
     *  `pointercancel`: la barra vuelve a su lugar y no queda «agarrada». */
    onCanvasPointerCancel() {
        const d = this.drag;
        if (!d) {
            return;
        }
        this.drag = null;
        this.state.dragTip = null;
        d.t.s = d.s;
        d.t.e = d.e;
        this.schedule();
    }
    async onCanvasPointerUp(ev) {
        const d = this.drag;
        if (!d) {
            return;
        }
        this.drag = null;
        this.state.dragTip = null;
        if (!d.mode || d.cancelled) {
            d.t.s = d.s;
            d.t.e = d.e;
            this.schedule();
            return;
        }
        if (d.mode === "link") {
            this.schedule();
            // El destino es donde se SUELTA, no la última tarea por la que se
            // pasó: soltar fuera de toda tarea no crea nada.
            const aqui = this.rowAt(ev);
            const rect = this.canvasRef.el.getBoundingClientRect();
            const dentro = ev.clientX >= rect.left && ev.clientX <= rect.right && ev.clientY >= rect.top && ev.clientY <= rect.bottom;
            if (d.target && dentro && aqui?.id === d.target.id) {
                await this.setLink(d.target, d.t.id, { type: d.type, lag: 0, elapsed: false });
            }
            return;
        }
        const s = d.t.s;
        const e = d.t.e;
        d.t.s = d.s;
        d.t.e = d.e;
        await this.writeDates(d.t, s, e);
    }

    rowAt(ev) {
        const rect = this.canvasRef.el.getBoundingClientRect();
        const i = Math.floor((ev.clientY - rect.top + this.scrollerRef.el.scrollTop) / ROW_H);
        return this.rows[i];
    }
    onCanvasClick(ev) {
        const t = this.rowAt(ev);
        if (t) {
            this.select(t);
        }
    }
    onCanvasDblClick(ev) {
        const t = this.rowAt(ev);
        if (t) {
            this.openTask(t);
        }
    }
    setZoom(zoom) {
        this.zoomTo(ZOOMS[zoom], this.scrollerRef.el.clientWidth / 2);
        this.state.zoom = zoom;
    }
    /** Semestre y Año van en el menú «⋯». */
    chooseScale(zoom) {
        this.state.moreScales = false;
        this.setZoom(zoom);
    }
    /** Cambia el ancho del día manteniendo fija la fecha bajo `anchorX`. */
    zoomTo(dayW, anchorX) {
        const el = this.scrollerRef.el;
        const fecha = this.t0 + ((el.scrollLeft + anchorX) / this.dayW) * DAY_MS;
        this.state.dayW = Math.min(80, Math.max(0.15, dayW));
        this.state.zoom = this.scale;
        // El espaciador cambia de ancho en el siguiente render; se reubica después.
        requestAnimationFrame(() => {
            el.scrollLeft = Math.max(0, this.x(fecha) - anchorX);
            this.schedule();
        });
    }
    /** Ctrl + rueda: zoom continuo centrado en el cursor, como en MS Project. */
    onTimelineWheel(ev) {
        if (!ev.ctrlKey) {
            return;
        }
        ev.preventDefault();
        const rect = this.scrollerRef.el.getBoundingClientRect();
        this.zoomTo(this.dayW * (ev.deltaY < 0 ? 1.15 : 1 / 1.15), ev.clientX - rect.left);
    }
    /** «Ajustar al proyecto»: todo el cronograma en el ancho de la ventana. */
    fitProject() {
        const conFecha = this.tasks.filter((t) => t.s !== null);
        if (!conFecha.length) {
            return;
        }
        const ini = Math.min(...conFecha.map((t) => t.s));
        const fin = Math.max(...conFecha.map((t) => t.e));
        const el = this.scrollerRef.el;
        this.state.dayW = Math.min(80, Math.max(0.15, (el.clientWidth - 60) / Math.max(1, (fin - ini) / DAY_MS)));
        this.state.zoom = this.scale;
        requestAnimationFrame(() => this.scrollToDate(ini));
    }

    /** «Mostrar nivel N» de MS Project: pliega todo resumen de nivel ≥ N. */
    showLevel(value) {
        // Viene del <select> como texto: en una plantilla OWL `Number` no
        // existe (cada identificador se busca en el componente), y llamarlo
        // ahí falla con «v6 is not a function».
        const level = parseInt(value, 10) || 0;
        this.state.level = level;
        this.collapsed.clear();
        if (level) {
            for (const t of this.tasks) {
                if (t.summary && t.depth >= level - 1) {
                    this.collapsed.add(t.id);
                }
            }
        }
        this.refreshRows();
        this.schedule();
    }
    get levels() {
        void this.state.version;
        return [...new Set((this.tasks || []).map((t) => t.depth + 1))].sort((a, b) => a - b);
    }

    // -------------------------------------------------- divisor tabla | línea de tiempo
    savedTableWidth() {
        try {
            return Number(window.localStorage.getItem(TABLE_W_KEY)) || 640;
        } catch {
            return 640;
        }
    }
    /** Pantalla de celular o tableta vertical (menos de 992 px). */
    get compact() {
        return this.ui.size <= SIZES.MD;
    }
    /** El ancho que de verdad ocupa la tabla: el guardado, pero sin comerse
     *  la línea de tiempo. Con 640 px fijos, en un celular el gantt medía 0. */
    get tableWidth() {
        const cuerpo = this.state.bodyW;
        if (!cuerpo) {
            return this.state.tableW;
        }
        const max = Math.max(140, Math.round(cuerpo * (this.compact ? 0.45 : 0.75)));
        return Math.min(this.state.tableW, max);
    }
    // En pantallas táctiles la tabla no tiene barra vertical propia: el dedo
    // la desplaza moviendo el área de la línea de tiempo, como la rueda.
    onTableTouchStart(ev) {
        this.touchY = ev.touches.length === 1 ? ev.touches[0].clientY : null;
    }
    onTableTouchMove(ev) {
        if (this.touchY === null || this.touchY === undefined || ev.touches.length !== 1) {
            return;
        }
        const y = ev.touches[0].clientY;
        this.scrollerRef.el.scrollTop += this.touchY - y;
        this.touchY = y;
    }
    onSplitterDown(ev) {
        ev.preventDefault();
        const x0 = ev.clientX;
        const w0 = this.tableWidth;
        const max = this.scrollerRef.el.parentElement.parentElement.clientWidth * 0.75;
        const move = (e) => {
            this.state.tableW = Math.round(Math.min(max, Math.max(260, w0 + e.clientX - x0)));
        };
        const up = () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", up);
            try {
                window.localStorage.setItem(TABLE_W_KEY, String(this.state.tableW));
            } catch {
                // sin almacenamiento: el ancho vale solo para esta sesión
            }
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    }

    // ------------------------------------------------------------------ teclado
    onKeyDown(ev) {
        const i = this.rowIndex.get(this.state.selected);
        const t = this.rows[i];
        if (this.state.editing) {
            return;
        }
        // Lo que se teclea en la búsqueda o en un filtro es texto, no un
        // atajo (Supr borraría la tarea seleccionada).
        if (["INPUT", "SELECT", "TEXTAREA"].includes(ev.target.tagName)) {
            return;
        }
        // Ctrl+Z deshace; Ctrl+Y o Ctrl+Mayús+Z rehace.
        if ((ev.ctrlKey || ev.metaKey) && this.state.editable && ["z", "y"].includes(ev.key.toLowerCase())
            && !["INPUT", "SELECT", "TEXTAREA"].includes(ev.target.tagName)) {
            ev.preventDefault();
            if (ev.key.toLowerCase() === "y" || ev.shiftKey) {
                this.redo();
            } else {
                this.undo();
            }
            return;
        }
        if (ev.altKey && ev.shiftKey && t && ["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown"].includes(ev.key)) {
            this.structure({ ArrowRight: "indent", ArrowLeft: "outdent", ArrowUp: "up", ArrowDown: "down" }[ev.key], t);
            ev.preventDefault();
            return;
        }
        if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
            const j = i === undefined ? 0 : Math.min(this.rows.length - 1, Math.max(0, i + (ev.key === "ArrowDown" ? 1 : -1)));
            this.select(this.rows[j]);
            this.ensureRowVisible(j);
        } else if (ev.key === "ArrowLeft" && t) {
            if (t.summary && !this.collapsed.has(t.id)) {
                this.toggle(t);
            } else if (t.parent_id && this.byId.has(t.parent_id)) {
                const padre = this.byId.get(t.parent_id);
                this.select(padre);
                this.ensureRowVisible(this.rowIndex.get(padre.id));
            }
        } else if (ev.key === "ArrowRight" && t?.summary && this.collapsed.has(t.id)) {
            this.toggle(t);
        } else if (ev.key === "Enter" && t) {
            this.openTask(t);
        } else if (ev.key === "Escape") {
            if (this.drag) {
                // Esc cancela el arrastre en curso: la barra vuelve a su lugar.
                this.drag.cancelled = true;
                this.drag.t.s = this.drag.s;
                this.drag.t.e = this.drag.e;
                this.drag.target = null;
                this.state.dragTip = null;
            }
            this.state.menu = null;
            this.state.pickLink = null;
            this.state.trace = null;
            this.schedule();
        } else if (ev.key === "Insert" && t) {
            this.structure("insert", t);
        } else if (ev.key === "Delete" && t) {
            this.structure("delete", t);
        } else {
            return;
        }
        ev.preventDefault();
    }
    ensureRowVisible(i) {
        const el = this.scrollerRef.el;
        if (i * ROW_H < el.scrollTop) {
            el.scrollTop = i * ROW_H;
        } else if ((i + 1) * ROW_H > el.scrollTop + el.clientHeight) {
            el.scrollTop = (i + 1) * ROW_H - el.clientHeight;
        }
    }

    scrollToToday() {
        this.scrollToDate(Date.now());
    }
    scrollToDate(ms) {
        const el = this.scrollerRef.el;
        if (el) {
            el.scrollLeft = Math.max(0, this.x(ms) - 3 * this.dayW - 40);
        }
        this.schedule();
    }

    // ------------------------------------------------------------- dibujo
    resize() {
        const el = this.scrollerRef.el;
        if (!el) {
            return;
        }
        this.state.count = Math.ceil(el.clientHeight / ROW_H) + 2;
        this.state.bodyW = this.bodyRef.el?.clientWidth || 0;
        const dpr = window.devicePixelRatio || 1;
        for (const [canvas, h] of [[this.canvasRef.el, el.clientHeight], [this.headerRef.el, HEADER_H]]) {
            canvas.width = Math.floor(el.clientWidth * dpr);
            canvas.height = Math.floor(h * dpr);
            canvas.style.width = `${el.clientWidth}px`;
            canvas.style.height = `${h}px`;
        }
        this.schedule();
    }
    schedule() {
        if (!this.frame) {
            this.frame = requestAnimationFrame(() => {
                this.frame = null;
                this.draw();
            });
        }
    }
    theme() {
        const cs = getComputedStyle(this.scrollerRef.el);
        return { text: cs.color, line: "rgba(128,128,128,0.18)", strong: "rgba(128,128,128,0.45)", font: cs.fontFamily };
    }
    draw() {
        if (!this.scrollerRef.el || !this.rows) {
            return;
        }
        const el = this.scrollerRef.el;
        const W = el.clientWidth;
        const H = el.clientHeight;
        const left = el.scrollLeft;
        const top = el.scrollTop;
        const dpr = window.devicePixelRatio || 1;
        const th = this.theme();
        const dayW = this.dayW;
        const dayFrom = Math.floor(left / dayW);
        const dayTo = Math.ceil((left + W) / dayW);

        // ---- cuerpo
        const ctx = this.canvasRef.el.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, W, H);
        // fines de semana y líneas de mes
        for (let d = dayFrom; d <= dayTo; d++) {
            const dt = DateTime.fromMillis(this.t0 + d * DAY_MS);
            const xd = d * dayW - left;
            // Días no laborables DEL CALENDARIO del proyecto (antes,
            // sábado y domingo fijos) y sus feriados, que se ven desde más lejos.
            const feriado = dayW >= 2 && this.holidays?.has(dt.toISODate());
            if (feriado || (dayW >= 8 && this.offWeekdays?.has(dt.weekday))) {
                ctx.fillStyle = feriado ? COLORS.holiday : COLORS.weekend;
                ctx.fillRect(xd, 0, Math.max(dayW, 1), H);
            }
            if (dt.day === 1) {
                ctx.fillStyle = th.line;
                ctx.fillRect(Math.round(xd), 0, 1, H);
            }
        }
        const first = Math.floor(top / ROW_H);
        const last = Math.min(this.rows.length - 1, Math.ceil((top + H) / ROW_H));
        // fila seleccionada y separadores
        for (let i = first; i <= last; i++) {
            const y = i * ROW_H - top;
            if (this.rows[i]?.id === this.state.selected) {
                ctx.fillStyle = COLORS.select;
                ctx.fillRect(0, y, W, ROW_H);
            }
            ctx.fillStyle = th.line;
            ctx.fillRect(0, y + ROW_H - 1, W, 1);
        }
        // hoy
        const xt = this.x(Date.now()) - left;
        ctx.strokeStyle = COLORS.today;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(Math.round(xt) + 0.5, 0);
        ctx.lineTo(Math.round(xt) + 0.5, H);
        ctx.stroke();
        ctx.setLineDash([]);
        // vínculos (debajo de las barras)
        this.drawLinks(ctx, left, top, H);
        // Mientras se arrastra un vínculo se VE adónde va a llegar:
        // la mitad de la barra destino resaltada, el punto exacto, el codo
        // definitivo con su flecha y el tipo junto al cursor.
        if (this.drag?.mode === "link" && this.drag.pointer) {
            this.drawLinkPreview(ctx, left, top);
        }
        // barras
        ctx.font = `12px ${th.font}`;
        ctx.textBaseline = "middle";
        for (let i = first; i <= last; i++) {
            const t = this.rows[i];
            if (t) {
                ctx.globalAlpha = this.inTrace(t) ? 1 : 0.2;
                this.drawTask(ctx, t, i * ROW_H - top, left, th, W);
                ctx.globalAlpha = 1;
            }
        }

        // ---- encabezado: arriba mes (o año), abajo día/semana/mes
        const hc = this.headerRef.el.getContext("2d");
        hc.setTransform(dpr, 0, 0, dpr, 0, 0);
        hc.clearRect(0, 0, W, HEADER_H);
        hc.font = `12px ${th.font}`;
        hc.textBaseline = "middle";
        hc.fillStyle = th.line;
        hc.fillRect(0, HEADER_H / 2, W, 1);
        hc.fillRect(0, HEADER_H - 1, W, 1);
        let prevTop = null;
        let prevBottom = null;
        for (let d = dayFrom - 1; d <= dayTo; d++) {
            const dt = DateTime.fromMillis(this.t0 + d * DAY_MS);
            const xd = d * dayW - left;
            const anual = ["month", "quarter", "semester"].includes(this.scale);
            const topKey = this.scale === "year" ? Math.floor(dt.year / 10) : anual ? dt.year : `${dt.year}-${dt.month}`;
            if (topKey !== prevTop) {
                prevTop = topKey;
                hc.fillStyle = th.strong;
                hc.fillRect(Math.round(xd), 0, 1, HEADER_H / 2);
                hc.fillStyle = th.text;
                const label = this.scale === "year" ? `${Math.floor(dt.year / 10) * 10}–${Math.floor(dt.year / 10) * 10 + 9}`
                    : anual ? String(dt.year) : dt.toFormat("LLLL yyyy");
                hc.fillText(label, Math.max(xd, 0) + 6, HEADER_H / 4);
            }
            let bottomKey;
            let bottomLabel;
            if (this.scale === "day") {
                bottomKey = d;
                bottomLabel = String(dt.day);
            } else if (this.scale === "week") {
                bottomKey = `${dt.weekYear}-${dt.weekNumber}`;
                bottomLabel = _t("W%s", dt.weekNumber);
            } else if (this.scale === "month") {
                bottomKey = `${dt.year}-${dt.month}`;
                bottomLabel = dt.toFormat("LLL");
            } else if (this.scale === "quarter") {
                bottomKey = `${dt.year}-Q${dt.quarter}`;
                bottomLabel = _t("Q%s", dt.quarter);
            } else if (this.scale === "semester") {
                const sem = dt.month <= 6 ? 1 : 2;
                bottomKey = `${dt.year}-H${sem}`;
                bottomLabel = _t("H%s", sem);
            } else {
                bottomKey = String(dt.year);
                bottomLabel = String(dt.year);
            }
            if (bottomKey !== prevBottom) {
                prevBottom = bottomKey;
                hc.fillStyle = th.line;
                hc.fillRect(Math.round(xd), HEADER_H / 2, 1, HEADER_H / 2);
                hc.fillStyle = th.text;
                hc.fillText(bottomLabel, xd + 4, (HEADER_H * 3) / 4);
            }
        }
        if (xt > 0 && xt < W) {
            hc.fillStyle = COLORS.today;
            hc.fillRect(Math.round(xt) - 1, HEADER_H - 4, 3, 4);
        }
    }

    drawTask(ctx, t, y, left, th, W) {
        if (t.s === null) {
            return;
        }
        // La fecha límite, como la flecha de MS Project: verde, o roja si
        // la tarea termina después.
        if (t.dl !== null) {
            const xd = this.x(t.dl) - left;
            ctx.fillStyle = t.e !== null && t.e > t.dl ? COLORS.deadlineMissed : COLORS.deadline;
            ctx.beginPath();
            ctx.moveTo(xd - 5, y + 3);
            ctx.lineTo(xd + 5, y + 3);
            ctx.lineTo(xd, y + 10);
            ctx.closePath();
            ctx.fill();
            ctx.fillRect(Math.round(xd) - 1, y + 9, 2, ROW_H - 12);
        }
        const x0 = this.x(t.s) - left;
        const x1 = Math.max(this.x(t.e) - left, x0 + 2);
        // La banda de holgura y las líneas base pueden quedar a la vista
        // aunque la barra no: el recorte mira la extensión de las tres.
        const lineas = this.baselineSegments(t);
        const xBanda = this.floatBandEnd(t);
        const xs = [x0, x1, ...(xBanda ? [xBanda - left] : []), ...lineas.flatMap((l) => [this.x(l.s) - left, this.x(l.e) - left])];
        if (Math.max(...xs) < -400 || Math.min(...xs) > W + 400) {
            return;
        }
        // Líneas base debajo de la barra: la vigente y las comparadas en una franja.
        this.drawBaselineStrip(ctx, lineas, left, y + ROW_H - 8, 4);
        const mid = y + ROW_H / 2 - 1;
        // La banda de holgura, del fin de la barra al fin más tardío
        if (xBanda) {
            this.drawFloatBand(ctx, t.milestone ? x0 : x1, xBanda - left, mid);
        }
        if (t.milestone) {
            ctx.fillStyle = COLORS.milestone;
            ctx.beginPath();
            ctx.moveTo(x0, mid - 6);
            ctx.lineTo(x0 + 6, mid);
            ctx.lineTo(x0, mid + 6);
            ctx.lineTo(x0 - 6, mid);
            ctx.closePath();
            ctx.fill();
            ctx.fillStyle = th.text;
            ctx.fillText(t.name, x0 + 10 + (this.showHandles(t) ? HANDLE_GAP + HANDLE_R * 2 : 0), mid);
            if (this.showHandles(t)) {
                this.drawHandles(ctx, x0 - 7, x0 + 7, mid, true);
            }
            return;
        }
        if (t.summary) {
            ctx.fillStyle = th.text;
            ctx.fillRect(x0, mid - 4, x1 - x0, 6);
            for (const xe of [x0, x1]) {
                ctx.beginPath();
                ctx.moveTo(xe - 4, mid + 2);
                ctx.lineTo(xe + 4, mid + 2);
                ctx.lineTo(xe, mid + 7);
                ctx.closePath();
                ctx.fill();
            }
            return;
        }
        const h = 14;
        ctx.fillStyle = t.critical ? COLORS.critical : COLORS.bar;
        this.roundRect(ctx, x0, mid - h / 2, x1 - x0, h, 3);
        if (t.progress > 0) {
            ctx.fillStyle = t.critical ? COLORS.criticalProgress : COLORS.barProgress;
            this.roundRect(ctx, x0, mid - h / 2, ((x1 - x0) * Math.min(t.progress, 100)) / 100, h, 3);
        }
        ctx.fillStyle = th.text;
        ctx.fillText(t.name, x1 + 6 + (this.showHandles(t) ? HANDLE_GAP + HANDLE_R * 2 : 0), mid);
        if (this.showHandles(t)) {
            this.drawHandles(ctx, x0, x1, mid);
        }
    }
    // ---- banda de holgura
    /** Dónde termina la banda (px absolutos), o null: sin holgura, crítica,
     * terminada, resumen o banda apagada. Termina en el fin MÁS TARDÍO del
     * motor, no en fin + holgura × px/día: la holgura va en días laborables y
     * sobre un fin de semana la banda se quedaría corta. */
    floatBandEnd(t) {
        if (!this.state.showFloat || t.summary || t.critical || t.actual_finish || !t.lf || t.e === null || !(t.float > 0)) {
            return null;
        }
        return t.lf > t.e ? this.x(t.lf) : null;
    }
    /** Media altura, verde tenue con trama cruzada: se lee como «espacio», no
     * como una segunda barra. */
    drawFloatBand(ctx, xa, xb, mid) {
        const alto = 7;
        ctx.fillStyle = COLORS.float + "40";
        ctx.fillRect(xa, mid - alto / 2, xb - xa, alto);
        if (!this.hatch) {
            const c = document.createElement("canvas");
            c.width = c.height = 6;
            const g = c.getContext("2d");
            g.strokeStyle = COLORS.float + "66";
            g.lineWidth = 1;
            g.beginPath();
            g.moveTo(0, 6);
            g.lineTo(6, 0);
            g.moveTo(0, 0);
            g.lineTo(6, 6);
            g.stroke();
            this.hatch = ctx.createPattern(c, "repeat");
        }
        if (this.hatch) {
            ctx.fillStyle = this.hatch;
            ctx.fillRect(xa, mid - alto / 2, xb - xa, alto);
        }
    }
    // ---- franja de líneas base
    /** Los tramos de línea base de la tarea: la vigente y las comparadas, cada uno con su color. */
    baselineSegments(t) {
        const out = [];
        if (t.bs !== null && t.be !== null) {
            out.push({ s: t.bs, e: t.be, color: COLORS.baseline });
        }
        for (const [i, id] of this.state.compare.entries()) {
            const f = this.compareDates?.get(id)?.get(t.id);
            if (f) {
                out.push({ s: f.s, e: f.e, color: COMPARE_COLORS[i] });
            }
        }
        return out;
    }
    /** Una sola franja bajo la barra. Donde dos o tres líneas base se traslapan,
     * rayas diagonales con sus colores; un tramo de duración cero (un
     * hito) es un rombo, partido en franjas si coinciden varios. */
    drawBaselineStrip(ctx, segs, left, top, alto) {
        if (!segs.length) {
            return;
        }
        const tramos = segs.map((g) => ({ a: this.x(g.s) - left, b: this.x(g.e) - left, color: g.color }));
        const hitos = tramos.filter((g) => g.b - g.a < 1);
        const barras = tramos.filter((g) => g.b - g.a >= 1);
        const cortes = [...new Set(barras.flatMap((g) => [g.a, g.b]))].sort((p, q) => p - q);
        for (let k = 0; k + 1 < cortes.length; k++) {
            const [a, b] = [cortes[k], cortes[k + 1]];
            const colores = barras.filter((g) => g.a <= a && g.b >= b).map((g) => g.color);
            if (!colores.length) {
                continue;
            }
            if (colores.length === 1) {
                ctx.fillStyle = colores[0];
                ctx.fillRect(a, top, b - a, alto);
                continue;
            }
            ctx.save();
            ctx.beginPath();
            ctx.rect(a, top, b - a, alto);
            ctx.clip();
            const paso = 3;
            for (let x = a - alto, n = 0; x < b; x += paso, n++) {
                ctx.fillStyle = colores[n % colores.length];
                ctx.beginPath();
                ctx.moveTo(x, top + alto);
                ctx.lineTo(x + alto, top);
                ctx.lineTo(x + alto + paso, top);
                ctx.lineTo(x + paso, top + alto);
                ctx.closePath();
                ctx.fill();
            }
            ctx.restore();
        }
        const porX = new Map();
        for (const h of hitos) {
            const clave = Math.round(h.a);
            porX.set(clave, [...(porX.get(clave) || []), h.color]);
        }
        const r = 4;
        for (const [x, colores] of porX) {
            const cy = top + alto / 2;
            colores.forEach((color, i) => {
                ctx.save();
                ctx.beginPath();
                ctx.rect(x - r + (2 * r * i) / colores.length, cy - r, (2 * r) / colores.length, 2 * r);
                ctx.clip();
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.moveTo(x, cy - r);
                ctx.lineTo(x + r, cy);
                ctx.lineTo(x, cy + r);
                ctx.lineTo(x - r, cy);
                ctx.closePath();
                ctx.fill();
                ctx.restore();
            });
        }
    }
    drawLinkPreview(ctx, left, top) {
        const d = this.drag;
        const rect = this.canvasRef.el.getBoundingClientRect();
        const ia = this.rowIndex.get(d.t.id);
        const sx = this.x(d.fromFinish && !d.t.milestone ? d.t.e : d.t.s) - left;
        const sy = ia * ROW_H - top + ROW_H / 2 - 1;
        // el lado de salida, marcado en la barra de origen
        ctx.fillStyle = COLORS.linkOk;
        ctx.beginPath();
        ctx.arc(sx, sy, 4, 0, Math.PI * 2);
        ctx.fill();
        if (!d.target) {
            ctx.strokeStyle = COLORS.link;
            ctx.setLineDash([5, 4]);
            ctx.beginPath();
            ctx.moveTo(sx, sy);
            ctx.lineTo(d.pointer.x - rect.left, d.pointer.y - rect.top);
            ctx.stroke();
            ctx.setLineDash([]);
            return;
        }
        const b = d.target;
        const ib = this.rowIndex.get(b.id);
        const y = ib * ROW_H - top;
        const bx0 = this.x(b.s) - left;
        const bx1 = Math.max(this.x(b.e) - left, bx0 + 2);
        const mitad = (bx0 + bx1) / 2;
        // la mitad de llegada, resaltada
        ctx.fillStyle = COLORS.linkZone;
        ctx.strokeStyle = COLORS.linkOk;
        const zx = b.milestone ? bx0 - 8 : d.toStart ? bx0 : mitad;
        const zw = b.milestone ? 16 : (bx1 - bx0) / 2;
        ctx.fillRect(zx, y + 3, zw, ROW_H - 7);
        ctx.strokeRect(zx + 0.5, y + 3.5, zw - 1, ROW_H - 8);
        const tx = d.toStart ? bx0 : bx1;
        const ty = y + ROW_H / 2 - 1;
        // el codo definitivo, como quedará dibujado
        const pts = linkPath(d.type, { x: sx, y: sy }, { x: tx, y: ty });
        ctx.strokeStyle = COLORS.linkOk;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        for (const p of pts.slice(1)) {
            ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
        ctx.lineWidth = 1;
        ctx.fillStyle = COLORS.linkOk;
        ctx.beginPath();
        ctx.arc(tx, ty, 4, 0, Math.PI * 2);
        ctx.fill();
        // el tipo, grande, junto al cursor
        const px = d.pointer.x - rect.left + 12;
        const py = d.pointer.y - rect.top - 14;
        ctx.font = "bold 12px sans-serif";
        const etiqueta = d.type.toUpperCase();
        const w = ctx.measureText(etiqueta).width + 10;
        ctx.fillStyle = COLORS.linkOk;
        this.roundRect(ctx, px, py, w, 18, 4);
        ctx.fillStyle = "#ffffff";
        ctx.fillText(etiqueta, px + 5, py + 9);
    }

    showHandles(t) {
        return this.state.editable && !t.summary && (t.id === this.hover || t.id === this.state.selected);
    }
    drawHandles(ctx, x0, x1, mid, milestone = false) {
        ctx.lineWidth = 1.5;
        for (const cx of milestone ? [x1 + HANDLE_GAP + HANDLE_R] : [x0 - HANDLE_GAP - HANDLE_R, x1 + HANDLE_GAP + HANDLE_R]) {
            ctx.beginPath();
            ctx.arc(cx, mid, HANDLE_R, 0, Math.PI * 2);
            ctx.fillStyle = "#ffffff";
            ctx.fill();
            ctx.strokeStyle = COLORS.bar;
            ctx.stroke();
        }
    }

    roundRect(ctx, x, y, w, h, r) {
        ctx.beginPath();
        ctx.roundRect ? ctx.roundRect(x, y, w, h, r) : ctx.rect(x, y, w, h);
        ctx.fill();
    }

    drawLinks(ctx, left, top, H) {
        this.linkHits = [];
        const firstY = top - ROW_H;
        const lastY = top + H + ROW_H;
        ctx.lineWidth = 1;
        for (const l of this.links) {
            const ia = this.rowIndex.get(l.from);
            const ib = this.rowIndex.get(l.to);
            if (ia === undefined || ib === undefined) {
                continue;
            }
            const ya = ia * ROW_H;
            const yb = ib * ROW_H;
            if (Math.max(ya, yb) < firstY || Math.min(ya, yb) > lastY) {
                continue;
            }
            const a = this.byId.get(l.from);
            const b = this.byId.get(l.to);
            if (a.s === null || b.s === null) {
                continue;
            }
            const sx = this.x(l.type === "fs" || l.type === "ff" ? a.e : a.s) - left;
            const tx = this.x(l.type === "fs" || l.type === "ss" ? b.s : b.e) - left;
            const pts = linkPath(l.type, { x: sx, y: ya - top + ROW_H / 2 - 1 }, { x: tx, y: yb - top + ROW_H / 2 - 1 });
            this.linkHits.push({ l, pts });
            const enRuta = this.state.trace && this.state.trace.ids.has(a.id) && this.state.trace.ids.has(b.id);
            // En la ruta, el vínculo que manda va grueso y sólido; el
            // que no manda (su sucesora tiene holgura respecto de él), punteado.
            const manda = enRuta && this.state.trace.driving?.has(`${l.from}-${l.to}`);
            const noManda = enRuta && this.state.trace.driving && !manda;
            ctx.globalAlpha = !this.state.trace || enRuta ? 1 : 0.15;
            ctx.lineWidth = manda ? 2.5 : enRuta && !noManda ? 2 : 1;
            ctx.setLineDash(noManda ? [4, 3] : []);
            const color = enRuta ? COLORS.today : a.critical && b.critical ? COLORS.critical : COLORS.link;
            ctx.strokeStyle = color;
            ctx.beginPath();
            ctx.moveTo(pts[0].x, pts[0].y);
            for (const p of pts.slice(1)) {
                ctx.lineTo(p.x, p.y);
            }
            ctx.stroke();
            ctx.setLineDash([]);
            // flecha hacia la tarea destino
            const end = pts[pts.length - 1];
            const dir = l.type === "fs" || l.type === "ss" ? 1 : -1;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.moveTo(end.x, end.y);
            ctx.lineTo(end.x - dir * 5, end.y - 3.5);
            ctx.lineTo(end.x - dir * 5, end.y + 3.5);
            ctx.closePath();
            ctx.fill();
        }
    }

    get linkTypes() {
        return Object.entries(LINK_LABELS);
    }

    // -------------------------------------------------------------- barra de estado
    // ---- filtros
    setFilter(key, value) {
        this.state.filters = { ...this.state.filters, [key]: value };
        this.refreshRows();
        this.schedule();
    }
    clearFilters() {
        this.state.filters = { ...EMPTY_FILTERS };
        this.refreshRows();
        this.schedule();
    }
    get activeFilterCount() {
        const f = this.state.filters;
        return ["user", "critical", "late", "milestones"].filter((k) => f[k]).length + (f.from || f.to ? 1 : 0);
    }
    get assigneeNames() {
        void this.state.version;
        const nombres = new Set();
        for (const t of this.tasks || []) {
            for (const n of (t.users || "").split(", ")) {
                if (n) {
                    nombres.add(n);
                }
            }
        }
        return [...nombres].sort((a, b) => a.localeCompare(b));
    }

    get stats() {
        void this.state.version;
        const tareas = this.tasks || [];
        const fin = tareas.reduce((m, t) => (t.e && t.e > m ? t.e : m), 0);
        return {
            tasks: tareas.filter((t) => !t.summary).length,
            milestones: tareas.filter((t) => t.milestone).length,
            critical: tareas.filter((t) => t.critical && !t.summary).length,
            links: (this.links || []).length,
            finish: fin ? formatDate(DateTime.fromMillis(fin)) : "",
            // Cuántas filas deja ver el filtro (sin contar resúmenes).
            shown: this.filterKeep ? tareas.filter((t) => this.filterKeep.has(t.id) && !t.summary).length : null,
        };
    }
}
