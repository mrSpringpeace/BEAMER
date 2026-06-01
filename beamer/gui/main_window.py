"""Hlavní okno aplikace BEAMER."""
from __future__ import annotations

import os
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QIcon, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QTabWidget, QVBoxLayout, QHBoxLayout,
    QFileDialog, QMessageBox, QStatusBar, QScrollArea, QPushButton,
    QProgressBar, QLabel, QCheckBox, QComboBox,
)

from ..defaults import create_default_state, create_empty_state
from .. import project_io
from ..i18n import tr
from ..settings import SETTINGS
from .widgets import InputPanel, ResultsPanel
from .plots import BeamDiagramCanvas, SchemaCanvas, SectionCanvas, StressCanvas, MarginCanvas
from .worker import ComputeWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._update_title()
        self._apply_icon()
        self.resize(1500, 950)
        self.state = create_empty_state()
        self.result = None
        self.reserves = []
        self._parts_crit = []
        self._worker = None
        self._dirty = True
        self._sec_sig = None

        self._build_ui()
        self._build_menu()

        # vstupy se aktualizují real-time, těžký výpočet (VVÚ+MS) se spouští tlačítkem
        self.input_panel.changed.connect(self._on_input_changed)
        QShortcut(QKeySequence("F5"), self, activated=self.compute)

        # debounce pro živou aktualizaci náhledu průřezu
        self._sec_timer = QTimer(self)
        self._sec_timer.setSingleShot(True)
        self._sec_timer.setInterval(150)
        self._sec_timer.timeout.connect(self._live_update_section)

        self._live_update_section()
        self.compute()

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)

        # ── horní lišta: tlačítko Spočítat + přepínač VVÚ + progress bar ──
        bar = QHBoxLayout()
        self.compute_btn = QPushButton(tr("▶  Spočítat  (F5)"))
        self.compute_btn.setStyleSheet(
            "QPushButton{background:#1565c0;color:white;font-weight:bold;"
            "padding:6px 16px;border-radius:4px;}"
            "QPushButton:disabled{background:#9bb6d6;}")
        self.compute_btn.clicked.connect(self.compute)
        bar.addWidget(self.compute_btn)
        self.dirty_lbl = QLabel("")
        self.dirty_lbl.setStyleSheet("color:#c62828; font-weight:bold;")
        bar.addWidget(self.dirty_lbl)
        bar.addStretch(1)
        self.vvu_combined_cb = QCheckBox(tr("VVÚ v jednom grafu"))
        self.vvu_combined_cb.setChecked(SETTINGS.vvu_combined)
        self.vvu_combined_cb.toggled.connect(self._on_vvu_combined)
        bar.addWidget(self.vvu_combined_cb)
        self.vvu_deform_cb = QCheckBox(tr("Zobrazit průhyb a pootočení"))
        self.vvu_deform_cb.setChecked(SETTINGS.vvu_show_deform)
        self.vvu_deform_cb.toggled.connect(self._on_vvu_deform)
        bar.addWidget(self.vvu_deform_cb)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(260)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        bar.addWidget(self.progress)
        root.addLayout(bar)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        self.input_panel = InputPanel(self.state)
        self.input_panel.setMinimumWidth(340)
        self.input_panel.setMaximumWidth(440)
        splitter.addWidget(self.input_panel)

        # střed: nahoře schéma nosníku (1/3), dole scrollovatelné VVÚ grafy (2/3)
        center = QSplitter(Qt.Vertical)
        self.schema_canvas = SchemaCanvas()
        center.addWidget(self.schema_canvas)
        self.beam_canvas = BeamDiagramCanvas()
        beam_scroll = QScrollArea()
        beam_scroll.setWidgetResizable(True)
        beam_scroll.setWidget(self.beam_canvas)
        center.addWidget(beam_scroll)
        center.setStretchFactor(0, 1)
        center.setStretchFactor(1, 2)
        center.setSizes([220, 600])
        splitter.addWidget(center)

        # pravý: taby
        self.tabs = QTabWidget()

        # tab napjatost
        stress_tab = QWidget()
        sv = QVBoxLayout(stress_tab)
        psel = QHBoxLayout()
        psel.addWidget(QLabel(tr("Úsek:")))
        self.part_sel = QComboBox()
        self.part_sel.currentIndexChanged.connect(self._on_part_selected)
        psel.addWidget(self.part_sel, 1)
        sv.addLayout(psel)
        top = QHBoxLayout()
        self.section_canvas = SectionCanvas()
        top.addWidget(self.section_canvas, 1)
        self.results_panel = ResultsPanel()
        top.addWidget(self.results_panel, 1)
        sv.addLayout(top, 1)
        self.stress_canvas = StressCanvas()
        sv.addWidget(self.stress_canvas, 1)
        self.tabs.addTab(stress_tab, tr("Průřez a napjatost"))

        # tab výsledky (souhrnný protokol) – uprostřed
        from PySide6.QtWidgets import QTextEdit
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setStyleSheet("font-family:'Consolas',monospace; font-size:11px;")
        self.tabs.addTab(self.results_text, tr("Výsledky"))

        # tab posouzení – poslední
        margin_tab = QWidget()
        mv = QVBoxLayout(margin_tab)
        self.margin_canvas = MarginCanvas()
        mv.addWidget(self.margin_canvas)
        self.tabs.addTab(margin_tab, tr("Posouzení (RF)"))

        splitter.addWidget(self.tabs)
        splitter.setSizes([400, 600, 500])
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    def _build_menu(self):
        """Menu se staví jen jednou; při změně jazyka se aktualizují texty
        existujících akcí (`_retranslate_menu`) – žádné mazání QAction
        (mazání uvnitř události menu by způsobilo pád)."""
        mb = self.menuBar()
        self._menu_file = mb.addMenu("")
        m = self._menu_file
        self._a_new = QAction(self); self._a_new.triggered.connect(self.new_project); m.addAction(self._a_new)
        self._a_open = QAction(self); self._a_open.setShortcut(QKeySequence.Open)
        self._a_open.triggered.connect(self.open_project); m.addAction(self._a_open)
        self._a_save = QAction(self); self._a_save.setShortcut(QKeySequence.Save)
        self._a_save.triggered.connect(self.save_project); m.addAction(self._a_save)
        m.addSeparator()
        self._a_nos = QAction(self); self._a_nos.triggered.connect(self.import_nos); m.addAction(self._a_nos)
        m.addSeparator()
        self._a_exp = QAction(self); self._a_exp.triggered.connect(self.export_report); m.addAction(self._a_exp)
        self._a_png = QAction(self); self._a_png.triggered.connect(self.export_png); m.addAction(self._a_png)
        m.addSeparator()
        self._a_quit = QAction(self); self._a_quit.triggered.connect(self.close); m.addAction(self._a_quit)

        self._a_demo = QAction(self); self._a_demo.triggered.connect(self.load_demo); mb.addAction(self._a_demo)
        self._a_set = QAction(self); self._a_set.triggered.connect(self.open_settings); mb.addAction(self._a_set)
        self._a_about = QAction(self); self._a_about.triggered.connect(self.open_about); mb.addAction(self._a_about)
        self._retranslate_menu()

    def _retranslate_menu(self):
        self._menu_file.setTitle(tr("&Soubor"))
        self._a_new.setText(tr("Nový"))
        self._a_open.setText(tr("Otevřít…"))
        self._a_save.setText(tr("Uložit jako…"))
        self._a_nos.setText(tr("Importovat Ministatik (*.nos)…"))
        self._a_exp.setText(tr("Export protokolu (TXT)…"))
        self._a_png.setText(tr("Export VVÚ (PNG)…"))
        self._a_quit.setText(tr("Konec"))
        self._a_demo.setText(tr("Demo nosník"))
        self._a_set.setText(tr("Nastavení…"))
        self._a_about.setText(tr("O programu"))

    def _update_title(self):
        from .. import __version__
        self.setWindowTitle(f"{tr('BEAMER – statická analýza nosníku')}  v{__version__}")

    def _apply_icon(self):
        from .. import icon_path
        for ext in ("ico", "png"):
            p = icon_path(ext)
            if os.path.exists(p):
                self.setWindowIcon(QIcon(p))
                break

    def open_about(self):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDialogButtonBox
        from .. import __version__, icon_path
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("O programu"))
        dlg.setMinimumWidth(440)
        v = QVBoxLayout(dlg)
        top = QHBoxLayout()
        ip = icon_path("png")
        if os.path.exists(ip):
            lbl_icon = QLabel()
            lbl_icon.setPixmap(QPixmap(ip).scaledToWidth(72, Qt.SmoothTransformation))
            top.addWidget(lbl_icon, 0, Qt.AlignTop)
        desc = tr("Statická analýza přímého nosníku a posouzení napjatosti po průřezu. "
                  "Letecké konstrukční výpočty (VVÚ, průhyb, RF).")
        txt = QLabel(
            f"<h3>BEAMER&nbsp;&nbsp;v{__version__}</h3>"
            f"<p>{desc}</p>"
            f"<p>© mrSpringpeace</p>")
        txt.setOpenExternalLinks(True)
        txt.setWordWrap(True)
        top.addWidget(txt, 1)
        v.addLayout(top)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.accept)
        bb.accepted.connect(dlg.accept)
        v.addWidget(bb)
        if os.path.exists(icon_path("ico")):
            dlg.setWindowIcon(QIcon(icon_path("ico")))
        dlg.exec()

    def open_settings(self):
        from .settings_dialog import SettingsDialog
        lang_before = SETTINGS.language
        dlg = SettingsDialog(self)
        dlg.display_changed.connect(self._on_display_settings)
        dlg.exec()
        # Přestavbu rozhraní po změně jazyka odložíme až po doběhnutí události
        # menu (jinak by se přestavovalo/maláo menu uvnitř jeho vlastní akce → pád).
        if SETTINGS.language != lang_before:
            QTimer.singleShot(0, self._retranslate)

    def _on_display_settings(self):
        # formát čísel / sloučené VVÚ → překreslit bez přepočtu
        self.beam_canvas.combined = SETTINGS.vvu_combined
        self.beam_canvas.show_deform = SETTINGS.vvu_show_deform
        for cb, val in ((self.vvu_combined_cb, SETTINGS.vvu_combined),
                        (self.vvu_deform_cb, SETTINGS.vvu_show_deform)):
            if cb.isChecked() != val:
                cb.blockSignals(True)
                cb.setChecked(val)
                cb.blockSignals(False)
        self._sec_sig = None
        self._live_update_section()
        self._refresh_views()

    def _on_vvu_combined(self, on):
        SETTINGS.vvu_combined = bool(on)
        SETTINGS.save()
        self.beam_canvas.combined = bool(on)
        self.beam_canvas.plot(self.state, self.result)

    def _on_vvu_deform(self, on):
        SETTINGS.vvu_show_deform = bool(on)
        SETTINGS.save()
        self.beam_canvas.show_deform = bool(on)
        self.beam_canvas.plot(self.state, self.result)

    def _retranslate(self):
        """Přestaví UI po změně jazyka."""
        self._update_title()
        self._retranslate_menu()
        self.compute_btn.setText(tr("▶  Spočítat  (F5)"))
        self.vvu_combined_cb.setText(tr("VVÚ v jednom grafu"))
        self.vvu_deform_cb.setText(tr("Zobrazit průhyb a pootočení"))
        self.tabs.setTabText(0, tr("Průřez a napjatost"))
        self.tabs.setTabText(1, tr("Výsledky"))
        self.tabs.setTabText(2, tr("Posouzení (RF)"))
        self.input_panel.reload_from_state()
        self._sec_sig = None
        self._live_update_section()
        self._refresh_views()

    # ── přepočet (worker thread) ──
    def _on_input_changed(self):
        """Vstup se změnil – real-time překreslí schéma a (debounced) náhled
        průřezu + charakteristiky; VVÚ a MS se počítají až tlačítkem."""
        self._dirty = True
        self.dirty_lbl.setText("● změněno – stiskněte Spočítat")
        self.results_panel.clear_analysis()
        try:
            self.schema_canvas.plot(self.state)   # živý náhled zadání (bez reakcí)
        except Exception:
            pass
        self._sec_timer.start()

    def _live_section(self):
        """Postaví reprezentativní průřez pro náhled (rychlý, bez FEM).
        FEM přesné hodnoty IT/Iω/střed smyku se počítají až při výpočtu
        (Spočítat) nebo v editoru průřezu tlačítkem „Spočítat (FEM)"."""
        from ..section import build_section
        from ..sections_along import segment_at
        try:
            if self.state.section_segments:
                seg = segment_at(self.state, self.state.length/2)
                return build_section(seg.sec1, fem=False), True
            return build_section(self.state.cross_section, fem=False), False
        except Exception:
            return None, False

    def _section_signature(self):
        import json
        cs = self.state.cross_section
        segs = [(s.x1, s.x2, s.sec1.type, dict(s.sec1.params), s.sec1.polygon_points,
                 (s.sec2.type if s.sec2 else None),
                 (dict(s.sec2.params) if s.sec2 else None),
                 (s.sec2.polygon_points if s.sec2 else None))
                for s in self.state.section_segments]
        return json.dumps([self.state.variable_section, self.state.length, cs.type,
                           dict(cs.params), cs.polygon_points, segs], default=str, sort_keys=True)

    def _live_update_section(self):
        """Aktualizuje náhled průřezu + charakteristiky, jen pokud se průřez
        skutečně změnil (vyhne se zbytečnému FEM přepočtu při editaci podpor)."""
        sig = self._section_signature()
        if sig == self._sec_sig:
            return
        self._sec_sig = sig
        sec, variable = self._live_section()
        title = f"— {tr('Průřez (uprostřed)')} —" if variable else tr("— Průřez —")
        self.section_canvas.plot(sec)
        self.results_panel.set_section(sec, title)

    def compute(self):
        if self._worker is not None and self._worker.isRunning():
            return
        self.compute_btn.setEnabled(False)
        self.progress.setValue(0)
        self.statusBar().showMessage(tr("Počítám…"))
        self._worker = ComputeWorker(self.state, n_stations=120)
        self._worker.progress.connect(lambda f: self.progress.setValue(int(f*100)))
        self._worker.done.connect(self._on_compute_done)
        self._worker.start()

    def _on_compute_done(self, result, reserves):
        self.result = result
        self.reserves = reserves
        self._dirty = False
        self.dirty_lbl.setText("")
        self.compute_btn.setEnabled(True)
        self.progress.setValue(100)
        self._refresh_views()

    def _refresh_views(self):
        self.schema_canvas.plot(self.state, self.result)   # schéma + reakce
        self.beam_canvas.plot(self.state, self.result)
        # kritický řez/napětí na každém úseku → přepínač úseku
        from ..analysis import critical_per_part
        self._parts_crit = (critical_per_part(self.state, self.reserves)
                            if self.reserves else [])
        self._refresh_part_selector()
        self._render_selected_part()
        self.margin_canvas.plot(self.reserves)
        self.results_panel.set_analysis(self.result, self.state, self.reserves)
        try:
            from ..report import build_report
            self.results_text.setPlainText(build_report(self.state, self.result, self.reserves))
        except Exception:
            pass
        if self.result and not self.result.is_stable:
            self.statusBar().showMessage("⚠ " + self.result.error_message)
        else:
            self.statusBar().showMessage(tr("Přepočítáno."))

    def _refresh_part_selector(self):
        self.part_sel.blockSignals(True)
        cur = self.part_sel.currentIndex()
        self.part_sel.clear()
        for cp in self._parts_crit:
            rf = cp["crit"].RF if cp.get("crit") else float("nan")
            self.part_sel.addItem(
                f"{tr('Úsek')} {cp['idx']+1}  ({cp['x1']:.0f}–{cp['x2']:.0f}) · "
                f"{cp['material']} · RF={rf:.2f}", cp["idx"])
        if 0 <= cur < self.part_sel.count():
            self.part_sel.setCurrentIndex(cur)
        self.part_sel.blockSignals(False)

    def _on_part_selected(self, _):
        self._render_selected_part()

    def _render_selected_part(self):
        sec = self.result.section if self.result else None
        resolver = getattr(self.result, "resolver", None) if self.result else None
        if (self.result and self.result.is_stable and self.result.points
                and self._parts_crit and resolver is not None):
            idx = max(0, self.part_sel.currentIndex())
            cp = self._parts_crit[min(idx, len(self._parts_crit)-1)]
            crit = cp.get("crit")
            xq = crit.x if crit else (cp["x1"]+cp["x2"])/2
            pcrit = min(self.result.points, key=lambda p: abs(p.x - xq))
            try:
                sec_crit = resolver.at(pcrit.x)
            except Exception:
                sec_crit = sec
            self.section_canvas.plot(sec_crit)
            self.stress_canvas.plot(sec_crit, pcrit.N, pcrit.V, pcrit.M, pcrit.Mk)
            self.results_panel.set_section(
                sec_crit, f"— {tr('Úsek')} {cp['idx']+1} · {tr('kritický řez')} x={pcrit.x:.0f} —")
        else:
            self.section_canvas.plot(sec)
            self.stress_canvas.plot(sec, 0, 0, 0, 0)

    # ── soubor ──
    def new_project(self):
        self._load_state(create_empty_state())

    def load_demo(self):
        self._load_state(create_default_state())

    def _load_state(self, state):
        from ..defaults import ensure_parts
        ensure_parts(state)
        self.state = state
        self.input_panel.state = self.state
        self.input_panel.reload_from_state()
        # `changed` je signál InputPanelu (přežije reload_from_state),
        # spojení z __init__ zůstává – nepřipojovat znovu (duplikace).
        self._sec_sig = None
        self._live_update_section()
        self.compute()

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Otevřít projekt"), "", "BEAMER (*.json)")
        if not path:
            return
        try:
            state = project_io.load_project(path)
        except Exception as e:
            QMessageBox.critical(self, tr("Chyba"), tr("Nelze načíst: ") + str(e))
            return
        self._load_state(state)

    def import_nos(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Importovat Ministatik (*.nos)…"),
                                              "", "Ministatik (*.nos)")
        if not path:
            return
        from .. import nos_io
        try:
            state = nos_io.load_nos(path)
        except Exception as e:
            QMessageBox.critical(self, tr("Chyba"), tr("Nelze importovat: ") + str(e))
            return
        self._load_state(state)
        self.statusBar().showMessage(tr("Importováno z Ministatik: ") + path)

    def save_project(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Uložit projekt"), "projekt.json", "BEAMER (*.json)")
        if not path:
            return
        try:
            project_io.save_project(self.state, path)
            self.statusBar().showMessage(tr("Uloženo: ") + path)
        except Exception as e:
            QMessageBox.critical(self, tr("Chyba"), tr("Nelze uložit: ") + str(e))

    def export_report(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Export protokolu"), "protokol.txt", "Text (*.txt)")
        if not path:
            return
        from ..report import build_report
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(build_report(self.state, self.result, self.reserves))
            self.statusBar().showMessage(tr("Protokol uložen: ") + path)
        except Exception as e:
            QMessageBox.critical(self, tr("Chyba"), tr("Nelze exportovat: ") + str(e))

    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Export VVÚ"), "vvu.png", "PNG (*.png)")
        if not path:
            return
        self.beam_canvas.fig.savefig(path, dpi=150)
        self.statusBar().showMessage(tr("Obrázek uložen: ") + path)
