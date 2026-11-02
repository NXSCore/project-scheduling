# -*- coding: utf-8 -*-
"""Dibujo del informe: tabla + diagrama de Gantt paginados, en PDF vectorial.

Se dibuja con `reportlab` (dependencia de Odoo) y no con QWeb + wkhtmltopdf:
el diagrama son cientos de rectángulos y líneas con coordenadas exactas, y el
SVG del WebKit viejo de wkhtmltopdf no es confiable para eso.

Este módulo NO toca la base: recibe filas ya leídas con los permisos de quien
imprime (`ReportData`) y devuelve los bytes del PDF. Así se prueba solo.
"""
import io
import math
import os
from datetime import datetime, timedelta

from babel.dates import format_date
from reportlab.lib import pagesizes
from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.pdfgen import canvas

PAPERS = {"a4": pagesizes.A4, "a3": pagesizes.A3, "letter": pagesizes.LETTER, "tabloid": pagesizes.TABLOID}

# Puntos por día de cada escala, cuando el cronograma NO se ajusta al papel.
SCALES = {"day": 16.0, "week": 4.0, "month": 1.2, "quarter": 0.45}

C = {
    "task": HexColor("#4a90d9"), "task_dark": HexColor("#23629f"),
    "critical": HexColor("#d9534f"), "critical_dark": HexColor("#9e2b27"),
    "summary": HexColor("#6f42c1"), "milestone": HexColor("#6f42c1"),
    "float": HexColor("#b9e4b0"), "baseline": HexColor("#9aa0a6"),
    # Las dos líneas base de comparación (los mismos del planificador).
    "compare1": HexColor("#0284c7"), "compare2": HexColor("#c026d3"),
    "link": HexColor("#5f6368"), "today": HexColor("#f0883e"),
    "grid": HexColor("#e3e6ea"), "weekend": HexColor("#f2f3f5"),
    "deadline": HexColor("#16a34a"), "deadline_missed": HexColor("#dc2626"),
    "head": HexColor("#f6f7f9"), "text": HexColor("#202124"), "muted": HexColor("#6b7075"),
}

# (clave, ancho en puntos a escala 100 %, alineación)
#: Todas las columnas que el informe sabe imprimir (las del
#: planificador): clave → (ancho en puntos a escala 100 %, alineación).
COLUMN_SPECS = {
    "num": (22, "r"), "code": (42, "l"), "name": (170, "l"), "duration": (40, "r"),
    "start": (50, "c"), "end": (50, "c"), "pred": (60, "l"), "succ": (60, "l"), "users": (80, "l"),
    "progress": (26, "r"), "float": (36, "r"), "free_float": (36, "r"), "critical": (24, "c"), "constraint": (90, "l"),
    "deadline": (50, "c"), "actual_start": (50, "c"), "actual_end": (50, "c"),
    "baseline_start": (50, "c"), "baseline_end": (50, "c"),
}
DEFAULT_COLUMNS = ["num", "code", "name", "duration", "start", "end", "progress"]

_FONTS = None


def fonts():
    """DejaVu si el sistema la tiene (cubre cualquier alfabeto); si no, la
    Helvetica estándar del PDF, que cubre el español (WinAnsi)."""
    global _FONTS
    if _FONTS is None:
        _FONTS = ("Helvetica", "Helvetica-Bold")
        for base in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu"):
            regular, bold = os.path.join(base, "DejaVuSans.ttf"), os.path.join(base, "DejaVuSans-Bold.ttf")
            if os.path.exists(regular) and os.path.exists(bold):
                try:
                    pdfmetrics.registerFont(TTFont("ReDejaVu", regular))
                    pdfmetrics.registerFont(TTFont("ReDejaVu-Bold", bold))
                    _FONTS = ("ReDejaVu", "ReDejaVu-Bold")
                except (TTFError, OSError):  # una fuente rota no impide imprimir
                    _FONTS = ("Helvetica", "Helvetica-Bold")
                break
    return _FONTS


