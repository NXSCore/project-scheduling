<!-- /!\ Non OCA Context : Set here the badge of your runbot / runboat instance. -->
[![Pre-commit Status](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://pre-commit.com/)
[![License: LGPL-3](https://img.shields.io/badge/licence-LGPL--3-blue.svg)](http://www.gnu.org/licenses/lgpl-3.0-standalone.html)
[![Odoo](https://img.shields.io/badge/Odoo-19.0-714B67.svg)](https://www.odoo.com)

# Programación de proyectos para Odoo — dependencias, ruta crítica, planificador y Gantt

Suite de módulos para planear proyectos en Odoo como en Microsoft Project o Primavera P6:
vínculos tipados con desfase, ruta crítica, planificador con barras, intercambio de archivos
con MS Project, avance físico y reporte PDF del cronograma. **Funciona en Odoo Community y en
Enterprise.**

Los módulos son genéricos: no dependen de ningún dominio. Lo propio de cada caso (reglas de
importación, líneas base, avance calculado de otra forma) se agrega con módulos de extensión que
redefinen los puntos de extensión documentados en cada modelo.

| Rama | Odoo |
|---|---|
| `19.0` | 19.0 Community / Enterprise |
| `18.0` | 18.0 Community / Enterprise |

<!-- /!\ do not modify below this line -->

<!-- prettier-ignore-start -->

[//]: # (addons)

Este repositorio contiene los siguientes módulos:

| addon | versión | resumen |
|-------|---------|---------|
| [project_planned_dates](project_planned_dates/) | 19.0.1.0.0 | Fecha de **inicio planeada** de la tarea (`planned_date_begin`), que en Odoo 19 solo trae `project_enterprise`. Rango inicio → fin en formulario y lista. |
| [project_dependency](project_dependency/) | 19.0.1.20.0 | Vínculos **FS / SS / FF / SF** con desfase (también negativo y en días naturales), restricciones de fecha estilo MS Project, **ruta crítica** y holguras, simulación «¿y si…?» y chequeo de salud del cronograma (14 puntos DCMA). |
| [project_planner](project_planner/) | 19.0.1.15.0 | Vista **planificador** estilo MS Project: tabla + barras, EDT, sangría, deshacer, filtros, comparar hasta tres líneas base. OWL propio: **no usa `web_gantt`**. |
| [project_planner_report](project_planner_report/) | 19.0.1.7.0 | Exporta la tabla y el Gantt del planificador a **PDF** paginado (banda de holgura, líneas base). |
| [project_msproject](project_msproject/) | 19.0.1.9.0 | **Importa y exporta XML de Microsoft Project** (MSPDI). |
| [project_progress](project_progress/) | 19.0.1.1.0 | **Avance físico** por tarea con evidencia, avance esperado contra real y recordatorio semanal. |
| [project_dependency_gantt](project_dependency_gantt/) | 19.0.1.0.0 | Pinta la ruta crítica en el **Gantt de Enterprise** y añade el selector de tipo de vínculo en su conector. `auto_install`. |
| [project_gantt](project_gantt/) | 19.0.1.0.0 | Niveles **EDT** (paquete, nivel 2 y 3), Gantt agrupado por paquete en orden EDT, «Mostrar subtareas» encendido. |
| [project_subschedule](project_subschedule/) | 19.0.1.0.0 | Subcronograma por etapa del proyecto que se **congela** al cerrar la etapa. |
| [resource_mx_holidays](resource_mx_holidays/) | 19.0.1.0.0 | Días de descanso obligatorio de México (**LFT art. 74**) calculados por año en el calendario de trabajo. |
| [project_schedule_demo](project_schedule_demo/) | 19.0.1.0.0 | Proyecto de ejemplo: EDT, los cuatro tipos de vínculo, hitos y ruta crítica. |

[//]: # (end addons)

<!-- prettier-ignore-end -->

---

## Arquitectura

| Módulo | Depende de | Community | Enterprise |
|---|---|:-:|:-:|
| `project_planned_dates` | `project` | ✅ | ✅ (no estorba) |
| `project_dependency` | `project`, `project_planned_dates` | ✅ | ✅ |
| `project_planner` | `project_dependency` | ✅ | ✅ |
| `project_planner_report` | `project_planner` | ✅ | ✅ |
| `project_msproject` | `project_dependency` | ✅ | ✅ |
| `project_progress` | `project`, `project_planned_dates` | ✅ | ✅ |
| `project_dependency_gantt` | `project_dependency`, `project_enterprise` | — | ✅ |
| `project_gantt` | `project_dependency`, `project_enterprise` | — | ✅ |
| `project_subschedule` | `project_gantt` | — | ✅ |
| `resource_mx_holidays` | `resource` | ✅ | ✅ |
| `project_schedule_demo` | `project_dependency`, `project_planner` | ✅ | ✅ |

```
                    project (Community)
                        │
             project_planned_dates ─────────────┐
                        │                          │
               project_dependency          project_progress
          ┌─────────────┼───────────────┬──────────────────────┐
project_planner  project_msproject  project_dependency_gantt*  project_gantt*
          │                                                              │
project_planner_report                                     project_subschedule*

resource_mx_holidays (independiente)          * requieren Odoo Enterprise (web_gantt)
```

Cada módulo trae su propio `README.rst` con el detalle.

### Qué instalar

- **Community:** `project_planner` (arrastra el motor y las fechas planeadas). Añadir según el
  caso `project_planner_report`, `project_msproject`, `project_progress` y, en México,
  `resource_mx_holidays`.
- **Enterprise:** lo mismo; `project_dependency_gantt` se instala solo. Para el Gantt por EDT,
  `project_gantt` (y `project_subschedule` si se trabaja por etapas).
- **Demo / capacitación:** `project_schedule_demo`.

> **Community → Enterprise sin migración.** `project_planned_dates` declara
> `planned_date_begin` con la misma definición, columna y restricción que `project_enterprise`.
> Si después se instala Enterprise, Odoo funde las dos definiciones y los datos se quedan donde están.

### Puntos de extensión

| Módulo | Método | Para qué |
|---|---|---|
| `project_dependency` | `project.task._schedule_baseline()` | Línea base para la salud del cronograma |
| `project_dependency` | `project.task._schedule_progress()` | Avance de cada tarea en los reportes |
| `project_planner` | `project.task._planner_task_extra()`, `_planner_baselines()` | Datos y líneas base extra en el planificador |
| `project_msproject` | `_check_can_import()`, `_after_import()` | Cuándo se permite importar y qué hacer después |
| `project_progress` | `project.task._progress_reminder_domain()` | Qué tareas reciben el recordatorio semanal |
| `project_subschedule` | `_phase_unlocked()` | Quién puede reabrir un subcronograma congelado |

---

## Requisitos

- Odoo **19.0** (Community o Enterprise; los módulos marcados con * necesitan Enterprise).
- Dependencias de Python: ninguna fuera de las de Odoo (el PDF usa `reportlab`, que ya trae Odoo).

## Instalación

```bash
# addons_path debe incluir este repo (y, en Enterprise, los addons de Enterprise antes que él)
odoo -d <base> -i project_planner,project_planner_report,project_msproject,project_progress
```

## Pruebas

```bash
# Community: sin los addons de Enterprise en el addons_path
odoo -d gantt_ce --with-demo --load-language=es_MX --stop-after-init \
  -i project_planner_report,project_msproject,project_progress,resource_mx_holidays,project_schedule_demo \
  --test-enable --test-tags /project_planned_dates,/project_dependency,/project_planner,/project_planner_report,/project_msproject,/project_progress,/resource_mx_holidays,/project_schedule_demo

# Enterprise: los once módulos
odoo -d gantt_ee --with-demo --load-language=es_MX --stop-after-init -i <todos> --test-enable --test-tags /<cada módulo>
```

Las pruebas de permisos usan `with_user()`; las de idioma activan `es_MX` y comprueban que las
traducciones **cargan**, no solo que el `.po` existe. El CI (`.github/workflows/test.yml`) corre la
matriz Community y, si hay acceso a los addons de Enterprise, también Enterprise.

## Traducciones

Textos visibles en inglés y su traducción en `i18n/es_MX.po`, **exportado desde Odoo**, nunca
escrito a mano:

```bash
# Odoo 19
odoo i18n export -d <db> -l es_MX -o - <módulo> > <módulo>/i18n/es_MX.po
# Odoo 18 (no existe el subcomando `odoo i18n`; el archivo debe ser una ruta real, no /dev/stdout)
odoo --i18n-export=<archivo>.po -l es_MX --modules=<módulo> -d <db> --stop-after-init
```

Al cambiar la **etiqueta** de un campo (`string=`), el export trae la traducción vieja (va atada
al XML ID, no al texto): revisar esas entradas a mano.

## Convenciones

- Identificadores en inglés (módulos `project_*`, modelos `project.*`); comentarios y docstrings
  en español.
- Commits `[TAG] módulo: encabezado` en inglés.
- Licencia **LGPL-3** en todos los módulos.

## Compatibilidad con OCA

Ningún nombre de módulo choca con `OCA/project`, `project-reporting`, `timesheet` ni
`hr-holidays` (16.0 a 19.0).

**No instalar junto con `OCA/project_timeline`.** No choca ningún campo (OCA usa
`planned_date_start`/`planned_date_end`; esta suite, `planned_date_begin`/`date_deadline`, los de
Enterprise), pero la tarea quedaría con **dos juegos de fechas planeadas que no se sincronizan**.

## Lint

`pre-commit run --all-files` debe pasar limpio (ruff y los chequeos de módulo de OCA). Cada
exención de `ruff.toml` lleva su razón.

## Bug Tracker

Los fallos se gestionan en las issues del repositorio. En caso de encontrar un problema, revisa
primero si ya ha sido reportado.

## Créditos

### Autores

- Iván Candelas (Nexus Core)

### Mantenedores

Este repositorio lo mantiene **Nexus Core**.

- Sitio web: https://nxscore.mx

## Licencia

Los módulos de este repositorio se distribuyen bajo licencia
[LGPL-3](http://www.gnu.org/licenses/lgpl-3.0-standalone.html).

Cada módulo es responsable de su propia licencia; consulta el `__manifest__.py`
correspondiente para más detalle.
