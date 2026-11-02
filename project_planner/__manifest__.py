# -*- coding: utf-8 -*-
{
    "name": "Project Planner",
    "version": "19.0.1.15.0",
    "category": "Services/Project",
    "license": "LGPL-3",
    "summary": "A Microsoft Project style planner view for Odoo project tasks.",
    "description": """
Vista de planificación al estilo de MS Project para cualquier proyecto de Odoo.

- Tabla (EDT, nombre, duración, inicio, fin, predecesoras) + línea de tiempo en
  un solo `<canvas>`: el scroll cuesta lo mismo con 50 tareas que con 5,000.
- Árbol plegable, resumen, hitos de 0 días, ruta crítica, vínculos de los 4
  tipos con desfase (`project.dependency`), escalas de día a año.
- Edición: arrastrar barras, asas de vínculo, celdas, predecesoras escritas
  como MS Project, menú contextual, insertar/eliminar/sangría/subir/bajar.
- Tipo de vista `planner` en el selector de vistas (también en la app
  Proyectos estándar) y acción cliente a pantalla completa.

Lo específico de un dominio (línea base, avance físico, un botón en otra
ficha) lo agrega un módulo de extensión redefiniendo
`project.task._planner_task_extra()`.

Depende solo de `project`, `project_planned_dates` (fecha de inicio planeada) y
`project_dependency` (vínculos tipados, EDT, hitos y ruta crítica).
""",
    "author": "Iván Candelas (Nexus Core)",
    "website": "https://nxscore.mx",
    "depends": ["project", "project_planned_dates", "project_dependency"],
    "data": [
        "views/project_task_views.xml",
        "views/project_project_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "project_planner/static/src/planner/*",
        ],
    },
    "installable": True,
    "application": False,
}
