=========================
Project Physical Progress
=========================

.. |badge1| image:: https://img.shields.io/badge/maturity-Beta-yellow.png
    :target: https://odoo-community.org/page/development-status
    :alt: Beta
.. |badge2| image:: https://img.shields.io/badge/licence-LGPL--3-blue.png
    :target: http://www.gnu.org/licenses/lgpl-3.0-standalone.html
    :alt: License: LGPL-3
.. |badge3| image:: https://img.shields.io/badge/odoo-18.0-875A7B.png
    :target: https://www.odoo.com
    :alt: Odoo 18.0

|badge1| |badge2| |badge3|

**Avance físico** de las tareas de cualquier proyecto de Odoo, con su
evidencia, el avance esperado, la brecha y un recordatorio semanal.

**Índice de contenidos**

.. contents::
   :local:

Características
===============

- Avance físico reportado (0-100), el **esperado** según las fechas (lineal) y
  la **brecha** entre ambos.
- **Reporte con evidencia**: el avance solo se escribe desde el asistente, que
  adjunta el documento o deja constancia de que no lo hubo.
- **Avance vencido** y **recordatorio semanal** (cron) a quien tiene la tarea.
- El hito muestra las fotos de avance de sus tareas para validarlas a la vista.

Puntos de extensión
===================

- ``project.task._progress_reminder_domain()``: qué tareas reciben el
  recordatorio semanal.

Instalación
===========

Depende de ``project`` y ``project_planned_dates``.

Bug Tracker
===========

Los fallos se gestionan en las issues del repositorio. En caso de encontrar un
problema, revisa primero si ya ha sido reportado.

Créditos
========

Autores
~~~~~~~

* Nexus Core

Colaboradores
~~~~~~~~~~~~~

* Iván Candelas <ivan.candelas@gmail.com>

Mantenedores
~~~~~~~~~~~~

Este módulo es mantenido por Nexus Core.

Sitio web: https://nxscore.mx
