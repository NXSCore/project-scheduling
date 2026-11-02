/** @odoo-module **/
// «Mostrar subtareas» arranca ENCENDIDO en
// todas las pantallas de tareas. Odoo guarda ese interruptor en el navegador
// de cada usuario (`localStorage["showSubtasks"]`, leído por
// project/static/src/views/project_task_model_mixin.js y por el panel de
// control de tareas) y su valor de fábrica es «apagado»: un paquete se veía
// sin sus subtareas y el usuario tenía que saber que existía el interruptor.
//
// Solo se fija cuando el navegador TODAVÍA NO TIENE valor: si el usuario lo
// apaga, Odoo guarda «false» y aquí ya no se toca — su elección manda.
import { browser } from "@web/core/browser/browser";

const KEY = "showSubtasks";

try {
    if (browser.localStorage.getItem(KEY) === null) {
        browser.localStorage.setItem(KEY, "true");
    }
} catch {
    // Navegador sin almacenamiento (modo privado estricto): queda el valor de
    // fábrica de Odoo, que es un comportamiento válido.
}
