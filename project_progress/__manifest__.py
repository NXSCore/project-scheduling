# -*- coding: utf-8 -*-
{
    "name": "Project Physical Progress",
    "version": "19.0.1.1.0",
    "category": "Services/Project",
    "license": "LGPL-3",
    "summary": "Physical progress of project tasks with its evidence, expected progress and gap, and a weekly reminder.",
    "description": """
Avance físico de una tarea para cualquier proyecto de Odoo. Depende solo de Proyecto.

- **Avance físico** reportado (0-100), el **esperado** según las fechas (lineal,
  convención) y la **brecha**.
- **Reporte con evidencia**: el avance solo se escribe por el asistente, que
  adjunta el documento o deja constancia de que no lo hubo.
- **Avance vencido** y **recordatorio semanal** a quien tiene la tarea; una
  extensión decide qué tareas entran (`_progress_reminder_domain`).

El hito muestra las fotos de avance de sus tareas (la evidencia de imagen de cada reporte)
para validarlas a la vista.
""",
    "author": "Iván Candelas (Nexus Core)",
    "website": "https://nxscore.mx",
    "depends": ["project", "project_planned_dates"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "wizards/project_progress_report_wizard_views.xml",
        "views/project_task_views.xml",
        "views/project_milestone_views.xml",
    ],
    "installable": True,
    "application": False,
}
