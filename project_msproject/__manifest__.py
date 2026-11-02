# -*- coding: utf-8 -*-
{
    "name": "Project - Microsoft Project Exchange",
    "version": "18.0.1.9.0",
    "category": "Services/Project",
    "license": "LGPL-3",
    "summary": "Import and export Microsoft Project XML schedules for any Odoo project.",
    "description": """
Importa el XML de MS Project (*Archivo → Guardar como → XML*, formato MSPDI) a
cualquier proyecto de Odoo: jerarquía y orden EDT,
fechas en la zona del usuario, hitos de 0 días, responsables por correo o
nombre, y vínculos con tipo (FS/SS/FF/SF) y desfase en `project.dependency`.
Reimportar actualiza por `<UID>`; no duplica ni borra. Lector en Python con
`lxml` sin entidades ni red (XXE), sin dependencias nuevas.

También EXPORTA el mismo formato (botón «Exportar a MS Project»), y lo
exportado se reimporta sin perder nada (prueba de ida y vuelta).

Lo de un dominio —cuándo se permite importar, a quién avisar— lo agrega un
módulo de extensión redefiniendo `_check_can_import()` y `_after_import()`.

**Por qué es un módulo aparte:** el intercambio con MS Project es opcional y
queda aislado del motor de programación.
""",
    "author": "Iván Candelas (Nexus Core)",
    "website": "https://nxscore.mx",
    "depends": ["project", "project_planned_dates", "project_dependency"],
    "data": [
        "security/ir.model.access.csv",
        "views/mspdi_import_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
