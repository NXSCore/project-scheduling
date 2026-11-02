# -*- coding: utf-8 -*-
{
    "name": "Project WBS Gantt",
    "version": "19.0.1.0.0",
    "category": "Services/Project",
    "license": "LGPL-3",
    "summary": "WBS levels and order and a schedule Gantt by package for any Odoo project (Enterprise).",
    "description": """
Estructura EDT y Gantt del cronograma para cualquier proyecto de Odoo. Depende solo
de Proyecto (Enterprise) y de `project_dependency`.

- **EDT:** paquete raíz, profundidad y grupos de nivel 2 y 3 de cada tarea; el
  código EDT delante del nombre donde se pide y el Gantt en orden EDT,
  con las filas de resumen marcadas. El código EDT y la ruta crítica
  vienen de `project_dependency`.
- **Gantt por paquete:** agrupa por paquete y nivel, colorea la ruta crítica y
  arranca en escala semana; botón «Gantt por EDT» en el proyecto.
- **«Mostrar subtareas» encendido** por omisión en las pantallas de tareas.

Lo propio de cada dominio (reglas, línea base, entregables) va en un módulo de
extensión que herede de este.
""",
    "author": "Iván Candelas (Nexus Core)",
    "website": "https://nxscore.mx",
    "depends": ["project_enterprise", "project_dependency"],
    "data": ["views/project_task_views.xml"],
    "assets": {
        "web.assets_backend": ["project_gantt/static/src/show_subtasks_default.js"],
    },
    "installable": True,
    "application": False,
}
