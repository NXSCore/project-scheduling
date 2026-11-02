==================
Stage Subschedules
==================

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

**Subcronograma por etapa** del proyecto dentro del cronograma principal, que
se **congela** cuando el proyecto deja esa etapa.

**Índice de contenidos**

.. contents::
   :local:

Características
===============

- Una tarea agrupadora marcada con la etapa (``phase_id``) y todas sus
  subtareas, que la heredan (``effective_phase_id``); una subtarea no declara
  otra etapa.
- Botón «Subcronograma de la etapa» (el Gantt EDT de ``project_gantt`` con solo
  esa rama) y «Agrupar por etapa».
- Cuando el proyecto pasa a una etapa posterior, el subcronograma de la
  anterior se congela: nombre, fechas, dependencias, padre, altas y bajas. El
  sistema (``sudo``) no se frena.

Por qué existe
==============

Odoo trae etapas de proyecto (``project.project.stage``) y tareas con
subtareas, pero sin liga entre ellas. Este módulo permite ver y proteger el
cronograma de cada etapa **sin partir** el del proyecto: la ruta crítica y las
dependencias entre etapas siguen enteras. Sirve a cualquier proyecto por etapas
(consultoría, construcción, implantación).

Puntos de extensión
===================

- ``_phase_unlocked()``: quién puede reabrir un subcronograma congelado. Aquí,
  nadie; un módulo de extensión lo redefine (p. ej., con una solicitud de
  cambio aprobada).

Instalación
===========

Depende de ``project_gantt``. Requiere **Odoo Enterprise**.

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
