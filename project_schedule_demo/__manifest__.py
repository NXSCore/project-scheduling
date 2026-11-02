# -*- coding: utf-8 -*-
{
    "name": "Project Scheduling — Demo Project",
    "version": "18.0.1.0.0",
    "category": "Services/Project",
    "license": "LGPL-3",
    "summary": "A sample office-building project with WBS, the four link types, lags, milestones and a critical path.",
    "description": """
Un proyecto de ejemplo para enseñar la suite de programación en una demo o una capacitación,
en Community o en Enterprise:

- Paquetes y subtareas (EDT de dos niveles).
- Los cuatro tipos de vínculo: fin-inicio, inicio-inicio, fin-fin e inicio-fin, con desfase
  positivo, adelanto (desfase negativo) y desfase en días naturales.
- Dos hitos de cero días y una ruta crítica que se ve en el planificador.

Las fechas se calculan a partir del día de instalación, así que el proyecto siempre está «vivo».
Es dato de ejemplo: no se instala en producción.
""",
    "author": "Iván Candelas (Nexus Core)",
    "website": "https://nxscore.mx",
    "depends": ["project_dependency", "project_planner"],
    "data": ["data/demo_project.xml"],
    "installable": True,
    "application": False,
}
