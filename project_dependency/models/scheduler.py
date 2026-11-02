# -*- coding: utf-8 -*-
"""El motor de programación — calcula las fechas, no solo las mide.

Este motor CALCULA las fechas, como el botón «Calcular» de MS Project u Open
Planner Studio, y también MIDE la ruta crítica (`slack`, al final):

- **Calendario laboral** del proyecto, a nivel de MINUTO:
  sus turnos por día de la semana (p. ej. 9–13 y 15–19) y sus feriados. Así
  calcula MS Project; a nivel de día las fechas se corren ±1 día.
- **Pasada hacia adelante** con los cuatro tipos de vínculo y su desfase, en días
  laborables o naturales (`lag_elapsed`).
- **Restricciones de fecha** de MS Project: SNET, MSO, FNET y MFO mueven la
  tarea; SNLT y FNLT solo avisan si se incumplen; ALAP la lleva a su fecha más
  tardía con una pasada hacia atrás.
- Una tarea **sin predecesoras** queda anclada en su inicio actual: es lo que
  hace MS Project cuando alguien escribe una fecha de inicio (la convierte en
  «No comenzar antes del»). Sin esto, todo lo que no tiene predecesora se iría
  al inicio del proyecto.
- Los **resúmenes** salen de sus hijas. Un vínculo con un resumen se expande a
  sus subtareas, como en MS Project.
- La **duración guardada** (`duration_days`) manda; solo si falta se deduce
  de las fechas.

No escribe nada por sí mismo: devuelve los cambios. Quien lo llama decide si
los muestra (vista previa) o los aplica.
"""
from bisect import bisect_left, bisect_right
from datetime import datetime, time, timedelta

import pytz

#: Las restricciones de MS Project, con sus códigos MSPDI (`<ConstraintType>`).
CONSTRAINT_TYPES = [
    ("asap", "As Soon As Possible"),
    ("alap", "As Late As Possible"),
    ("snet", "Start No Earlier Than"),
    ("snlt", "Start No Later Than"),
    ("fnet", "Finish No Earlier Than"),
    ("fnlt", "Finish No Later Than"),
    ("mso", "Must Start On"),
    ("mfo", "Must Finish On"),
]
MSPDI_CONSTRAINTS = {0: "asap", 1: "alap", 2: "mso", 3: "mfo", 4: "snet", 5: "snlt", 6: "fnet", 7: "fnlt"}

#: Tope de búsqueda de un día laborable: un calendario sin días laborables no
#: debe colgar el servidor.
MAX_SEARCH_DAYS = 3660


