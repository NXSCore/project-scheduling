=======================================
Project Dependencies — Enterprise Gantt
=======================================

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

Puente de ``project_dependency`` con el **Gantt de Enterprise**
(``web_gantt`` / ``project_enterprise``).

**Índice de contenidos**

.. contents::
   :local:

Características
===============

- Colorea la **ruta crítica** en el Gantt de tareas y lleva sus campos a la
  barra.
- Botón «Dependencias» en el popover de la barra: tipo y desfase a dos clics.
- Selector de **tipo de vínculo** dentro del conector del Gantt (parche OWL
  sobre ``GanttConnector``).

Detalles técnicos
=================

- Los recursos se cargan en ``web.assets_backend_lazy``, donde ``web_gantt``
  declara sus componentes; en ``web.assets_backend`` el parche se evaluaría
  antes de que exista ``@web_gantt/gantt_connector``.
- Separado de ``project_dependency`` para que el motor instale en Community.

Instalación
===========

Se instala solo (``auto_install``) cuando ``project_dependency`` y
``project_enterprise`` están presentes. Requiere **Odoo Enterprise**; en
Community el cronograma se ve en el planificador de ``project_planner``.

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
