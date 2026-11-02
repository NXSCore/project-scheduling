=================================
Project Planned Dates (Community)
=================================

.. |badge1| image:: https://img.shields.io/badge/maturity-Beta-yellow.png
    :target: https://odoo-community.org/page/development-status
    :alt: Beta
.. |badge2| image:: https://img.shields.io/badge/licence-LGPL--3-blue.png
    :target: http://www.gnu.org/licenses/lgpl-3.0-standalone.html
    :alt: License: LGPL-3
.. |badge3| image:: https://img.shields.io/badge/odoo-19.0-875A7B.png
    :target: https://www.odoo.com
    :alt: Odoo 19.0

|badge1| |badge2| |badge3|

Fecha de **inicio planeada** en las tareas de proyecto sin Odoo Enterprise, para
que los módulos de programación funcionen en Community.

**Índice de contenidos**

.. contents::
   :local:

Características
===============

- Declara ``project.task.planned_date_begin`` con la **misma** definición que
  ``project_enterprise`` (nombre, tipo, columna y restricción
  ``_planned_dates_check``).
- **En Community** muestra el rango inicio → fin en el formulario y la lista.
- **En Enterprise** no estorba: Odoo funde las dos definiciones en una sola
  columna y una sola restricción.

Por qué existe
==============

En Odoo 19 la fecha de inicio planeada la declara ``project_enterprise``;
Community solo trae ``date_deadline``. Sin inicio no hay duración, y sin
duración no hay dependencias con desfase, ruta crítica, planificador ni
intercambio con Microsoft Project.

Instalar Enterprise después sobre una base Community **conserva los datos**: no
hay migración.

No trae la vista Gantt (es de ``web_gantt``, Enterprise). En Community el Gantt
es el planificador de ``project_planner``.

Instalación
===========

Depende únicamente de ``project``. Se instala automáticamente como dependencia
de los demás módulos de la suite.

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