class Axis:
    """Fecha local → coordenada en DÍAS desde el inicio del rango.

    Con `workdays_only`, los días no laborables no ocupan lugar: una barra que
    cruza un fin de semana se acorta, como en «Mostrar solo días laborables».
    """

    def __init__(self, date_from, date_to, nonworking, workdays_only, holidays=()):
        self.d0 = date_from.date()
        self.d1 = date_to.date() + timedelta(days=1)
        self.nonworking = nonworking
        # Los feriados del calendario también son no laborables.
        self.holidays = set(holidays)
        self.workdays_only = workdays_only
        self.index = {}
        i = 0
        d = self.d0
        while d <= self.d1:
            self.index[d] = i
            if not (workdays_only and self.is_off(d)):
                i += 1
            d += timedelta(days=1)
        self.length = i if workdays_only else (self.d1 - self.d0).days

    def is_off(self, d):
        return d.weekday() in self.nonworking or d in self.holidays

    def pos(self, dt):
        if not self.workdays_only:
            return (dt - datetime.combine(self.d0, datetime.min.time())).total_seconds() / 86400.0
        d = min(max(dt.date(), self.d0), self.d1)
        if self.is_off(d):
            return float(self.index[d])
        frac = (dt - datetime.combine(dt.date(), datetime.min.time())).total_seconds() / 86400.0
        return self.index[d] + (frac if self.d0 <= dt.date() <= self.d1 else 0.0)

    def days(self):
        d = self.d0
        while d < self.d1:
            yield d
            d += timedelta(days=1)


def _segments(axis, unit, locale):
    """Tramos del encabezado: (inicio, fin, etiqueta) en fechas."""
    d = axis.d0
    while d < axis.d1:
        if unit == "day":
            nxt, label = d + timedelta(days=1), str(d.day)
        elif unit == "week":
            nxt = d + timedelta(days=7 - d.weekday())
            label = "W%02d" % d.isocalendar()[1]
        elif unit == "month":
            nxt = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
            label = format_date(d, "LLL", locale=locale).rstrip(".").capitalize()
        elif unit == "month_year":
            nxt = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
            label = format_date(d, "LLLL yyyy", locale=locale).capitalize()
        elif unit == "quarter":
            q = (d.month - 1) // 3
            nxt = d.replace(month=3 * q + 1, day=1)
            nxt = (nxt + timedelta(days=95)).replace(day=1)
            label = "Q%d" % (q + 1)
        else:  # year
            nxt, label = d.replace(year=d.year + 1, month=1, day=1), str(d.year)
        yield d, min(nxt, axis.d1), label
        d = nxt


def _datetime(d):
    return datetime.combine(d, datetime.min.time())


