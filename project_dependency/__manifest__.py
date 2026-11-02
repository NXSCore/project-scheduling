# -*- coding: utf-8 -*-
{
    "name": "Project Dependencies — Types, Lag and Critical Path",
    "version": "18.0.1.20.0",
    "category": "Project",
    "license": "LGPL-3",
    "summary": "Finish-to-start, start-to-start, finish-to-finish and "
               "start-to-finish links with lag, and the critical path they "
               "make computable.",
    "description": """
Odoo 19 trae `project.task.depend_on_ids`: un Many2many pelado, sin tipo y sin
desfase. Eso es un fin-a-inicio implícito y nada más —`project/models/
project_task.py:281`; `project_enterprise` tampoco los añade—.

**No es un detalle cosmético: sin tipos, la ruta crítica se calcula mal.** Dos
ingenierías que arrancan juntas (inicio-a-inicio) obligadas a ir en fila por
falta de tipo alargan el proyecto en el cálculo y ponen en la ruta crítica a
quien no está.

Le sirve a cualquier proyecto de Odoo, en Community o Enterprise. El Gantt de
Enterprise lo pinta `project_dependency_gantt`. Lo propio de un dominio —a quién
se le avisa cuando la ruta crítica se retrasa— va en un módulo de extensión.

**Convive con `depend_on_ids`, no lo sustituye.** Un fin-a-inicio sin desfase
se refleja en el campo nativo para que el Gantt lo siga dibujando y la lógica
de tarea bloqueada siga funcionando. Los otros tres tipos viven solo aquí: el
Gantt no sabe dibujarlos, y dibujarlos como fin-a-inicio diría en pantalla algo
distinto de lo que se calcula.
""",
    "author": "Iván Candelas (Nexus Core)",
    "website": "https://nxscore.mx",
    "depends": ["project", "project_planned_dates"],
    "data": [
        "security/ir.model.access.csv",
        "security/project_dependency_rules.xml",
        "views/project_dependency_views.xml",
        "wizards/schedule_simulation_views.xml",
        "wizards/schedule_health_views.xml",
        "wizards/schedule_report_views.xml",
    ],
    "installable": True,
    "application": False,
}
