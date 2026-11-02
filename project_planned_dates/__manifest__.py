# -*- coding: utf-8 -*-
{
    "name": "Project Planned Dates (Community)",
    "version": "19.0.1.0.0",
    "category": "Services/Project",
    "license": "LGPL-3",
    "summary": "Planned start date on project tasks without Odoo Enterprise, so the scheduling modules run on Community.",
    "description": """
En Odoo 19 la fecha de inicio planeada de una tarea (`project.task.planned_date_begin`) la
declara `project_enterprise` (`project_enterprise/models/project_task.py:26`). Community solo
trae la fecha límite (`date_deadline`). Sin inicio no hay duración, y sin duración no hay
dependencias con desfase, ruta crítica, planificador ni intercambio con Microsoft Project.

Este módulo declara el campo con la MISMA definición que Enterprise —nombre, tipo, columna y
restricción `_planned_dates_check`—, así que:

- **En Community** da el campo y lo muestra como rango (inicio → fin) en el formulario y la lista.
- **En Enterprise** no estorba: Odoo funde las dos definiciones en una sola columna y una sola
  restricción, y las vistas aplican los mismos atributos que ya pone `project_enterprise`.
  Instalar Enterprise después sobre una base Community conserva los datos.

No trae la vista Gantt (es de `web_gantt`, Enterprise). En Community el Gantt es el
planificador de `project_planner`.
""",
    "author": "Iván Candelas (Nexus Core)",
    "website": "https://nxscore.mx",
    "depends": ["project"],
    "data": ["views/project_task_views.xml"],
    "installable": True,
    "application": False,
}