class WorkTime:
    """Tiempo de trabajo a nivel de MINUTO, como MS Project.

    Por día de la semana, sus turnos (p. ej. 9–13 y 15–19); los feriados son
    días enteros. Todo en hora LOCAL del calendario (datetime sin zona). Un
    inicio se ajusta HACIA ADELANTE al siguiente minuto laborable; un fin, HACIA
    ATRÁS al final del turno anterior: un fin a las 09:00 es «el día anterior a
    las 19:00», que es lo que MS Project entiende.
    """

    def __init__(self, turnos, holidays):
        self.turnos = {d: sorted(v) for d, v in turnos.items() if v} or {
            d: [(8 * 60, 12 * 60), (13 * 60, 17 * 60)] for d in range(5)}
        self.holidays = set(holidays)
        # Rendimiento : la ruta crítica llama a `between` ~12 mil
        # veces sobre tramos de un año, y recorrerlo día por día eran 4.4 millones de `intervals`. Los
        # turnos de una fecha no cambian, así que se guardan; y los días COMPLETOS de un tramo se cuentan
        # con aritmética (minutos por día de la semana, menos los feriados), sin recorrerlos.
        self._intervals = {}
        self._day_minutes = [sum(b - a for a, b in self.turnos.get(w, [])) for w in range(7)]
        self._sorted_holidays = sorted(self.holidays)

    def intervals(self, d):
        hit = self._intervals.get(d)
        if hit is None:
            if d in self.holidays:
                hit = []
            else:
                base = datetime.combine(d, time())
                hit = [(base + timedelta(minutes=a), base + timedelta(minutes=b))
                       for a, b in self.turnos.get(d.weekday(), [])]
            self._intervals[d] = hit
        return hit

    def _full_days_minutes(self, desde, hasta):
        """Minutos laborables de los días COMPLETOS de `desde` a `hasta`, ambos incluidos."""
        n = (hasta - desde).days + 1
        if n <= 0:
            return 0.0
        semanas, resto = divmod(n, 7)
        w0 = desde.weekday()
        total = semanas * sum(self._day_minutes) + sum(self._day_minutes[(w0 + i) % 7] for i in range(resto))
        feriados = self._sorted_holidays
        for f in feriados[bisect_left(feriados, desde):bisect_right(feriados, hasta)]:
            total -= self._day_minutes[f.weekday()]
        return float(total)

    def is_work_day(self, d):
        return bool(self.intervals(d))

    def next_start(self, dt):
        d = dt.date()
        for _ in range(MAX_SEARCH_DAYS):
            for a, b in self.intervals(d):
                if dt < b:
                    return max(dt, a)
            d += timedelta(days=1)
            dt = datetime.combine(d, time())
        return dt

    def prev_end(self, dt):
        d = dt.date()
        for _ in range(MAX_SEARCH_DAYS):
            for a, b in reversed(self.intervals(d)):
                if dt > a:
                    return min(dt, b)
            d -= timedelta(days=1)
            dt = datetime.combine(d, time.max)
        return dt

    def add(self, dt, minutos):
        """`minutos` de trabajo desde `dt`; devuelve un punto de FIN."""
        if minutos <= 0:
            return dt
        dt = self.next_start(dt)
        resto = minutos
        d = dt.date()
        for _ in range(MAX_SEARCH_DAYS):
            for a, b in self.intervals(d):
                if b <= dt:
                    continue
                desde = max(a, dt)
                cabe = (b - desde).total_seconds() / 60
                if resto <= cabe:
                    return desde + timedelta(minutes=resto)
                resto -= cabe
            d += timedelta(days=1)
            dt = datetime.combine(d, time())
        return dt

    def sub(self, dt, minutos):
        """`minutos` de trabajo hacia atrás desde `dt`; devuelve un INICIO."""
        if minutos <= 0:
            return dt
        dt = self.prev_end(dt)
        resto = minutos
        d = dt.date()
        for _ in range(MAX_SEARCH_DAYS):
            for a, b in reversed(self.intervals(d)):
                if a >= dt:
                    continue
                hasta = min(b, dt)
                cabe = (hasta - a).total_seconds() / 60
                if resto <= cabe:
                    return hasta - timedelta(minutes=resto)
                resto -= cabe
            d -= timedelta(days=1)
            dt = datetime.combine(d, time.max)
        return dt

    def between(self, ini, fin):
        """Minutos de trabajo entre dos instantes."""
        if fin <= ini:
            return 0.0

        def parcial(d):
            total = 0.0
            for a, b in self.intervals(d):
                x, y = max(a, ini), min(b, fin)
                if y > x:
                    total += (y - x).total_seconds() / 60
            return total

        d0, d1 = ini.date(), fin.date()
        if d0 == d1:
            return parcial(d0)
        return parcial(d0) + self._full_days_minutes(d0 + timedelta(days=1), d1 - timedelta(days=1)) + parcial(d1)

    def shift(self, dt, minutos, elapsed):
        """El desfase de un vínculo: minutos laborables, o naturales («edías»)."""
        if not minutos:
            return dt
        if elapsed:
            return dt + timedelta(minutes=minutos)
        return self.add(dt, minutos) if minutos > 0 else self.sub(dt, -minutos)


