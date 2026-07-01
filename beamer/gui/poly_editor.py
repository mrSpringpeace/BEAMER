"""Editor vlastního průřezu – kreslicí plátno se snapem + tabulka souřadnic.

Podpora **kompozitního průřezu**: definice je seznam `Body` (vyplněné těleso),
každé tělo má vnější obrys a libovolný počet děr. Editor pracuje vždy s jedním
„cílovým" polygonem (obrys vybraného tělesa nebo jedna z jeho děr); ostatní se
vykreslují jako pozadí. Při změně mutuje přímo `sdef.bodies` a emituje `changed`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QHeaderView, QCheckBox, QComboBox,
)

from ..i18n import tr
from ..model import Body
from .spin import NoWheelDoubleSpinBox

GRID = 5.0      # snap mřížka [mm]
HIT_PX = 10     # poloměr uchopení bodu [px]


class DrawingCanvas(QWidget):
    """Kreslicí plátno polygonu.
    Levé tlačítko: přidat / uchopit / táhnout bod aktivního polygonu.
    Pravé tlačítko: smazat bod.
    Prostřední tlačítko: panování plátna.
    Kolečko: zoom kolem kurzoru."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.points = []          # aktivní polygon: list of [y, z] v mm
        self.bg_groups = []       # všechna tělesa pro render – každé jako celek
                                  # (vnější obrys + díry s odečtením):
                                  # [{"outer":[(y,z),...], "holes":[[(y,z),..],..],
                                  #   "label":str}, ...]
        self.snap = True
        self.scale = 1.5          # px/mm
        self.pan_x = 0.0          # px posun počátku
        self.pan_y = 0.0
        self._drag = None         # index taženého bodu
        self._panning = None      # (px, py) poslední pozice myši při panu
        self._user_view = False   # uživatel ručně panoval/zoomoval → neresetovat
        self.setMinimumHeight(520)
        self.setMinimumWidth(560)
        self.setMouseTracking(True)
        self.setStyleSheet("background:#ffffff; border:1px solid #bbb;")

    # ── konverze souřadnic ──
    def _origin(self):
        return QPointF(self.width()/2 + self.pan_x, self.height()/2 + self.pan_y)

    def w2s(self, y, z):
        o = self._origin()
        return QPointF(o.x() + y*self.scale, o.y() - z*self.scale)

    def s2w(self, px, py):
        o = self._origin()
        y = (px - o.x())/self.scale
        z = (o.y() - py)/self.scale
        if self.snap:
            y = round(y/GRID)*GRID
            z = round(z/GRID)*GRID
        return y, z

    # ── data ──
    def set_bodies(self, target_yz, bg_groups):
        """Nastav aktivní polygon (list [y,z]) a všechna tělesa kompozitu
        (jako celek s vyřezanými dírami). Aktivní polygon canvas mutuje v place;
        po změně emituje `changed`, volající čte `self.points` zpět."""
        self.points = [list(p) for p in (target_yz or [])]
        self.bg_groups = list(bg_groups or [])
        if not self._user_view:
            self._autoscale()
        self.update()

    def get_points(self):
        return [{"y": p[0], "z": p[1]} for p in self.points]

    def fit_view(self):
        """Vrátí pohled (pan + zoom) na celou geometrii (active + pozadí)."""
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._user_view = False
        self._autoscale()
        self.update()

    def _all_pts_for_view(self):
        out = list(self.points)
        for bg in self.bg_groups:
            out.extend([list(p) for p in bg.get("outer", [])])
            for h in bg.get("holes", []):
                out.extend([list(p) for p in h])
        return out

    def _autoscale(self):
        all_pts = self._all_pts_for_view()
        if len(all_pts) < 2:
            self.pan_x = 0.0
            self.pan_y = 0.0
            return
        ys = [p[0] for p in all_pts]
        zs = [p[1] for p in all_pts]
        y_mid = (max(ys) + min(ys)) / 2
        z_mid = (max(zs) + min(zs)) / 2
        span = max(max(ys)-min(ys), max(zs)-min(zs), 1)
        avail = min(self.width(), self.height()) - 60
        if avail > 20:
            self.scale = max(0.05, min(50.0, avail/span))
        # vycentrovat na (y_mid, z_mid)
        self.pan_x = -y_mid * self.scale
        self.pan_y = z_mid * self.scale     # z roste nahoru → py klesá

    # ── myš ──
    def _hit(self, px, py):
        for i, p in enumerate(self.points):
            s = self.w2s(p[0], p[1])
            if (s.x()-px)**2 + (s.y()-py)**2 <= HIT_PX**2:
                return i
        return None

    def mousePressEvent(self, e):
        px, py = e.position().x(), e.position().y()
        if e.button() == Qt.MiddleButton:
            self._panning = (px, py)
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() == Qt.LeftButton:
            i = self._hit(px, py)
            if i is not None:
                self._drag = i
            else:
                y, z = self.s2w(px, py)
                self.points.append([y, z])
                self.changed.emit()
            self.update()
        elif e.button() == Qt.RightButton:
            i = self._hit(px, py)
            if i is not None:
                self.points.pop(i)
                self.changed.emit()
                self.update()

    def mouseMoveEvent(self, e):
        px, py = e.position().x(), e.position().y()
        if self._panning is not None:
            dx = px - self._panning[0]
            dy = py - self._panning[1]
            self.pan_x += dx
            self.pan_y += dy
            self._panning = (px, py)
            self._user_view = True
            self.update()
            return
        if self._drag is not None:
            y, z = self.s2w(px, py)
            self.points[self._drag] = [y, z]
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton and self._panning is not None:
            self._panning = None
            self.setCursor(Qt.ArrowCursor)
            return
        if self._drag is not None:
            self._drag = None
            self.changed.emit()

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        if delta == 0:
            return
        px = e.position().x()
        py = e.position().y()
        # world pozice pod kurzorem (před zoomem)
        o = self._origin()
        y_w = (px - o.x()) / self.scale
        z_w = (o.y() - py) / self.scale
        factor = 1.2 if delta > 0 else (1/1.2)
        new_scale = max(0.05, min(50.0, self.scale * factor))
        if new_scale == self.scale:
            return
        self.scale = new_scale
        # posuň pan tak, aby (y_w, z_w) zůstalo přesně pod kurzorem
        self.pan_x = px - y_w * self.scale - self.width()/2
        self.pan_y = py + z_w * self.scale - self.height()/2
        self._user_view = True
        self.update()

    # ── vykreslení ──
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        o = self._origin()
        # mřížka
        step = GRID*self.scale
        if step >= 4:
            p.setPen(QPen(QColor(235, 235, 235), 1))
            x = o.x() % step
            while x < W:
                p.drawLine(int(x), 0, int(x), H)
                x += step
            y = o.y() % step
            while y < H:
                p.drawLine(0, int(y), W, int(y))
                y += step
        # osy
        p.setPen(QPen(QColor(120, 160, 220), 1))
        p.drawLine(0, int(o.y()), W, int(o.y()))
        p.drawLine(int(o.x()), 0, int(o.x()), H)

        # ── tělesa kompozitu: každé jako celek (obrys ∪ díry → OddEvenFill) ──
        for bg in self.bg_groups:
            outer = bg.get("outer") or []
            holes = bg.get("holes") or []
            if len(outer) < 3:
                continue
            path = QPainterPath()
            path.setFillRule(Qt.OddEvenFill)
            path.addPolygon(QPolygonF([self.w2s(y, z) for y, z in outer]))
            for h in holes:
                if len(h) >= 3:
                    path.addPolygon(QPolygonF([self.w2s(y, z) for y, z in h]))
            p.setBrush(QBrush(QColor(180, 205, 235, 170)))
            p.setPen(QPen(QColor(80, 110, 170), 1))
            p.drawPath(path)
            # vyznač díry červeně čárkovaně (vizuální klíč, že jsou odečteny)
            for h in holes:
                if len(h) >= 3:
                    p.setBrush(Qt.NoBrush)
                    p.setPen(QPen(QColor(190, 70, 70, 220), 1, Qt.DashLine))
                    p.drawPolygon(QPolygonF([self.w2s(y, z) for y, z in h]))
            # popisek tělesa u centroidu
            label = bg.get("label")
            if label:
                cy = sum(q[0] for q in outer) / len(outer)
                cz = sum(q[1] for q in outer) / len(outer)
                s = self.w2s(cy, cz)
                p.setPen(QColor(80, 80, 80))
                p.drawText(s, label)

        # ── aktivní polygon (silný obrys přes již vykreslené tělo) ──
        if len(self.points) >= 2:
            poly = QPolygonF([self.w2s(y, z) for y, z in self.points])
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(30, 80, 200), 2.6))
            if len(self.points) >= 3:
                p.drawPolygon(poly)
            else:
                p.drawPolyline(poly)
        # body + popisky se souřadnicemi
        for i, (y, z) in enumerate(self.points):
            s = self.w2s(y, z)
            p.setBrush(QBrush(QColor(220, 50, 50)))
            p.setPen(QPen(QColor(120, 20, 20), 1))
            p.drawEllipse(s, 4, 4)
            # bílá podkladová obálka pro čitelnost
            label = f"P{i+1}  [{y:.1f}, {z:.1f}]"
            tp = s + QPointF(7, -5)
            p.setPen(QColor(255, 255, 255))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                p.drawText(tp + QPointF(dx, dy), label)
            p.setPen(QColor(40, 40, 40))
            p.drawText(tp, label)
        # legenda
        p.setPen(QColor(110, 110, 110))
        p.drawText(8, H-8, tr("L-klik: přidat/táhnout bod · P-klik: smazat · "
                              "S-klik: posun plátna · kolečko: zoom"))
        # info o zoomu vpravo nahoře
        p.setPen(QColor(140, 140, 140))
        p.drawText(W - 130, 14, f"zoom: {self.scale:.2f} px/mm")


