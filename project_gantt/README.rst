=================
Project WBS Gantt
=================

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

Estructura **EDT** y Gantt del cronograma por paquete para cualquier proyecto de
Odoo (Enterprise).

**Índice de contenidos**

.. contents::
   :local:

Características
===============

- **EDT:** paquete raíz, profundidad y grupos de nivel 2 y 3 de cada tarea; el
  código EDT delante del nombre y el Gantt en orden EDT, con las filas de
  resumen marcadas.
- **Gantt por paquete:** agrupa por paquete y nivel, colorea la ruta crítica y
  arranca en escala semana; botón «Gantt por EDT» en el proyecto.
- **«Mostrar subtareas» encendido** por omisión en las pantallas de tareas.

El código EDT y la ruta crítica vienen de ``project_dependency``. Lo propio de
cada dominio (reglas, línea base, entregables) va en un módulo de extensión que
herede de este.

Instalación
===========

Depende de ``project_enterprise`` y ``project_dependency``. Requiere **Odoo
Enterprise**.

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
