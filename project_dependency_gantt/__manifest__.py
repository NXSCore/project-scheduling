# -*- coding: utf-8 -*-
{
    "name": "Project Dependencies — Enterprise Gantt",
    "version": "19.0.1.0.0",
    "category": "Services/Project",
    "license": "LGPL-3",
    "summary": "Paints the critical path on the Enterprise task Gantt and lets the link type be picked from its connector.",
    "description": """
Puente de `project_dependency` con el Gantt de Enterprise (`web_gantt` / `project_enterprise`).
Se instala solo (`auto_install`) cuando los dos están presentes; en Community no se instala y
el cronograma se ve en el planificador de `project_planner`.

- Colorea la ruta crítica en el Gantt de tareas y lleva sus campos a la barra.
- Botón «Dependencias» en el popover de la barra: tipo y desfase a dos clics.
- Selector de tipo de vínculo dentro del conector del Gantt (parche OWL sobre `GanttConnector`).

Separado de `project_dependency` para que el motor (tipos, desfase, ruta crítica, simulación
y salud del cronograma) instale en Community.
""",
    "author": "Iván Candelas (Nexus Core)",
    "website": "https://nxscore.mx",
    "depends": ["project_dependency", "project_enterprise"],
    "data": ["views/project_task_views.xml"],
    # `web.assets_backend_lazy`, NO `web.assets_backend`. `web_gantt`
    # declara ahí sus componentes —el Gantt se carga solo cuando alguien lo
    # abre— así que un parche en el bundle normal se evalúa ANTES de que
    # `@web_gantt/gantt_connector` exista y el navegador tumba el módulo
    # entero con "unmet dependencies". `project_enterprise` hace lo mismo con
    # todo lo suyo de Gantt.
    "assets": {
        "web.assets_backend_lazy": [
            "project_dependency_gantt/static/src/gantt_connector_type.js",
            "project_dependency_gantt/static/src/gantt_connector_type.xml",
        ],
    },
    "installable": True,
    "auto_install": True,
    "application": False,
}