class GanttPdf:
    """Uso: `GanttPdf(data, opts).render()` → bytes.

    `data`: title, company, author, printed, project_start/finish/duration
    (textos), rows, links, nonworking (días de la semana 0=lunes), today
    (local), date_from/date_to (local), labels (textos traducidos), locale.
    Cada fila: id, num, code, name, depth, summary, milestone, start, end
    (local), duration, start_label, end_label, progress (0–100 o None),
    critical, float_days, baseline_start, baseline_end.
    """

    def __init__(self, data, opts):
        self.data, self.o = data, opts
        self.s = max(0.5, min(2.0, (opts.get("font_scale") or 100) / 100.0))
        w, h = PAPERS.get(opts.get("paper"), pagesizes.A3)
        self.page_w, self.page_h = (max(w, h), min(w, h)) if opts.get("orientation", "landscape") == "landscape" else (min(w, h), max(w, h))
        self.font, self.bold = fonts()
        self.L = data["labels"]
        s = self.s
        self.margin = 24.0
        self.row_h = 13.0 * s
        self.fs = 6.8 * s
        self.header_h = 46.0 * s
        self.timehead_h = 26.0 * s
        self.footer_h = 18.0 * s
        claves = [k for k in (opts.get("columns") or DEFAULT_COLUMNS) if k in COLUMN_SPECS]
        if "name" not in claves:
            claves.insert(0, "name")
        claves = ["num"] + [k for k in claves if k != "num"]
        self.cols = [(k, COLUMN_SPECS[k][0] * s, COLUMN_SPECS[k][1]) for k in claves]
        self.table_w = sum(wd for _, wd, _ in self.cols)
        self.time_w = self.page_w - 2 * self.margin - self.table_w
        if self.time_w < 80:
            raise ValueError("timeline_too_narrow")
        self.axis = Axis(data["date_from"], data["date_to"], data.get("nonworking", {5, 6}), opts.get("workdays_only"),
                         data.get("holidays", ()))
        if opts.get("fit_to_paper", True):
            self.h_pages = max(1, min(20, int(opts.get("timeline_pages") or 1)))
            self.ppd = self.time_w * self.h_pages / max(1.0, self.axis.length)
        else:
            self.ppd = SCALES.get(opts.get("scale"), SCALES["week"]) * s
            self.h_pages = max(1, math.ceil(self.axis.length * self.ppd / self.time_w))
        self.rows = data["rows"]
        self.by_id = {r["id"]: r for r in self.rows}

    # ------------------------------------------------------------ paginación
    def _rows_per_page(self, with_header):
        alto = self.page_h - 2 * self.margin - self.footer_h - self.timehead_h - (self.header_h if with_header else 0)
        return max(1, int(alto // self.row_h))

    def _row_chunks(self):
        chunks, i, first = [], 0, True
        while i < len(self.rows) or not chunks:
            con_encabezado = first or self.o.get("repeat_header", True)
            n = self._rows_per_page(con_encabezado)
            chunks.append((self.rows[i:i + n], con_encabezado))
            i += n
            first = False
        return chunks

    def render(self):
        buf = io.BytesIO()
        self.c = canvas.Canvas(buf, pagesize=(self.page_w, self.page_h), pageCompression=1)
        self.c.setTitle(self.data["title"])
        self.c.setAuthor(self.data.get("author") or "")
        chunks = self._row_chunks()
        total = len(chunks) * self.h_pages
        n = 0
        for filas, con_encabezado in chunks:
            for hp in range(self.h_pages):
                n += 1
                self._page(filas, con_encabezado, hp, n, total)
                self.c.showPage()
        self.c.save()
        self.page_count = total
        return buf.getvalue()

    # ------------------------------------------------------------- utilidades
    def y(self, top):
        """Coordenada desde ARRIBA → la de reportlab (desde abajo)."""
        return self.page_h - top

    def text(self, x, top, txt, size=None, bold=False, color=None, align="l", max_w=None):
        size = size or self.fs
        font = self.bold if bold else self.font
        txt = txt or ""
        if max_w is not None:
            txt = self.fit(txt, font, size, max_w)
        self.c.setFont(font, size)
        self.c.setFillColor(color or C["text"])
        yy = self.y(top)
        if align == "r":
            self.c.drawRightString(x, yy, txt)
        elif align == "c":
            self.c.drawCentredString(x, yy, txt)
        else:
            self.c.drawString(x, yy, txt)

    @staticmethod
    def fit(txt, font, size, max_w):
        if pdfmetrics.stringWidth(txt, font, size) <= max_w:
            return txt
        while txt and pdfmetrics.stringWidth(txt + "…", font, size) > max_w:
            txt = txt[:-1]
        return txt + "…" if txt else ""

    def _baseline_strip(self, r, top, alto):
        """La vigente y las comparadas en una franja; donde se
        traslapan, franjas finas alternando sus colores."""
        tramos = []
        if r.get("baseline_start") and r.get("baseline_end"):
            tramos.append((r["baseline_start"], r["baseline_end"], C["baseline"]))
        for i, (a, b) in enumerate(r.get("compare") or []):
            if a and b:
                tramos.append((a, b, C["compare%d" % (i + 1)]))
        if not tramos:
            return
        px = [(self.X(self.axis.pos(a)), self.X(self.axis.pos(b)), color) for a, b, color in tramos]
        px = [(a, max(b, a + 0.8), color) for a, b, color in px]
        cortes = sorted({x for a, b, _c in px for x in (a, b)})
        paso = 1.2 * self.s
        for a, b in zip(cortes, cortes[1:]):
            colores = [color for x0, x1, color in px if x0 <= a and x1 >= b]
            if len(colores) == 1:
                self.rect(a, top, b - a, alto, colores[0])
            elif colores:
                x, n = a, 0
                while x < b:
                    self.rect(x, top, min(paso, b - x), alto, colores[n % len(colores)])
                    x, n = x + paso, n + 1

    def rect(self, x, top, w, h, fill, stroke=None):
        self.c.setFillColor(fill)
        if stroke is not None:
            self.c.setStrokeColor(stroke)
        self.c.rect(x, self.y(top + h), w, h, fill=1, stroke=1 if stroke is not None else 0)

    def line(self, x0, t0, x1, t1, color, width=0.4, dash=None):
        self.c.setStrokeColor(color)
        self.c.setLineWidth(width)
        self.c.setDash(*(dash or ([], 0)))
        self.c.line(x0, self.y(t0), x1, self.y(t1))
        self.c.setDash([], 0)

    # ------------------------------------------------------------------ página
    def _page(self, filas, con_encabezado, hp, n, total):
        m, s = self.margin, self.s
        top = m
        if con_encabezado:
            self._header(top)
            top += self.header_h
        x_time = self.x_time = m + self.table_w
        rows_top = top + self.timehead_h
        rows_h = len(filas) * self.row_h
        # Ventana de tiempo de esta página, en días del eje.
        d_from = hp * self.time_w / self.ppd
        self.X = lambda dias: x_time + (dias - d_from) * self.ppd
        self._timehead(x_time, top, rows_top + rows_h, d_from)
        self._table(filas, m, top, rows_top)
        self.row_top = {r["id"]: rows_top + i * self.row_h for i, r in enumerate(filas)}
        # Todo lo del cronograma se recorta a su recuadro: una barra que sigue
        # en la página siguiente no invade la tabla.
        self.c.saveState()
        p = self.c.beginPath()
        p.rect(x_time, self.y(rows_top + rows_h), self.time_w, rows_h)
        self.c.clipPath(p, stroke=0, fill=0)
        if self.o.get("show_links", True):
            self._links(filas)
        for r in filas:
            self._bar(r)
        if self.o.get("status_line") == "today" and self.data.get("today"):
            x = self.X(self.axis.pos(self.data["today"]))
            self.line(x, rows_top, x, rows_top + rows_h, C["today"], 1.0 * s, ([3 * s, 2 * s], 0))
        self.c.restoreState()
        # Marco y líneas de fila.
        for i in range(len(filas) + 1):
            t = rows_top + i * self.row_h
            self.line(m, t, self.page_w - m, t, C["grid"], 0.3)
        self.line(x_time, top, x_time, rows_top + rows_h, C["muted"], 0.5)
        self._footer(n, total)

    def _header(self, top):
        s, m = self.s, self.margin
        d = self.data
        self.text(m, top + 14 * s, d["title"], 14 * s, bold=True, max_w=self.page_w * 0.55)
        self.text(m, top + 27 * s, "%s: %s" % (self.L["printed"], d["printed"]), 7.5 * s, color=C["muted"])
        resumen = "%s: %s    %s: %s    %s: %s" % (
            self.L["start"], d.get("project_start") or "—", self.L["finish"], d.get("project_finish") or "—",
            self.L["duration"], d.get("project_duration") or "—")
        self.text(m, top + 38 * s, resumen, 7.5 * s)
        derecha = self.page_w - m
        if d.get("company"):
            self.text(derecha, top + 14 * s, d["company"], 9 * s, bold=True, align="r")
        if d.get("author"):
            self.text(derecha, top + 27 * s, "%s: %s" % (self.L["author"], d["author"]), 7.5 * s, color=C["muted"], align="r")
        self.line(m, top + self.header_h - 4 * s, self.page_w - m, top + self.header_h - 4 * s, C["muted"], 0.6)

    def _units(self):
        ppd = self.ppd
        if ppd >= 12:
            return "month_year", "day"
        if ppd >= 2.2:
            return "month_year", "week"
        if ppd >= 0.5:
            return "year", "month"
        return "year", "quarter"

    def _timehead(self, x_time, top, bottom, d_from):
        s = self.s
        half = self.timehead_h / 2
        self.rect(self.margin, top, self.page_w - 2 * self.margin, self.timehead_h, C["head"])
        d_to = d_from + self.time_w / self.ppd
        superior, inferior = self._units()
        # Fines de semana sombreados (solo si se distinguen los días).
        if self.o.get("shade_weekends", True) and not self.axis.workdays_only and self.ppd >= 1.5:
            for d in self.axis.days():
                if self.axis.is_off(d):
                    p = self.axis.pos(_datetime(d))
                    if d_from - 1 <= p <= d_to:
                        x0 = max(x_time, self.X(p))
                        x1 = min(x_time + self.time_w, self.X(p + 1))
                        if x1 > x0:
                            self.rect(x0, top + self.timehead_h, x1 - x0, bottom - top - self.timehead_h, C["weekend"])
        for fila, unidad in ((0, superior), (1, inferior)):
            t = top + fila * half
            for ini, fin, etiqueta in _segments(self.axis, unidad, self.data.get("locale", "en_US")):
                p0, p1 = self.axis.pos(_datetime(ini)), self.axis.pos(_datetime(fin))
                if p1 <= d_from or p0 >= d_to:
                    continue
                x0, x1 = max(x_time, self.X(p0)), min(x_time + self.time_w, self.X(p1))
                if self.X(p0) >= x_time:
                    self.line(self.X(p0), t, self.X(p0), t + half if fila == 0 else bottom, C["grid"] if fila else C["muted"], 0.3)
                if x1 - x0 > 8 * s:
                    self.text((x0 + x1) / 2, t + half - 4 * s, etiqueta, self.fs * (1.0 if fila else 1.05),
                              bold=fila == 0, color=C["text"] if fila == 0 else C["muted"], align="c", max_w=x1 - x0 - 2)
        self.line(x_time, top + half, x_time + self.time_w, top + half, C["grid"], 0.3)
        # Encabezados de columna.
        x = self.margin
        for clave, ancho, alin in self.cols:
            cx = {"l": x + 2, "r": x + ancho - 2, "c": x + ancho / 2}[alin]
            self.text(cx, top + self.timehead_h - 6 * s, self.L["col_" + clave], self.fs, bold=True, align=alin, max_w=ancho - 3)
            x += ancho
        self.line(self.margin, top, self.page_w - self.margin, top, C["muted"], 0.5)

    def _table(self, filas, x0, top, rows_top):
        s = self.s
        for i, r in enumerate(filas):
            base = rows_top + i * self.row_h + self.row_h - 3.6 * s
            x = x0
            for clave, ancho, alin in self.cols:
                if clave == "name":
                    sangria = min(r["depth"], 8) * 7 * s
                    self.text(x + 2 + sangria, base, r["name"], bold=r["summary"], max_w=ancho - 4 - sangria)
                else:
                    propias = {
                        "num": str(r["num"]), "code": r["code"], "duration": r["duration"],
                        "start": r["start_label"], "end": r["end_label"],
                        "progress": "" if r.get("progress") is None else "%d%%" % round(r["progress"]),
                    }
                    valor = propias[clave] if clave in propias else (r.get("cells") or {}).get(clave, "")
                    cx = {"l": x + 2, "r": x + ancho - 2, "c": x + ancho / 2}[alin]
                    self.text(cx, base, valor, bold=r["summary"] and clave != "num", align=alin, max_w=ancho - 3)
                x += ancho

    # ---------------------------------------------------------------- barras
    def _span(self, r):
        return self.X(self.axis.pos(r["start"])), self.X(self.axis.pos(r["end"]))

    def _bar(self, r):
        if not (r.get("start") and r.get("end")):
            return
        s, o = self.s, self.o
        t = self.row_top[r["id"]]
        x0, x1 = self._span(r)
        mid = t + self.row_h / 2
        critico = r["critical"] and o.get("bar_colors", "critical") == "critical"
        fin_texto = x1
        # La fecha límite, como la flecha de MS Project (roja si se pasa).
        if r.get("deadline"):
            self._deadline_mark(self.X(self.axis.pos(r["deadline"])), t, r["end"] > r["deadline"])
        if r["milestone"]:
            k = 4.2 * s
            self.c.setFillColor(C["critical"] if critico else C["milestone"])
            p = self.c.beginPath()
            p.moveTo(x0, self.y(mid - k))
            p.lineTo(x0 + k, self.y(mid))
            p.lineTo(x0, self.y(mid + k))
            p.lineTo(x0 - k, self.y(mid))
            p.close()
            self.c.drawPath(p, fill=1, stroke=0)
            fin_texto = x0 + k
        elif r["summary"]:
            h = 3.2 * s
            top_bar = mid - h
            self.rect(x0, top_bar, max(x1 - x0, 0.5), h, C["summary"])
            self.c.setFillColor(C["summary"])
            for xe in (x0, x1):
                p = self.c.beginPath()
                p.moveTo(xe - 2.6 * s, self.y(top_bar))
                p.lineTo(xe + 2.6 * s, self.y(top_bar))
                p.lineTo(xe, self.y(top_bar + h + 3 * s))
                p.close()
                self.c.drawPath(p, fill=1, stroke=0)
        else:
            h = self.row_h * 0.52
            tb = mid - h / 2
            if o.get("show_baseline"):
                self._baseline_strip(r, tb + h + 0.6 * s, 1.8 * s)
            # Hasta el fin MÁS TARDÍO del motor, no fin + holgura: la holgura va
            # en días laborables y, sobre un fin de semana, la banda quedaría corta.
            if (o.get("show_float", True) and r.get("float_days", 0) > 0.01 and not r["critical"] and not r.get("done")
                    and r.get("late_finish")):
                f1 = self.X(self.axis.pos(r["late_finish"]))
                if f1 > x1:
                    self.rect(x1, mid - h / 4, f1 - x1, h / 2, C["float"])
                    fin_texto = f1
            color, oscuro = (C["critical"], C["critical_dark"]) if critico else (C["task"], C["task_dark"])
            self.rect(x0, tb, max(x1 - x0, 0.8), h, color)
            if o.get("show_progress", True) and r.get("progress"):
                self.rect(x0, tb + h * 0.3, max(x1 - x0, 0.8) * min(r["progress"], 100) / 100.0, h * 0.4, oscuro)
        # El nombre de una barra que quedó en la página anterior no se dibuja:
        # recortado al borde solo dejaría un pedazo de texto suelto.
        if o.get("names_on_bars", True) and fin_texto + 3 * s >= self.x_time:
            self.text(fin_texto + 3 * s, mid + self.fs * 0.35, r["name"], self.fs * 0.92, color=C["text"],
                      max_w=220 * s)

    def _deadline_mark(self, xd, top, vencida):
        s = self.s
        self.c.setFillColor(C["deadline_missed"] if vencida else C["deadline"])
        p = self.c.beginPath()
        p.moveTo(xd - 3 * s, self.y(top + 1 * s))
        p.lineTo(xd + 3 * s, self.y(top + 1 * s))
        p.lineTo(xd, self.y(top + 5 * s))
        p.close()
        self.c.drawPath(p, fill=1, stroke=0)
        self.rect(xd - 0.5 * s, top + 4.5 * s, 1 * s, self.row_h - 6 * s, C["deadline_missed"] if vencida else C["deadline"])

    def _links(self, filas):
        s = self.s
        visibles = self.row_top
        for ln in self.data["links"]:
            a, b = self.by_id.get(ln["from"]), self.by_id.get(ln["to"])
            if not (a and b) or a["id"] not in visibles or b["id"] not in visibles:
                continue
            if not (a.get("start") and b.get("start")):
                continue
            ax0, ax1 = self._span(a)
            bx0, bx1 = self._span(b)
            tipo = (ln.get("type") or "fs").upper()
            # Lado de salida (inicio: hacia la izquierda; fin: a la derecha) y
            # lado de llegada, según el tipo.
            sx, ds = (ax0, -1) if tipo[0] == "S" else (ax1, 1)
            tx, dt = (bx0, -1) if tipo[1] == "S" else (bx1, 1)
            sy = visibles[a["id"]] + self.row_h / 2
            ty = visibles[b["id"]] + self.row_h / 2
            g = 4 * s
            puntos_lo = [x + g for x, d in ((sx, ds), (tx, dt)) if d == 1]
            puntos_hi = [x - g for x, d in ((sx, ds), (tx, dt)) if d == -1]
            lo = max(puntos_lo) if puntos_lo else -1e9
            hi = min(puntos_hi) if puntos_hi else 1e9
            if lo <= hi:
                v = lo if ds == 1 else hi
                camino = [(sx, sy), (v, sy), (v, ty), (tx, ty)]
            else:
                ym = ty - math.copysign(self.row_h / 2, ty - sy)
                camino = [(sx, sy), (sx + ds * g, sy), (sx + ds * g, ym), (tx + dt * g, ym), (tx + dt * g, ty), (tx, ty)]
            color = C["critical"] if (a["critical"] and b["critical"] and self.o.get("bar_colors", "critical") == "critical") else C["link"]
            self.c.setStrokeColor(color)
            self.c.setLineWidth(0.5 * s)
            p = self.c.beginPath()
            p.moveTo(camino[0][0], self.y(camino[0][1]))
            for x, t in camino[1:]:
                p.lineTo(x, self.y(t))
            self.c.drawPath(p, fill=0, stroke=1)
            # Punta de flecha hacia la barra.
            k = 2.4 * s
            self.c.setFillColor(color)
            p = self.c.beginPath()
            p.moveTo(tx, self.y(ty))
            p.lineTo(tx + dt * k * 1.4, self.y(ty - k))
            p.lineTo(tx + dt * k * 1.4, self.y(ty + k))
            p.close()
            self.c.drawPath(p, fill=1, stroke=0)

    # ----------------------------------------------------------------- pie
    def _footer(self, n, total):
        s, m = self.s, self.margin
        base = self.page_h - m + 4 * s
        self.text(self.page_w - m, base, "%d / %d" % (n, total), 7.5 * s, color=C["muted"], align="r")
        if not self.o.get("show_legend", True):
            self.text(m, base, self.data["title"], 7 * s, color=C["muted"], max_w=self.page_w / 2)
            return
        x = m
        items = [("task", self.L["legend_task"])]
        if self.o.get("bar_colors", "critical") == "critical":
            items.append(("critical", self.L["legend_critical"]))
        items += [("summary", self.L["legend_summary"]), ("milestone", self.L["legend_milestone"])]
        if self.o.get("show_progress", True):
            items.append(("progress", self.L["legend_progress"]))
        if self.o.get("show_float", True):
            items.append(("float", self.L["legend_float"]))
        if self.o.get("show_baseline"):
            nombres = self.data.get("compare_names") or []
            # Con comparación, cada franja con el nombre de su versión.
            items.append(("baseline", self.data.get("current_baseline") if nombres and self.data.get("current_baseline")
                          else self.L["legend_baseline"]))
            items += [("compare%d" % (i + 1), nombre) for i, nombre in enumerate(nombres)]
        if self.o.get("status_line") == "today":
            items.append(("today", self.L["legend_today"]))
        if any(r.get("deadline") for r in self.rows):
            items.append(("deadline", self.L["legend_deadline"]))
        for clave, etiqueta in items:
            muestra = 12 * s
            arriba = base - 6 * s
            if clave == "milestone":
                k = 3.5 * s
                self.c.setFillColor(C["milestone"])
                p = self.c.beginPath()
                cx, cy = x + muestra / 2, arriba + 3 * s
                p.moveTo(cx, self.y(cy - k))
                p.lineTo(cx + k, self.y(cy))
                p.lineTo(cx, self.y(cy + k))
                p.lineTo(cx - k, self.y(cy))
                p.close()
                self.c.drawPath(p, fill=1, stroke=0)
            elif clave == "today":
                self.line(x + muestra / 2, arriba - 1 * s, x + muestra / 2, arriba + 7 * s, C["today"], 1.0 * s, ([2 * s, 1.5 * s], 0))
            elif clave == "deadline":
                self._deadline_mark(x + muestra / 2, arriba - 1 * s, False)
            elif clave == "progress":
                self.rect(x, arriba, muestra, 6 * s, C["task"])
                self.rect(x, arriba + 1.8 * s, muestra * 0.6, 2.4 * s, C["task_dark"])
            elif clave == "summary":
                self.rect(x, arriba + 1 * s, muestra, 3 * s, C["summary"])
            else:
                self.rect(x, arriba, muestra, 6 * s, C[clave])
            self.text(x + muestra + 3 * s, base, etiqueta, 7 * s, color=C["muted"])
            x += muestra + 8 * s + pdfmetrics.stringWidth(etiqueta, self.font, 7 * s)
        self.c.setFillColor(white)
