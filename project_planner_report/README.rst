==========================
Project Planner PDF Report
==========================

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

El **Informe** del planificador: exporta la tabla de tareas y el Gantt de
``project_planner`` a un **PDF** vectorial paginado.

**Índice de contenidos**

.. contents::
   :local:

Características
===============

Botón «Informe» en el planificador (vista y pantalla completa) que abre un
asistente con las opciones del documento:

- Empresa, autor, papel A4 / A3 / Carta / Tabloide, orientación y tamaño de
  letra.
- Colores por ruta crítica, línea de estado, páginas del cronograma, ajustar al
  papel, seguir la vista y encabezado repetido.
- Nombres en barras, avance, línea base, banda de holgura, dependencias, solo
  días laborables, fines de semana y leyenda.

El PDF lleva tabla + Gantt con numeración «n / N».

Detalles técnicos
=================

- Dibuja con ``reportlab`` (dependencia de Odoo); no usa wkhtmltopdf.
- Lee las tareas con los permisos de quien imprime.
- Módulo aparte porque es **opcional**: el planificador no lo necesita.

Instalación
===========

Depende únicamente de ``project_planner``.

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