class PolygonEditor(QWidget):
    """Editor kompozitního průřezu: výběr cílového polygonu (tělo/díra) +
    plátno + tabulka souřadnic. Mutuje přímo `sdef.bodies`."""
    changed = Signal()

    def __init__(self, sdef):
        super().__init__()
        self.sdef = sdef
        self._migrate_legacy()
        # cíl editace: (body_idx, hole_idx_or_None)
        self.target = (0, None)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        # ── horní lišta: výběr cíle + manipulační tlačítka ──
        bar = QHBoxLayout()
        bar.addWidget(QLabel(tr("Editovat:")))
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._on_combo)
        bar.addWidget(self.combo, 1)
        b_add_body = QPushButton(tr("+ Tělo"))
        b_add_body.clicked.connect(self._add_body)
        b_add_hole = QPushButton(tr("+ Díra"))
        b_add_hole.clicked.connect(self._add_hole)
        b_del = QPushButton(tr("Smazat aktuální"))
        b_del.clicked.connect(self._del_current)
        bar.addWidget(b_add_body)
        bar.addWidget(b_add_hole)
        bar.addWidget(b_del)
        v.addLayout(bar)

        # ── plátno ──
        self.canvas = DrawingCanvas()
        v.addWidget(self.canvas)

        # ── volby ──
        opts = QHBoxLayout()
        self.snap_cb = QCheckBox(tr("Snap na mřížku 5 mm"))
        self.snap_cb.setChecked(True)
        self.snap_cb.toggled.connect(self._on_snap)
        opts.addWidget(self.snap_cb)
        opts.addStretch(1)
        fit = QPushButton(tr("Vyfitnout pohled"))
        fit.clicked.connect(self.canvas.fit_view)
        opts.addWidget(fit)
        clr = QPushButton(tr("Vymazat aktuální"))
        clr.clicked.connect(self._clear)
        opts.addWidget(clr)
        v.addLayout(opts)

        # ── tabulka souřadnic ──
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["y [mm]", "z [mm]", tr("vložit"), ""])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setMaximumHeight(220)
        v.addWidget(self.table)
        hint = QLabel(tr("＋ vloží nový bod na hranu za daný bod (pak ho lze "
                         "posunout), ✕ bod smaže."))
        hint.setObjectName("hint"); hint.setWordWrap(True)
        v.addWidget(hint)
        addb = QPushButton(tr("+ Přidat bod na konec"))
        addb.clicked.connect(self._add_row)
        v.addWidget(addb)

        self.canvas.changed.connect(self._on_canvas)
        self._rebuild_combo()
        self._sync_target()

    # ─────────────────────────────────────────────────────────
    #  migrace legacy formátu → bodies
    # ─────────────────────────────────────────────────────────
    def _migrate_legacy(self):
        """Pokud `sdef.bodies` chybí, vytvoř jedno tělo z `polygon_points` (a děr).
        Pokud i to chybí, vytvoř jedno prázdné tělo, aby měl editor co ukázat."""
        if self.sdef.bodies:
            return
        pts = [dict(p) for p in (self.sdef.polygon_points or [])]
        holes = [[dict(q) for q in h] for h in (self.sdef.polygon_holes or [])]
        self.sdef.bodies = [Body(points=pts, holes=holes)]

    # ─────────────────────────────────────────────────────────
    #  pomocné funkce pro „cíl"
    # ─────────────────────────────────────────────────────────
    def _targets(self):
        """Seznam (label, body_idx, hole_idx_or_None) v pořadí kombu."""
        out = []
        for i, b in enumerate(self.sdef.bodies):
            out.append((tr("Tělo") + f" {i+1} – " + tr("obrys"), i, None))
            for j in range(len(b.holes)):
                out.append((tr("Tělo") + f" {i+1} – " + tr("díra") + f" {j+1}",
                            i, j))
        return out

    def _target_pts(self):
        bi, hi = self.target
        bodies = self.sdef.bodies
        if not bodies or bi >= len(bodies):
            return None
        body = bodies[bi]
        if hi is None:
            return body.points
        if 0 <= hi < len(body.holes):
            return body.holes[hi]
        return None

    def _set_target_pts(self, new_pts):
        bi, hi = self.target
        body = self.sdef.bodies[bi]
        if hi is None:
            body.points = new_pts
        else:
            body.holes[hi] = new_pts

    # ─────────────────────────────────────────────────────────
    #  combo a synchronizace
    # ─────────────────────────────────────────────────────────
    def _rebuild_combo(self):
        ts = self._targets()
        self.combo.blockSignals(True)
        self.combo.clear()
        for label, _, _ in ts:
            self.combo.addItem(label)
        # zachovat výběr, pokud existuje
        cur = -1
        for k, (_, bi, hi) in enumerate(ts):
            if bi == self.target[0] and hi == self.target[1]:
                cur = k
                break
        if cur < 0 and ts:
            cur = 0
            self.target = (ts[0][1], ts[0][2])
        if cur >= 0:
            self.combo.setCurrentIndex(cur)
        self.combo.blockSignals(False)

    def _on_combo(self, idx):
        ts = self._targets()
        if 0 <= idx < len(ts):
            _, bi, hi = ts[idx]
            self.target = (bi, hi)
            self._sync_target()

    def _sync_target(self):
        """Aktualizuj canvas (target + tělesa) i tabulku podle `self.target`."""
        bodies = self.sdef.bodies
        bi, hi = self.target
        if not bodies or bi >= len(bodies):
            self.canvas.set_bodies([], [])
            self._refresh_table()
            return
        # aktivní polygon → [y,z] kopie pro canvas (canvas ho mutuje v place)
        target_pts = self._target_pts() or []
        target_yz = [[float(p["y"]), float(p["z"])] for p in target_pts]
        # všechna tělesa kompozitu jako celek (canvas je sám vykreslí
        # s odečtením děr přes QPainterPath + OddEvenFill)
        groups = []
        for i, b in enumerate(bodies):
            label = tr("Tělo") + f" {i+1}"
            outer = [(float(p["y"]), float(p["z"])) for p in (b.points or [])]
            holes = [[(float(p["y"]), float(p["z"])) for p in h]
                     for h in (b.holes or []) if h]
            groups.append({"outer": outer, "holes": holes, "label": label})
        self.canvas.set_bodies(target_yz, groups)
        self._refresh_table()

    # ─────────────────────────────────────────────────────────
    #  reakce na úpravy v canvasu
    # ─────────────────────────────────────────────────────────
    def _on_canvas(self):
        """Canvas mutoval `points`. Zapiš zpět do bodies a obnov UI."""
        new_pts = self.canvas.get_points()
        self._set_target_pts(new_pts)
        # nestriguj `canvas.set_target` – aktivní polygon už canvas drží správně,
        # ale potřebujeme jen překreslit pozadí, kdyby se mezitím něco změnilo.
        # Tabulku ale stačí znova vyrobit, aby seděla s body.
        self._refresh_table()
        self.changed.emit()

    # ─────────────────────────────────────────────────────────
    #  tabulka
    # ─────────────────────────────────────────────────────────
    def _refresh_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for i, p in enumerate(self._target_pts() or []):
            r = self.table.rowCount()
            self.table.insertRow(r)
            ysp = NoWheelDoubleSpinBox()
            ysp.setRange(-1e5, 1e5); ysp.setDecimals(2); ysp.setValue(p["y"])
            ysp.valueChanged.connect(lambda val, idx=i: self._edit(idx, 0, val))
            self.table.setCellWidget(r, 0, ysp)
            zsp = NoWheelDoubleSpinBox()
            zsp.setRange(-1e5, 1e5); zsp.setDecimals(2); zsp.setValue(p["z"])
            zsp.valueChanged.connect(lambda val, idx=i: self._edit(idx, 1, val))
            self.table.setCellWidget(r, 1, zsp)
            ins = QPushButton("＋"); ins.setMaximumWidth(30)
            ins.setToolTip(tr("Vložit bod za tento (na hranu k dalšímu)"))
            ins.clicked.connect(lambda _, idx=i: self._insert_after(idx))
            self.table.setCellWidget(r, 2, ins)
            db = QPushButton("✕"); db.setMaximumWidth(30)
            db.clicked.connect(lambda _, idx=i: self._del_row(idx))
            self.table.setCellWidget(r, 3, db)
        self.table.blockSignals(False)

    def _edit(self, idx, comp, val):
        pts = self._target_pts()
        if pts is None or idx >= len(pts):
            return
        pts[idx]["y" if comp == 0 else "z"] = val
        self._sync_target()       # překreslí canvas i pozadí
        self.changed.emit()

    def _add_row(self):
        pts = self._target_pts()
        if pts is None:
            return
        pts.append({"y": 0.0, "z": 0.0})
        self._sync_target()
        self.changed.emit()

    def _insert_after(self, idx):
        """Vloží nový bod hned za bod `idx` – na střed hrany k následujícímu bodu
        (u posledního bodu na hranu zpět k prvnímu), takže padne přesně na obrys
        a lze ho pak posunout. Řeší editaci bez nutnosti začínat znovu."""
        pts = self._target_pts()
        if pts is None or not pts or idx >= len(pts):
            return
        cur = pts[idx]
        nxt = pts[(idx + 1) % len(pts)]
        mid = {"y": (float(cur["y"]) + float(nxt["y"])) / 2.0,
               "z": (float(cur["z"]) + float(nxt["z"])) / 2.0}
        pts.insert(idx + 1, mid)
        self._sync_target()
        self.changed.emit()

    def _del_row(self, idx):
        pts = self._target_pts()
        if pts is None or idx >= len(pts):
            return
        pts.pop(idx)
        self._sync_target()
        self.changed.emit()

    # ─────────────────────────────────────────────────────────
    #  +Tělo / +Díra / Smazat aktuální
    # ─────────────────────────────────────────────────────────
    def _add_body(self):
        self.sdef.bodies.append(Body(points=[], holes=[]))
        self.target = (len(self.sdef.bodies) - 1, None)
        self.canvas._user_view = False
        self._rebuild_combo()
        self._sync_target()
        self.changed.emit()

    def _add_hole(self):
        bi, _ = self.target
        if bi >= len(self.sdef.bodies):
            return
        body = self.sdef.bodies[bi]
        body.holes.append([])
        self.target = (bi, len(body.holes) - 1)
        self.canvas._user_view = False
        self._rebuild_combo()
        self._sync_target()
        self.changed.emit()

    def _del_current(self):
        bi, hi = self.target
        bodies = self.sdef.bodies
        if not bodies or bi >= len(bodies):
            return
        if hi is not None:
            if 0 <= hi < len(bodies[bi].holes):
                del bodies[bi].holes[hi]
            self.target = (bi, None)
        else:
            if len(bodies) <= 1:
                # ponech alespoň jedno (prázdné) tělo
                bodies[0] = Body(points=[], holes=[])
                self.target = (0, None)
            else:
                del bodies[bi]
                self.target = (max(0, bi - 1), None)
        self._rebuild_combo()
        self._sync_target()
        self.changed.emit()

    # ─────────────────────────────────────────────────────────
    #  ostatní
    # ─────────────────────────────────────────────────────────
    def _on_snap(self, v):
        self.canvas.snap = v

    def _clear(self):
        """Vyprázdnit aktivní polygon (obrys nebo díru)."""
        pts = self._target_pts()
        if pts is None:
            return
        pts.clear()
        self.canvas._user_view = False
        self._sync_target()
        self.changed.emit()
