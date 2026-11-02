=====================================
Mexican Public Holidays (LFT art. 74)
=====================================

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

Días de **descanso obligatorio** del artículo 74 de la Ley Federal del Trabajo,
**calculados** por año y escritos como ausencias del calendario de trabajo.

**Índice de contenidos**

.. contents::
   :local:

Características
===============

- Año Nuevo, Constitución (1er lunes de febrero), Benito Juárez (3er lunes de
  marzo), Trabajo, Independencia, Revolución (3er lunes de noviembre), Navidad y
  la transmisión del Poder Ejecutivo Federal (1 de diciembre, cada seis años
  desde 2024).
- ``resource.calendar._ensure_mx_holidays(year)`` los deja en el calendario
  (``resource.calendar.leaves``) sin duplicarlos, para que se vean y se puedan
  auditar en Odoo.

Limitaciones
============

Las jornadas electorales (fracción IX) no son deterministas: se cargan a mano.

Instalación
===========

Depende únicamente de ``resource``. Es independiente del resto de la suite:
separado de ``project_gantt`` para que una instalación fuera de México no
herede estos días.

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
