====================================
Project - Microsoft Project Exchange
====================================

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

**Importa y exporta** cronogramas en XML de Microsoft Project (formato MSPDI)
para cualquier proyecto de Odoo.

**Índice de contenidos**

.. contents::
   :local:

Características
===============

- Importa el XML de MS Project (*Archivo → Guardar como → XML*): jerarquía y
  orden EDT, fechas en la zona horaria del usuario, hitos de 0 días,
  responsables por correo o nombre, y vínculos con tipo (FS / SS / FF / SF) y
  desfase en ``project.dependency``.
- **Reimportar actualiza** por ``<UID>``: no duplica ni borra.
- Botón «Exportar a MS Project» con el mismo formato; lo exportado se reimporta
  sin perder nada (prueba de ida y vuelta).

Seguridad
=========

El XML se lee en Python con ``lxml`` sin resolver entidades ni acceder a la red
(protección contra XXE). Sin dependencias nuevas.

Puntos de extensión
===================

- ``_check_can_import()``: cuándo se permite importar.
- ``_after_import()``: qué hacer después (p. ej., a quién avisar).

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
