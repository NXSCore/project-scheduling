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

---

## Módulos

| Módulo | Qué hace | Depende de | Community | Enterprise |
|---|---|---|:-:|:-:|
| `project_planned_dates` | Fecha de **inicio planeada** de la tarea (`planned_date_begin`), que en Odoo 19 solo trae `project_enterprise`. Rango inicio → fin en formulario y lista | `project` | ✅ | ✅ (no estorba) |
| `project_dependency` | Vínculos **FS / SS / FF / SF** con desfase (también negativo y en días naturales), restricciones de fecha estilo MS Project, **ruta crítica** y holguras, simulación «¿y si…?» y chequeo de salud del cronograma (14 puntos DCMA) | `project`, `project_planned_dates` | ✅ | ✅ |
| `project_planner` | Vista **planificador** estilo MS Project: tabla + barras, EDT, sangría, deshacer, filtros, comparar hasta tres líneas base. OWL propio: **no usa `web_gantt`** | `project_dependency` | ✅ | ✅ |
| `project_planner_report` | Exporta la tabla y el Gantt del planificador a **PDF** paginado (banda de holgura, líneas base) | `project_planner` | ✅ | ✅ |
| `project_msproject` | **Importa y exporta XML de Microsoft Project** (MSPDI) | `project_dependency` | ✅ | ✅ |
| `project_progress` | **Avance físico** por tarea con evidencia, avance esperado contra real y recordatorio semanal | `project`, `project_planned_dates` | ✅ | ✅ |
| `project_dependency_gantt` | Pinta la ruta crítica en el **Gantt de Enterprise** y añade el selector de tipo de vínculo en su conector. `auto_install` | `project_dependency`, `project_enterprise` | — | ✅ |
| `project_gantt` | Niveles **EDT** (paquete, nivel 2 y 3), Gantt agrupado por paquete en orden EDT, «Mostrar subtareas» encendido | `project_dependency`, `project_enterprise` | — | ✅ |
| `project_subschedule` | Subcronograma por etapa del proyecto que se **congela** al cerrar la etapa | `project_gantt` | — | ✅ |
| `resource_mx_holidays` | Días de descanso obligatorio de México (**LFT art. 74**) calculados por año en el calendario de trabajo | `resource` | ✅ | ✅ |
| `project_schedule_demo` | Proyecto de ejemplo: EDT, los cuatro tipos de vínculo, hitos y ruta crítica | `project_dependency`, `project_planner` | ✅ | ✅ |

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

## Instalación

```bash
# addons_path debe incluir este repo (y, en Enterprise, los addons de Enterprise antes que él)
odoo -d <base> -i project_planner,project_planner_report,project_msproject,project_progress
```

Dependencias de Python: ninguna fuera de las de Odoo (el PDF usa `reportlab`, que ya trae Odoo).

## Pruebas

```bash
# Community: sin los addons de Enterprise en el addons_path
odoo -d gantt_ce --with-demo --load-language=es_MX --stop-after-init \
  -i project_planner_report,project_msproject,project_progress,resource_mx_holidays,project_schedule_demo \
  --test-enable --test-tags /project_planned_dates,/project_dependency,/project_planner,/project_planner_report,/project_msproject,/project_progress,/resource_mx_holidays,/project_schedule_demo

# Enterprise: los once módulos
odoo -d gantt_ee --with-demo --load-language=es_MX --stop-after-init -i <todos> --test-enable --test-tags /<cada módulo>
```

En Odoo 18 se omite `--with-demo`: el demo se carga por omisión.

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
