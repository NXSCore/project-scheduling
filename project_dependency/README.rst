===================================================
Project Dependencies — Types, Lag and Critical Path
===================================================

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

Vínculos **fin-a-inicio, inicio-a-inicio, fin-a-fin e inicio-a-fin** con
desfase entre tareas de proyecto, y la **ruta crítica** que con ellos se puede
calcular. Es el motor de programación de la suite.

**Índice de contenidos**

.. contents::
   :local:

Características
===============

- Modelo ``project.dependency``: tipo (FS / SS / FF / SF) y desfase, también
  negativo (adelanto) y en días naturales.
- Restricciones de fecha estilo MS Project.
- **Ruta crítica** y holguras, código EDT e hitos.
- Simulación «¿y si…?» del cronograma.
- Chequeo de **salud del cronograma** (14 puntos DCMA) y reporte del
  cronograma.

Por qué existe
==============

Odoo 18 trae ``project.task.depend_on_ids``: un Many2many sin tipo ni desfase,
es decir, un fin-a-inicio implícito. **Sin tipos, la ruta crítica se calcula
mal**: dos actividades que arrancan juntas (inicio-a-inicio) quedan obligadas a
ir en fila, alargan el proyecto en el cálculo y meten en la ruta crítica a
quien no está.

**Convive con** ``depend_on_ids``, **no lo sustituye**. Un fin-a-inicio sin
desfase se refleja en el campo nativo para que el Gantt lo siga dibujando y la
lógica de tarea bloqueada siga funcionando. Los otros tres tipos viven solo
aquí.

Puntos de extensión
===================

- ``project.task._schedule_baseline()``: línea base para la salud del
  cronograma.
- ``project.task._schedule_progress()``: avance de cada tarea en los reportes.

Instalación
===========

Depende de ``project`` y ``project_planned_dates``. Funciona en Community y
Enterprise; el Gantt de Enterprise lo pinta ``project_dependency_gantt``.

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