def holiday_leaves(cal):
    """Los feriados que Odoo aplica a `cal`, con SU regla
    (`resource.calendar._leave_intervals_batch`): ausencias sin recurso, de
    tipo «ausencia», del calendario O SIN CALENDARIO, de su compañía o sin
    compañía. No basta con `global_leave_ids`: un día festivo dado de
    alta sin «Horario de trabajo» Odoo lo aplica a todos los calendarios de
    la empresa."""
    dominio = [("resource_id", "=", False), ("time_type", "=", "leave"), ("calendar_id", "in", [False, cal.id])]
    if cal.company_id:
        dominio.append(("company_id", "in", [False, cal.company_id.id]))
    return cal.env["resource.calendar.leaves"].search(dominio, order="date_from")


def calendar_for(cal, desde, hasta):
    """El calendario laboral `cal` (resource.calendar): sus turnos por día de la
    semana y sus feriados globales del periodo. Sin calendario: lunes a viernes
    de 8 a 12 y de 13 a 17."""
    if not cal:
        return WorkTime({}, set()), "UTC"
    turnos = {}
    for a in cal.attendance_ids:
        if a.display_type or a.day_period == "lunch":
            continue
        turnos.setdefault(int(a.dayofweek), []).append((round(a.hour_from * 60), round(a.hour_to * 60)))
    tz = pytz.timezone(cal.tz or "UTC")
    feriados = set()
    for leave in holiday_leaves(cal):
        inicio = pytz.utc.localize(leave.date_from).astimezone(tz).date()
        fin = pytz.utc.localize(leave.date_to).astimezone(tz).date()
        if fin < desde or inicio > hasta:
            continue
        d = inicio
        while d <= fin:
            feriados.add(d)
            d += timedelta(days=1)
    return WorkTime(turnos, feriados), cal.tz or "UTC"


def working_days(cal, tz_name, start, end, milestone, minutes_per_day=480):
    """Duración laborable de una tarea según sus fechas, en días de
    `minutes_per_day` (el «minutos por día» de MS Project)."""
    if milestone or not (start and end):
        return 0.0
    tz = pytz.timezone(tz_name)
    s = pytz.utc.localize(start).astimezone(tz).replace(tzinfo=None)
    e = pytz.utc.localize(end).astimezone(tz).replace(tzinfo=None)
    return round(max(cal.between(s, e), 1) / (minutes_per_day or 480), 2)


