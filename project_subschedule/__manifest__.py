# -*- coding: utf-8 -*-
{
    "name": "Stage Subschedules",
    "version": "18.0.1.0.0",
    "category": "Services/Project",
    "license": "LGPL-3",
    "summary": "A grouping task marks the subschedule of a project stage inside the main schedule; it freezes once the project leaves that stage.",
    "description": """
Un proyecto tiene UN cronograma; cada etapa del proyecto (las etapas nativas de Odoo, `project.project.stage`)
tiene su **subcronograma** dentro de él: una tarea agrupadora marcada con la etapa y todas sus subtareas, que la
heredan. No se parte el cronograma: la ruta crítica y las dependencias entre etapas siguen enteras.

- Etapa en la agrupadora (`phase_id`) y heredada por las subtareas (`effective_phase_id`); una subtarea no
  declara otra etapa.
- Botón «Subcronograma de la etapa» (el Gantt EDT de `project_gantt` con solo esa rama) y «Agrupar por
  etapa».
- Cuando el proyecto pasa a una etapa posterior, el subcronograma de la anterior se congela (nombre, fechas,
  dependencias, padre, altas y bajas). El gancho `_phase_unlocked()` decide quién lo reabre: aquí, nadie;
  un módulo de extensión lo redefine (p. ej., con una solicitud de cambio aprobada). El sistema (`sudo`) no se frena.

Qué resuelve: ver y proteger el cronograma de cada etapa sin partir el del proyecto. Odoo trae etapas de
proyecto y tareas con subtareas, pero sin liga entre ellas. Sirve a cualquier proyecto por etapas
(consultoría, construcción, implantación).
""",
    "author": "Iván Candelas (Nexus Core)",
    "website": "https://nxscore.mx",
    "depends": ["project_gantt"],
    "data": [
        "views/views.xml",
    ],
    "installable": True,
    "application": False,
}
