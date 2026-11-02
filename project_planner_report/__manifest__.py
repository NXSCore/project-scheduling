# -*- coding: utf-8 -*-
{
    "name": "Project Planner PDF Report",
    "version": "18.0.1.7.0",
    "category": "Services/Project",
    "license": "LGPL-3",
    "summary": "Export the planner's task table and Gantt chart to a paginated PDF.",
    "description": """
El «Informe» del planificador.

Botón «Informe» en el planificador (las dos entradas: vista y pantalla
completa) que abre un asistente con las opciones del documento —empresa,
autor, papel A4/A3/Carta/Tabloide, orientación, tamaño de letra, colores por
ruta crítica, línea de estado, páginas del cronograma, ajustar al papel,
seguir la vista, encabezado repetido, nombres en barras, avance, línea base,
holgura, dependencias, solo días laborables, fines de semana, leyenda— y
descarga un PDF vectorial paginado (tabla + Gantt, «n / N»).

Módulo aparte porque es OPCIONAL y se despliega por separado: el planificador
no lo necesita. Dibuja con `reportlab` (dependencia de Odoo); no usa
wkhtmltopdf. Lee las tareas con los permisos de quien imprime.
""",
    "author": "Iván Candelas (Nexus Core)",
    "website": "https://nxscore.mx",
    "depends": ["project_planner"],
    "data": [
        "security/ir.model.access.csv",
        "security/report_security.xml",
        "views/report_wizard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "project_planner_report/static/src/*",
        ],
    },
    "installable": True,
    "application": False,
}
