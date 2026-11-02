===============
Project Planner
===============

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

Vista **planificador** al estilo de Microsoft Project para las tareas de
cualquier proyecto de Odoo, en Community y Enterprise. OWL propio: **no usa**
``web_gantt``.

**Índice de contenidos**

.. contents::
   :local:

Características
===============

- Tabla (EDT, nombre, duración, inicio, fin, predecesoras) y línea de tiempo en
  un solo ``<canvas>``: el desplazamiento cuesta lo mismo con 50 tareas que con
  5,000.
- Árbol plegable, tareas resumen, hitos de 0 días, ruta crítica, vínculos de
  los 4 tipos con desfase y escalas de día a año.
- Edición: arrastrar barras, asas de vínculo, celdas, predecesoras escritas
  como en MS Project, menú contextual, insertar / eliminar / sangría / subir /
  bajar, deshacer.
- Filtros y comparación de hasta tres líneas base.
- Tipo de vista ``planner`` en el selector de vistas (también en la app
  Proyectos estándar) y acción cliente a pantalla completa.
- Botón **Planificador** en la ficha del proyecto: abre el planificador a
  pantalla completa con las tareas de ese proyecto. Funciona en Community, sin
  ``web_gantt``.

Uso
===

- **Desde las tareas del proyecto:** *Proyecto* → tarjeta del proyecto →
  vista **Planificador** en el selector de vistas.
- **Desde la ficha del proyecto:** botón inteligente **Planificador**.

Puntos de extensión
===================

- ``project.task._planner_task_extra()``: datos extra por tarea (línea base,
  avance físico, un botón en otra ficha…).
- ``project.task._planner_baselines()``: líneas base que se pueden comparar.

Instalación
===========

Depende de ``project``, ``project_planned_dates`` y ``project_dependency``.

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