def schedule(tasks, links, cal, tz_name, minutes_per_day=480, project=None, drivers=None, edges=None):
    """Calcula las fechas a nivel de minuto. `tasks`: id → {start, end (UTC
    naive), milestone, summary, parent, constraint, constraint_date, duration
    (días)}; `links`: {pred, succ, type, lag (días), elapsed}. Devuelve
    (nuevas, conflictos, omitidos); nuevas = id → (inicio, fin) UTC naive.

    `manual` en una tarea = programada MANUALMENTE (MS Project no la
    mueve; sí condiciona a sus vecinas). `project` = {from_start, start,
    finish (UTC naive)}: un proyecto programado DESDE EL FIN (`ScheduleFromStart
    = 0` en MSPDI) se calcula hacia atrás desde su fecha de fin.

    Si se
    pasa `drivers` (un dict), el motor anota en él QUÉ fijó las fechas de cada
    tarea, tal como lo decidió el cálculo y no deducido después: id → {kind,
    preds, links}. `kind` es uno de `DRIVER_KINDS`; con `predecessor`, `preds`
    son las predecesoras (tal como se capturaron: un resumen y no sus hojas) y
    `links` los pares (predecesora, sucesora) que mandan.

    `project` admite además `manual_as_auto` y `early_anchor` (UTC
    naive), que solo usa `slack` en la pasada TEMPRANA de un proyecto
    programado desde el fin: las manuales se calculan como automáticas y las
    que no tienen predecesoras arrancan en `early_anchor` (el inicio del
    proyecto). Ver `slack`.

    Si se pasa `edges` (una lista), el motor la llena con los vínculos
    YA EXPANDIDOS a hojas (los que van hacia o desde un resumen, como los
    calcula): {pred, succ, type, lagmin, elapsed}. La holgura libre (`slack`)
    los necesita para medir cada vínculo con las mismas reglas del cálculo.
    """
    tz = pytz.timezone(tz_name)
    mpd = minutes_per_day or 480

    def local(dt):
        return pytz.utc.localize(dt).astimezone(tz).replace(tzinfo=None)

    def utc(dt):
        return tz.localize(dt).astimezone(pytz.utc).replace(tzinfo=None)

    info = {}
    for i, t in tasks.items():
        if t["summary"] or not (t["start"] and t["end"]):
            continue
        s_, e_ = local(t["start"]), local(t["end"])
        if t["milestone"]:
            dur = 0
        elif t.get("duration"):
            # La duración GUARDADA manda (como en MS Project), en minutos.
            dur = round(t["duration"] * mpd)
        else:
            dur = max(1, round(cal.between(s_, e_)))
        info[i] = {"dur": dur, "anchor": s_ if dur == 0 else cal.next_start(s_),
                   "manual": bool(t.get("manual")), "orig": (s_, e_)}

    # Vínculos con RESÚMENES, como MS Project: hacia un resumen = hacia cada
    # subtarea; desde un resumen = su inicio (min) o su fin (max).
    hijos = {}
    for i, t in tasks.items():
        if t["parent"] in tasks:
            hijos.setdefault(t["parent"], []).append(i)

    def hojas_de(i):
        if i in info:
            return [i]
        out = []
        for h in hijos.get(i, ()):
            out += hojas_de(h)
        return out

    entrantes, salientes, omitidos = {}, {}, []
    for k, l in enumerate(links):
        if l["pred"] not in tasks or l["succ"] not in tasks:
            continue
        preds, succs = hojas_de(l["pred"]), hojas_de(l["succ"])
        if not preds or not succs or set(preds) & set(succs):
            omitidos.append(l)
            continue
        lado_inicio = l["type"] in ("ss", "sf")
        for p in preds:
            for s2 in succs:
                e = {**l, "pred": p, "succ": s2, "group": (k, s2) if len(preds) > 1 else None,
                     "origin": (l["pred"], l["succ"]),
                     "agg": min if lado_inicio else max, "lagmin": (l["lag"] or 0.0) * (1440 if l["elapsed"] else mpd)}
                entrantes.setdefault(s2, []).append(e)
                salientes.setdefault(p, []).append(e)

    if edges is not None:
        edges.extend(e for lista in entrantes.values() for e in lista)
    grado = {i: len(entrantes.get(i, ())) for i in info}
    cola = [i for i, g in grado.items() if g == 0]
    orden = []
    while cola:
        n = cola.pop()
        orden.append(n)
        for l in salientes.get(n, ()):
            grado[l["succ"]] -= 1
            if grado[l["succ"]] == 0:
                cola.append(l["succ"])
    orden += [i for i in info if i not in set(orden)]

    def fin_de(es_, dur):
        return es_ if dur == 0 else cal.add(es_, dur)

    def ini_desde_fin(ef_, dur):
        return ef_ if dur == 0 else cal.sub(ef_, dur)

    def arranque(dt, dur):
        # Una tarea con duración arranca en el siguiente minuto laborable; un
        # hito se queda en el instante (p. ej. el fin de su predecesora).
        return dt if dur == 0 else cal.next_start(dt)

    es, ef, conflictos = {}, {}, []
    desde_fin = bool(project and project.get("from_start") is False and project.get("finish"))
    manual_auto = bool((project or {}).get("manual_as_auto"))
    ancla_manual = local(project["early_anchor"]) if (project or {}).get("early_anchor") else None
    honrar = (project or {}).get("honor_constraints", True)
    motivo = {}
    for n in orden:
        dur = info[n]["dur"]
        t = tasks[n]
        if info[n]["manual"] and not manual_auto:
            es[n], ef[n] = info[n]["orig"]
            motivo[n] = {"kind": "manual"}
            continue
        # Lo que YA OCURRIÓ no se reprograma (MS Project): una tarea terminada
        # queda en sus fechas reales; una en curso conserva su inicio real y su
        # fin se calcula desde ahí.
        real_ini, real_fin = t.get("actual_start"), t.get("actual_finish")
        if real_ini and real_fin:
            es[n], ef[n] = local(real_ini), local(real_fin)
            motivo[n] = {"kind": "actual"}
            continue
        if real_ini:
            es[n] = local(real_ini)
            ef[n] = fin_de(es[n], dur)
            motivo[n] = {"kind": "progress"}
            continue
        cands, grupos = [], {}
        for l in entrantes.get(n, ()):
            p = l["pred"]
            if p not in es:
                # La predecesora no se ha calculado porque el grafo
                # expandido (vínculos con resúmenes) cierra un CICLO. No se
                # truena: el vínculo se omite y se reporta.
                omitidos.append(l)
                continue
            lag, el = l["lagmin"], l["elapsed"]
            if l["type"] == "fs":
                c = arranque(cal.shift(ef[p], lag, el), dur)
            elif l["type"] == "ss":
                c = arranque(cal.shift(es[p], lag, el), dur)
            elif l["type"] == "ff":
                c = ini_desde_fin(cal.shift(ef[p], lag, el), dur)
            else:  # sf
                c = ini_desde_fin(cal.shift(es[p], lag, el), dur)
            if l.get("group"):
                grupos.setdefault(l["group"], (l["agg"], [], l["origin"]))[1].append(c)
            else:
                cands.append((c, l["origin"]))
        cands += [(agg(vals), origen) for agg, vals, origen in grupos.values()]
        inicio = max(c for c, _o in cands) if cands else info[n]["anchor"]
        if info[n]["manual"]:
            # Solo en la pasada TEMPRANA de un proyecto programado desde el
            # fin (`manual_as_auto`). La manual se calcula como automática —sin
            # restricciones, y sin predecesoras desde el inicio del proyecto— y su
            # inicio temprano es el MENOR entre eso y su posición, como lo guarda
            # MS Project.
            if not cands and ancla_manual:
                inicio = arranque(ancla_manual, dur)
            inicio = min(inicio, info[n]["orig"][0])
            es[n], ef[n] = inicio, fin_de(inicio, dur)
            motivo[n] = {"kind": "manual"}
            continue
        if cands:
            # Las que empatan con el máximo mandan JUNTAS: si varias
            # predecesoras fijan el inicio, se dice cuántas.
            mandan = sorted({o for c, o in cands if c == inicio})
            motivo[n] = {"kind": "predecessor", "preds": sorted({o[0] for o in mandan}), "links": mandan}
        else:
            motivo[n] = {"kind": "own_start"}
        cands = [c for c, _o in cands]
        tipo, c = t["constraint"], t["constraint_date"]
        cl = local(c) if c else None
        previo = inicio
        if cl and tipo == "snet":
            inicio = max(inicio, arranque(cl, dur))
        elif cl and tipo == "fnet":
            inicio = max(inicio, ini_desde_fin(cl, dur))
        elif cl and tipo in ("mso", "mfo"):
            forzado = arranque(cl, dur) if tipo == "mso" else ini_desde_fin(cl, dur)
            if cands and max(cands) > forzado:
                conflictos.append({"task": n, "constraint": tipo, "date": cl.date()})
            inicio = forzado
        # SNLT / FNLT: si el proyecto tiene «las tareas siempre respetan sus
        # restricciones» (`honor_constraints`, valor por omisión de MS
        # Project), el límite manda sobre los vínculos; si no, ganan los
        # vínculos. En los dos casos se reporta el conflicto.
        if cl and tipo == "snlt" and inicio > arranque(cl, dur):
            conflictos.append({"task": n, "constraint": tipo, "date": cl.date()})
            if honrar:
                inicio = arranque(cl, dur)
        elif cl and tipo == "fnlt" and fin_de(inicio, dur) > (cl if dur == 0 else cal.prev_end(cl)):
            conflictos.append({"task": n, "constraint": tipo, "date": cl.date()})
            if honrar:
                inicio = ini_desde_fin(cl, dur)
        if inicio != previo or (cl and tipo in ("mso", "mfo")):
            motivo[n] = {"kind": "constraint", "constraint": tipo}
        es[n] = inicio
        ef[n] = fin_de(inicio, dur)

    # ALAP: lo más tarde posible sin mover a sus sucesoras ni el fin del proyecto.
    if desde_fin:
        # Proyecto programado DESDE EL FIN (MSPDI `ScheduleFromStart = 0`):
        # MS Project pone TODA tarea automática en sus fechas TARDÍAS, hacia
        # atrás desde sus sucesoras y la fecha de fin del proyecto; las
        # predecesoras no la empujan. MS Project guarda
        # EarlyStart = lo que da la pasada hacia adelante, pero
        # Start = LateStart (con holgura negativa).
        fin_proyecto = local(project["finish"])
        for n in reversed(orden):
            t = tasks[n]
            if info[n]["manual"] or t.get("actual_start"):
                continue
            dur = info[n]["dur"]
            limites = []
            for l in salientes.get(n, ()):
                s2 = l["succ"]
                if s2 not in es:
                    continue
                atras = -l["lagmin"]
                if l["type"] == "fs":
                    limites.append(cal.shift(es[s2], atras, l["elapsed"]))
                elif l["type"] == "ss":
                    limites.append(fin_de(cal.shift(es[s2], atras, l["elapsed"]), dur))
                elif l["type"] == "ff":
                    limites.append(cal.shift(ef[s2], atras, l["elapsed"]))
                else:
                    limites.append(fin_de(cal.shift(ef[s2], atras, l["elapsed"]), dur))
            # El fin del proyecto acota a TODAS, no solo a las que no
            # tienen sucesoras: con un inicio-a-inicio, la sucesora no limita el
            # fin de su predecesora y esta se saldría del proyecto.
            lf = min(limites + [fin_proyecto])
            # La FECHA LÍMITE de MS Project (`Deadline`) no empuja la
            # tarea hacia adelante, pero acota su fin TARDÍO: es lo que da holgura negativa a una
            # tarea con fecha límite inalcanzable.
            if t.get("deadline"):
                lf = min(lf, local(t["deadline"]))
            # Hacia atrás, también un hito se alinea al CIERRE del turno
            # anterior (19:00 y no 09:00 del día siguiente), como MS Project.
            lf = cal.prev_end(lf)
            ls = ini_desde_fin(lf, dur)
            tipo, c = t["constraint"], t["constraint_date"]
            cl = local(c) if c else None
            if cl and tipo in ("mso", "mfo"):
                ls = arranque(cl, dur) if tipo == "mso" else ini_desde_fin(cl, dur)
            elif cl and tipo in ("snet", "fnet"):
                minimo = arranque(cl, dur) if tipo == "snet" else ini_desde_fin(cl, dur)
                if ls < minimo:
                    conflictos.append({"task": n, "constraint": tipo, "date": cl.date()})
                    # «terminar no antes de» se impone aunque el proyecto no
                    # respete restricciones; «comenzar no antes de», solo si las
                    # respeta (así lo calcula MS Project).
                    if honrar or tipo == "fnet":
                        ls = minimo
            elif cl and tipo in ("snlt", "fnlt"):
                maximo = arranque(cl, dur) if tipo == "snlt" else ini_desde_fin(cl, dur)
                ls = min(ls, maximo)
            motivo[n] = ({"kind": "constraint", "constraint": tipo} if cl and tipo not in ("asap", "alap")
                         else {"kind": "from_finish"})
            es[n], ef[n] = ls, fin_de(ls, dur)

    # ALAP en un proyecto desde el INICIO: lo más tarde posible sin mover a sus
    # sucesoras ni el fin del proyecto.
    if not desde_fin and any(tasks[n]["constraint"] == "alap" for n in info):
        fin_proyecto = max(ef.values())
        for n in reversed(orden):
            if tasks[n]["constraint"] != "alap" or info[n]["manual"] or tasks[n].get("actual_start"):
                continue
            dur = info[n]["dur"]
            limites = [fin_proyecto]
            for l in salientes.get(n, ()):
                s2 = l["succ"]
                if s2 not in es:
                    continue
                atras = -l["lagmin"]
                if l["type"] == "fs":
                    limites.append(cal.shift(es[s2], atras, l["elapsed"]))
                elif l["type"] == "ss":
                    limites.append(fin_de(cal.shift(es[s2], atras, l["elapsed"]), dur))
                elif l["type"] == "ff":
                    limites.append(cal.shift(ef[s2], atras, l["elapsed"]))
                else:
                    limites.append(fin_de(cal.shift(ef[s2], atras, l["elapsed"]), dur))
            lf = min(limites) if dur == 0 else cal.prev_end(min(limites))
            if lf > ef[n]:
                ef[n] = lf
                es[n] = ini_desde_fin(lf, dur)
                motivo[n] = {"kind": "alap"}

    nuevas = {n: (utc(es[n]), utc(ef[n])) for n in info}
    if drivers is not None:
        drivers.update(motivo)

    def rollup(i):
        if i in nuevas:
            return nuevas[i]
        rangos = [r for r in (rollup(h) for h in hijos.get(i, ())) if r]
        if not rangos:
            return None
        nuevas[i] = (min(r[0] for r in rangos), max(r[1] for r in rangos))
        return nuevas[i]

    for i, t in tasks.items():
        if t["summary"]:
            rollup(i)
    return nuevas, conflictos, omitidos


