=================================
Project Scheduling — Demo Project
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

Proyecto de ejemplo (un edificio de oficinas) para enseñar la suite de
programación en una demo o capacitación, en Community o Enterprise.

**Índice de contenidos**

.. contents::
   :local:

Características
===============

- Paquetes y subtareas (EDT de dos niveles).
- Los cuatro tipos de vínculo: fin-inicio, inicio-inicio, fin-fin e
  inicio-fin, con desfase positivo, adelanto (desfase negativo) y desfase en
  días naturales.
- Dos hitos de cero días y una ruta crítica que se ve en el planificador.

Las fechas se calculan a partir del día de instalación, así que el proyecto
siempre está «vivo».

Instalación
===========

Depende de ``project_dependency`` y ``project_planner``. Es **dato de ejemplo**:
no se instala en producción.

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
