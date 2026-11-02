# -*- coding: utf-8 -*-
{
    "name": "Mexican Public Holidays (LFT art. 74)",
    "version": "18.0.1.0.0",
    "category": "Human Resources",
    "license": "LGPL-3",
    "summary": "Computes the mandatory rest days of the Mexican Federal Labor Law for a working calendar.",
    "description": """
Los días de descanso obligatorio del artículo 74 de la Ley Federal del Trabajo, **calculados**
por año en vez de cargados a mano, y escritos como ausencias del calendario de trabajo
(`resource.calendar.leaves`) para que se vean y se puedan auditar en Odoo.

- Año Nuevo, Constitución (1er lunes de febrero), Benito Juárez (3er lunes de marzo),
  Trabajo, Independencia, Revolución (3er lunes de noviembre), Navidad y la transmisión
  del Poder Ejecutivo Federal (1 de diciembre, cada seis años desde 2024).
- `resource.calendar._ensure_mx_holidays(year)` los deja en el calendario sin duplicarlos.

Las jornadas electorales (fracción IX) no son deterministas: se cargan a mano.

Separado de `project_gantt` para que una instalación fuera de México no los herede.
""",
    "author": "Iván Candelas (Nexus Core)",
    "website": "https://nxscore.mx",
    "depends": ["resource"],
    "data": [],
    "installable": True,
    "application": False,
}