def slack(tasks, links, cal, tz_name, minutes_per_day=480, project=None):
    """Holgura total y ruta crítica como MS Project, en minutos LABORABLES.

    Reutiliza el motor completo dos veces: las fechas TEMPRANAS son la pasada
    hacia adelante (el proyecto «desde el inicio») y las TARDÍAS, el mismo
    motor «desde el fin» con el fin del proyecto (el de la pasada temprana, o
    la fecha de fin si el proyecto se programa desde el fin). Así las dos
    pasadas respetan exactamente las mismas reglas: vínculos con resúmenes,
    restricciones, manuales, fechas reales y fechas límite (`deadline`).

    - Hoja: holgura = min(inicio tardío − inicio temprano, fin tardío − fin
      temprano); crítica si es ≤ 0 (la NEGATIVA también: una fecha límite o una
      restricción que ya no se alcanza) y no está terminada.
    - Resumen: sus fechas salen de sus hojas; su holgura es fin tardío − fin
      temprano, salvo que el inicio dé negativo; crítico si la holgura es ≤ 0
      Y alguna hija lo es (MS Project no marca un resumen solo por sus fechas).

    Holgura LIBRE (MS Project «Free Slack»): lo que
    una tarea puede retrasarse sin que NINGUNA sucesora tenga que empezar (o
    terminar) más tarde. Por vínculo, en minutos laborables: FS = inicio
    temprano de la sucesora − (fin temprano + desfase); SS = inicio temprano −
    (inicio temprano + desfase); FF y SF igual contra el FIN temprano de la
    sucesora. Es el mínimo de sus vínculos; sin sucesoras, fin tardío − fin
    temprano (hasta el fin del proyecto). Nunca pasa de la total ni baja de 0:
    con la total negativa (una fecha límite o restricción que ya no se
    alcanza) la libre es 0. Así lo guarda MS Project en
    `FreeSlack`. Terminada: 0. Un resumen no la lleva.

    Proyecto programado DESDE EL FIN, dos reglas tomadas de
    MS Project (TotalSlack, FreeSlack y Critical):

    - En la pasada TEMPRANA, una tarea MANUAL se calcula como automática (sus
      restricciones no cuentan y, sin predecesoras, arranca en el inicio del
      proyecto) y su inicio temprano es el MENOR entre eso y su posición. Su
      posición fija solo cuenta para las fechas tardías.
    - En la pasada TARDÍA, «terminar no antes de» se impone aunque el proyecto
      no respete restricciones; «comenzar no antes de», no (queda la holgura
      negativa). Afecta también dónde «Calcular» pone esas tareas.

    Diferencias conocidas con MS Project: un resumen que contiene un resumen
    MANUAL, manuales con «comenzar no antes de» y sucesoras de una manual en
    curso. En un proyecto desde el INICIO las manuales
    siguen fijas en las dos pasadas: no hay archivo de MS Project que diga
    otra cosa.

    Devuelve id → {slack, free (minutos; `free` solo en hojas), critical, ef,
    lf (UTC naive)}.
    """
    import copy

    tz = pytz.timezone(tz_name)
    proyecto = dict(project or {})
    aristas = []
    temprana = {**proyecto, "from_start": True}
    if proyecto.get("from_start") is False and proyecto.get("finish"):
        inicios = [t["start"] for t in tasks.values() if t["start"] and not t["summary"]]
        temprana.update(early_anchor=min(inicios) if inicios else None, manual_as_auto=True)
    tempranas, _c, _o = schedule(copy.deepcopy(tasks), links, cal, tz_name, minutes_per_day,
                                 project=temprana, edges=aristas)
    if not tempranas:
        return {}
    if proyecto.get("from_start") is False and proyecto.get("finish"):
        fin = proyecto["finish"]
    else:
        fin = max(e for _s, e in tempranas.values())
    tardias, _c, _o = schedule(copy.deepcopy(tasks), links, cal, tz_name, minutes_per_day,
                               project={**proyecto, "from_start": False, "finish": fin})

    def local(dt):
        return pytz.utc.localize(dt).astimezone(tz).replace(tzinfo=None)

    def firmado(a, b):
        a, b = local(a), local(b)
        return cal.between(a, b) if b >= a else -cal.between(b, a)

    hijos = {}
    for i, t in tasks.items():
        if t["parent"] in tasks:
            hijos.setdefault(t["parent"], []).append(i)
    out = {}
    salen = {}
    for e in aristas:
        salen.setdefault(e["pred"], []).append(e)

    def libre(i, ef_, lf_):
        """La holgura libre de la hoja `i` (ver arriba)."""
        if tasks[i].get("actual_finish"):
            return 0.0
        mias = [e for e in salen.get(i, ()) if e["succ"] in tempranas]
        if not mias:
            return firmado(ef_, lf_)
        es_i, ef_i = local(tempranas[i][0]), local(tempranas[i][1])
        valores = []
        for e in mias:
            desde_inicio = e["type"] in ("ss", "sf")
            hacia_fin = e["type"] in ("ff", "sf")
            limite = cal.shift(es_i if desde_inicio else ef_i, e["lagmin"], e["elapsed"])
            s_es, s_ef = (local(x) for x in tempranas[e["succ"]])
            objetivo = s_ef if hacia_fin else s_es
            valores.append(cal.between(limite, objetivo) if objetivo >= limite else -cal.between(objetivo, limite))
        return min(valores)

    def hojas_de(i):
        if not tasks[i]["summary"]:
            return [i] if i in tempranas and i in tardias else []
        return [x for h in hijos.get(i, ()) for x in hojas_de(h)]

    def calcular(i):
        if i in out:
            return out[i]
        t = tasks[i]
        terminada = bool(t.get("actual_finish"))
        if not t["summary"]:
            if i not in tempranas or i not in tardias:
                return None
            (es_, ef_), (ls_, lf_) = tempranas[i], tardias[i]
            h = min(firmado(es_, ls_), firmado(ef_, lf_))
            # Entre 0 y la total, como lo guarda MS Project (ver arriba).
            out[i] = {"slack": h, "free": max(0.0, min(libre(i, ef_, lf_), h)), "critical": h <= 0 and not terminada,
                      "ef": ef_, "lf": lf_}
            return out[i]
        hojas = hojas_de(i)
        criticas = [calcular(h) for h in hijos.get(i, ())]
        if not hojas:
            return None
        es_ = min(tempranas[h][0] for h in hojas)
        ef_ = max(tempranas[h][1] for h in hojas)
        ls_ = min(tardias[h][0] for h in hojas)
        lf_ = max(tardias[h][1] for h in hojas)
        a, b = firmado(es_, ls_), firmado(ef_, lf_)
        h = min(a, b) if a < 0 else b
        alguna = any(c and c["critical"] for c in criticas)
        out[i] = {"slack": h, "critical": h <= 0 and alguna and not terminada, "ef": ef_, "lf": lf_}
        return out[i]

    for i in tasks:
        calcular(i)
    return out
