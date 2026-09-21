from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,QComboBox,QDialog,QDialogButtonBox,QDoubleSpinBox,QFileDialog,
    QFormLayout,QHBoxLayout,QLineEdit,QMessageBox,QPushButton,QScrollArea,
    QSpinBox,QVBoxLayout,QWidget
)
from ..analysis_templates import (
    expand_cyclic_protocol,
    parse_cyclic_protocol_text,
    parse_cyclic_targets_text,
)
from ..project import AnalysisSettingsData

def fs(value,low=-1e20,high=1e20):
    w=QDoubleSpinBox(); w.setDecimals(10); w.setRange(low,high); w.setValue(float(value)); return w

class AnalysisDialog(QDialog):
    def __init__(
        self,
        analysis=None,
        *,
        next_tag=1,
        default_node=1,
        analysis_type=None,
        ndf=6,
        plain_patterns=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Analysis Settings")
        self.setModal(True)
        self.setSizeGripEnabled(True)
        self.resize(500,620)

        root=QVBoxLayout(self)
        form_host=QWidget()
        form=QFormLayout(form_host)
        self.form = form
        self._row_widgets = {}
        self.ndf = max(1, min(int(ndf), 6))
        self.plain_patterns = {
            int(tag): str(name)
            for tag, name in dict(plain_patterns or {}).items()
        }
        self.tag=QSpinBox(); self.tag.setRange(1,2147483647); self.tag.setValue(analysis.tag if analysis else next_tag)
        default_kind = (
            analysis.analysis_type
            if analysis
            else str(analysis_type or "Static")
        )
        default_name = (
            analysis.name
            if analysis
            else f"{default_kind} {next_tag}"
        )
        self.name=QLineEdit(default_name)
        self.kind=QComboBox(); self.kind.addItems(["Static","Pushover","Cyclic","Transient","Modal"]); self.kind.setCurrentText(default_kind)
        self.constraints=QComboBox(); self.constraints.addItems(["Transformation","Plain"]); self.constraints.setCurrentText(analysis.constraints_handler if analysis else "Transformation")
        self.numberer=QComboBox(); self.numberer.addItems(["RCM","Plain"]); self.numberer.setCurrentText(analysis.numberer if analysis else "RCM")
        self.system=QComboBox(); self.system.addItems(["UmfPack","BandGeneral","ProfileSPD","SparseGeneral"]); self.system.setCurrentText(analysis.system if analysis else "UmfPack")
        self.system_pivoting=QCheckBox("Use pivoting (-piv)")
        self.system_pivoting.setChecked(
            analysis.system_pivoting if analysis else False
        )
        self.system_pivoting.setToolTip(
            "Preserve OpenSees SparseGeneral -piv for models that require "
            "partial pivoting."
        )
        self.system_pivoting.setEnabled(
            self.system.currentText() == "SparseGeneral"
        )
        self.system.currentTextChanged.connect(
            lambda text: self.system_pivoting.setEnabled(
                text == "SparseGeneral"
            )
        )
        self.test=QComboBox(); self.test.addItems(["NormDispIncr","NormUnbalance","EnergyIncr"]); self.test.setCurrentText(analysis.test if analysis else "NormDispIncr")
        self.tol=fs(analysis.tolerance if analysis else 1e-8,1e-16,1e10)
        self.max_iter=QSpinBox(); self.max_iter.setRange(1,100000); self.max_iter.setValue(analysis.max_iterations if analysis else 50)
        self.algorithm=QComboBox(); self.algorithm.addItems(["Linear","Newton","NewtonLineSearch","ModifiedNewton"]); self.algorithm.setCurrentText(analysis.algorithm if analysis else "Newton")
        self.algorithm_initial=QCheckBox(
            "Use initial tangent (-initial)"
        )
        self.algorithm_initial.setChecked(
            analysis.algorithm_initial if analysis else False
        )
        self.algorithm_initial.setToolTip(
            "OpenSees ModifiedNewton -initial: form the tangent from the "
            "initial stiffness instead of the current tangent."
        )
        self.algorithm_initial.setEnabled(
            self.algorithm.currentText() == "ModifiedNewton"
        )
        self.algorithm.currentTextChanged.connect(
            lambda text: self.algorithm_initial.setEnabled(
                text == "ModifiedNewton"
            )
        )
        self.integrator=QComboBox()
        self._initial_integrator=(analysis.integrator if analysis else None)
        self.integrator.setToolTip(
            "Controls the analysis stepping/integration scheme. Available choices "
            "depend on the selected analysis type."
        )
        self.steps=QSpinBox(); self.steps.setRange(1,10000000); self.steps.setValue(analysis.steps if analysis else 10)
        self.load_inc=fs(analysis.load_increment if analysis else 0.1,-1e20,1e20)
        self.control_node=QSpinBox(); self.control_node.setRange(1,2147483647); self.control_node.setValue(analysis.control_node if analysis else default_node)
        self.control_dof=QComboBox()
        dof_names=("UX","UY","UZ","RX","RY","RZ")
        for i,n in enumerate(dof_names[:self.ndf],1):
            self.control_dof.addItem(f"{n} ({i})",i)
        if analysis and analysis.control_dof > self.ndf:
            self.control_dof.addItem(
                f"DOF {analysis.control_dof} (outside current ndf={self.ndf})",
                analysis.control_dof,
            )
        if analysis:
            i=self.control_dof.findData(analysis.control_dof)
            if i>=0:self.control_dof.setCurrentIndex(i)
        self.disp_inc=fs(analysis.displacement_increment if analysis else 0.001,-1e20,1e20)
        cyclic_values=(
            analysis.cyclic_targets
            if analysis
            else [0.005,-0.005,0.01,-0.01,0.0]
        )
        self.cyclic_targets=QLineEdit(
            ", ".join(f"{value:g}" for value in cyclic_values)
        )
        self.cyclic_targets.setPlaceholderText(
            "e.g. 0.005, -0.005, 0.01, -0.01, 0"
        )
        self.cyclic_targets.setToolTip(
            "Absolute control-displacement targets, visited in order."
        )
        self.cyclic_protocol_mode=QComboBox()
        self.cyclic_protocol_mode.addItem(
            "Absolute targets · one column",
            "targets",
        )
        self.cyclic_protocol_mode.addItem(
            "Amplitude + cycles · two columns",
            "amplitude_cycles",
        )
        self.cyclic_import_button=QPushButton("Import CSV/TXT...")
        self.cyclic_import_button.setToolTip(
            "Import a cyclic protocol. Absolute-target mode reads column 1; "
            "Amplitude+cycles mode reads columns 1 and 2 and expands reversals."
        )
        cyclic_import_host=QWidget()
        cyclic_import_layout=QHBoxLayout(cyclic_import_host)
        cyclic_import_layout.setContentsMargins(0,0,0,0)
        cyclic_import_layout.addWidget(self.cyclic_protocol_mode,1)
        cyclic_import_layout.addWidget(self.cyclic_import_button)
        self.cyclic_protocol_import=cyclic_import_host
        self.cyclic_inc=fs(
            analysis.cyclic_increment if analysis else 0.001,
            1e-12,
            1e20,
        )
        self.cyclic_inc.setToolTip(
            "Maximum absolute displacement increment used to subdivide each branch."
        )
        self.dt=fs(analysis.dt if analysis else 0.01,1e-12,1e20)
        self.gamma=fs(
            analysis.gamma if analysis else 0.5,
            0.5,
            1e20,
        )
        self.gamma.setToolTip(
            "OpenSees Newmark uses gamma=0.5 for no numerical damping; "
            "gamma>0.5 adds numerical damping. Values below 0.5 are not allowed."
        )
        self.beta=fs(
            analysis.beta if analysis else 0.25,
            1e-12,
            1e20,
        )
        self.beta.setToolTip(
            "OpenSeesPy Studio uses the default displacement-form Newmark "
            "integrator, so beta must be positive."
        )
        self.hht_alpha=fs(
            analysis.hht_alpha if analysis else 0.9,
            2.0 / 3.0,
            1.0,
        )
        self.hht_alpha.setToolTip(
            "OpenSees HHT alpha should be between 2/3 and 1.0; "
            "alpha=1.0 reduces to Newmark."
        )
        self.generalized_alpha_m=fs(
            analysis.generalized_alpha_m if analysis else 1.0,
            0.5,
            1e20,
        )
        self.generalized_alpha_f=fs(
            analysis.generalized_alpha_f if analysis else 1.0,
            0.5,
            1e20,
        )
        self.generalized_alpha_m.setToolTip(
            "For the default OpenSees GeneralizedAlpha scheme, use "
            "alphaM >= alphaF >= 0.5."
        )
        self.generalized_alpha_f.setToolTip(
            "For the default OpenSees GeneralizedAlpha scheme, use "
            "alphaM >= alphaF >= 0.5."
        )
        self.arc_length_s=fs(
            analysis.arc_length_s if analysis else 0.01,
            1e-12,
            1e20,
        )
        self.arc_length_alpha=fs(
            analysis.arc_length_alpha if analysis else 1.0,
            1e-12,
            1e20,
        )
        self.damping_ratio=fs(
            analysis.rayleigh_damping_ratio if analysis else 0.0,
            0.0,
            0.999999,
        )
        self.damping_mode_i=QSpinBox(); self.damping_mode_i.setRange(1,10000)
        self.damping_mode_i.setValue(analysis.rayleigh_mode_i if analysis else 1)
        self.damping_mode_j=QSpinBox(); self.damping_mode_j.setRange(1,10000)
        self.damping_mode_j.setValue(analysis.rayleigh_mode_j if analysis else 3)
        self.preload_gravity=QCheckBox(
            "Preload existing Plain patterns, then hold with loadConst"
        )
        self.preload_gravity.setChecked(
            analysis.preload_gravity if analysis else False
        )
        self.gravity_steps=QSpinBox(); self.gravity_steps.setRange(1,100000)
        self.gravity_steps.setValue(analysis.gravity_steps if analysis else 10)
        self.deferred_patterns=QLineEdit(
            ", ".join(
                str(tag)
                for tag in (
                    analysis.deferred_pattern_tags if analysis else []
                )
            )
        )
        self.deferred_patterns.setPlaceholderText(
            "e.g. 3  (driving lateral / excitation pattern)"
        )
        self.driver_mode=QComboBox()
        self.driver_mode.addItem(
            "Auto-generate reference pattern",
            "auto",
        )
        self.driver_mode.addItem(
            "Use existing Plain pattern",
            "existing",
        )
        self.driver_mode.setToolTip(
            "DisplacementControl requires a nonzero reference load pattern. "
            "Auto-generate is the safe default for Static, Pushover, and Cyclic."
        )
        self.driver_pattern=QComboBox()
        for pattern_tag, pattern_name in sorted(self.plain_patterns.items()):
            self.driver_pattern.addItem(
                f"{pattern_tag} · {pattern_name}",
                pattern_tag,
            )
        self.driver_distribution=QComboBox()
        self.driver_distribution.addItems(
            ["Uniform", "Triangular", "Mass proportional"]
        )
        initial_driver_tag = None
        if (
            analysis is not None
            and (
                analysis.analysis_type in {"Pushover", "Cyclic"}
                or (
                    analysis.analysis_type == "Static"
                    and analysis.integrator == "DisplacementControl"
                )
            )
            and analysis.deferred_pattern_tags
        ):
            initial_driver_tag = int(analysis.deferred_pattern_tags[0])
        if initial_driver_tag in self.plain_patterns:
            self.driver_mode.setCurrentIndex(
                self.driver_mode.findData("existing")
            )
            index = self.driver_pattern.findData(initial_driver_tag)
            if index >= 0:
                self.driver_pattern.setCurrentIndex(index)
        else:
            self.driver_mode.setCurrentIndex(
                self.driver_mode.findData("auto")
            )
        self.driver_distribution.setCurrentText(
            "Triangular"
            if default_kind == "Pushover"
            else "Uniform"
        )
        self.modes=QSpinBox(); self.modes.setRange(1,10000); self.modes.setValue(analysis.num_modes if analysis else 3)
        self.eigen_solver=QComboBox()
        self.eigen_solver.addItem("ARPACK · general / sparse", "-genBandArpack")
        self.eigen_solver.addItem("Full General LAPACK", "-fullGenLapack")
        self.eigen_solver.addItem("Symmetric Band LAPACK", "-symmBandLapack")
        if analysis:
            index=self.eigen_solver.findData(analysis.eigen_solver)
            if index>=0:self.eigen_solver.setCurrentIndex(index)
        self.recovery=QCheckBox("Try NewtonLineSearch / ModifiedNewton / Newton on failed step"); self.recovery.setChecked(analysis.recovery if analysis else True)
        self.adaptive=QCheckBox("Adaptive step size / automatic cutback")
        self.adaptive.setChecked(analysis.adaptive_step if analysis else False)
        self.cutback=fs(
            analysis.adaptive_cutback_factor if analysis else 0.5,
            0.01,
            0.99,
        )
        self.min_factor=fs(
            analysis.adaptive_min_factor if analysis else 0.125,
            1e-6,
            1.0,
        )
        self.growth=fs(
            analysis.adaptive_growth_factor if analysis else 1.5,
            1.0,
            10.0,
        )
        self.easy_iter=QSpinBox()
        self.easy_iter.setRange(1,100000)
        self.easy_iter.setValue(
            analysis.adaptive_easy_iterations if analysis else 4
        )
        self.grow_after=QSpinBox()
        self.grow_after.setRange(1,100000)
        self.grow_after.setValue(
            analysis.adaptive_growth_after if analysis else 3
        )
        self.live_convergence=QCheckBox("Live convergence monitor (iteration-level)")
        self.live_convergence.setChecked(
            analysis.live_convergence if analysis else True
        )
        self.live_convergence.setToolTip(
            "Streams every convergence-test iteration to the GUI. "
            "Disable for very long analyses if console I/O becomes excessive."
        )
        self.external_console=QCheckBox("Show external solver terminal (Windows debug)")
        self.external_console.setChecked(analysis.show_external_console if analysis else False)
        self.external_console.setToolTip(
            "Opens a separate PowerShell window that mirrors the live solver log. "
            "The Studio worker still runs in its isolated process."
        )
        fields=(
            ("tag","Tag",self.tag),
            ("name","Name",self.name),
            ("kind","Analysis type",self.kind),
            ("constraints","Constraints",self.constraints),
            ("numberer","Numberer",self.numberer),
            ("system","System",self.system),
            (
                "system_pivoting",
                "System option",
                self.system_pivoting,
            ),
            ("test","Test",self.test),
            ("tol","Tolerance",self.tol),
            ("max_iter","Max iterations",self.max_iter),
            ("algorithm","Algorithm",self.algorithm),
            (
                "algorithm_initial",
                "Algorithm option",
                self.algorithm_initial,
            ),
            ("integrator","Integrator",self.integrator),
            ("steps","Steps",self.steps),
            ("load_inc","Load increment",self.load_inc),
            ("control_node","Control node",self.control_node),
            ("control_dof","Control DOF",self.control_dof),
            ("disp_inc","Disp. increment",self.disp_inc),
            ("cyclic_targets","Cyclic targets",self.cyclic_targets),
            ("cyclic_protocol_import","Protocol import",self.cyclic_protocol_import),
            ("cyclic_inc","Cyclic max increment",self.cyclic_inc),
            ("dt","Time step dt",self.dt),
            ("gamma","Newmark gamma",self.gamma),
            ("beta","Newmark beta",self.beta),
            ("hht_alpha","HHT alpha",self.hht_alpha),
            ("generalized_alpha_m","Generalized-alpha alphaM",self.generalized_alpha_m),
            ("generalized_alpha_f","Generalized-alpha alphaF",self.generalized_alpha_f),
            ("arc_length_s","ArcLength s",self.arc_length_s),
            ("arc_length_alpha","ArcLength alpha",self.arc_length_alpha),
            ("damping_ratio","Rayleigh damping ratio",self.damping_ratio),
            ("damping_mode_i","Rayleigh mode i",self.damping_mode_i),
            ("damping_mode_j","Rayleigh mode j",self.damping_mode_j),
            ("modes","Number of modes",self.modes),
            ("eigen_solver","Eigen solver",self.eigen_solver),
            ("preload_gravity","Gravity preload",self.preload_gravity),
            ("gravity_steps","Gravity preload steps",self.gravity_steps),
            ("driver_mode","Driving load",self.driver_mode),
            ("driver_pattern","Existing Plain pattern",self.driver_pattern),
            ("driver_distribution","Auto load distribution",self.driver_distribution),
            ("deferred_patterns","Excitation pattern tag(s)",self.deferred_patterns),
            ("recovery","Recovery",self.recovery),
            ("adaptive","Adaptive step",self.adaptive),
            ("cutback","Cutback factor",self.cutback),
            ("min_factor","Minimum factor",self.min_factor),
            ("growth","Growth factor",self.growth),
            ("easy_iter","Easy if iterations <=",self.easy_iter),
            ("grow_after","Grow after easy steps",self.grow_after),
            ("live_convergence","Live convergence",self.live_convergence),
            ("external_console","External terminal",self.external_console),
        )
        for key,label,w in fields:
            form.addRow(label+":",w)
            self._row_widgets[key]=w

        self.scroll=QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(form_host)
        root.addWidget(self.scroll,1)

        b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        root.addWidget(b)
        self.kind.currentTextChanged.connect(self._sync)
        self.cyclic_import_button.clicked.connect(
            self._import_cyclic_protocol
        )
        self.integrator.currentTextChanged.connect(
            lambda _text: self._sync(self.kind.currentText())
        )
        self.preload_gravity.toggled.connect(
            lambda _checked: self._sync(self.kind.currentText())
        )
        self.driver_mode.currentIndexChanged.connect(
            lambda _index: self._sync(self.kind.currentText())
        )
        self.adaptive.toggled.connect(
            lambda _checked: self._sync(self.kind.currentText())
        )
        self.damping_ratio.valueChanged.connect(
            lambda _value: self._sync(self.kind.currentText())
        )
        self._sync(self.kind.currentText())

    def _set_row_visible(self, key, visible):
        widget=self._row_widgets[key]
        widget.setVisible(bool(visible))
        label=self.form.labelForField(widget)
        if label is not None:
            label.setVisible(bool(visible))

    def _sync_integrator(self, kind):
        options = {
            "Static": ["LoadControl", "DisplacementControl", "ArcLength"],
            "Pushover": ["DisplacementControl"],
            "Cyclic": ["DisplacementControl"],
            "Transient": ["Newmark", "HHT", "GeneralizedAlpha"],
            "Modal": ["None"],
        }[kind]
        defaults = {
            "Static": "LoadControl",
            "Pushover": "DisplacementControl",
            "Cyclic": "DisplacementControl",
            "Transient": "Newmark",
            "Modal": "None",
        }
        current=self.integrator.currentText()
        desired=current if current in options else defaults[kind]
        if self._initial_integrator in options:
            desired=self._initial_integrator
            self._initial_integrator=None
        self.integrator.blockSignals(True)
        self.integrator.clear()
        self.integrator.addItems(options)
        self.integrator.setCurrentText(desired)
        self.integrator.blockSignals(False)
        self.integrator.setEnabled(kind in {"Static","Transient"})

    def _sync(self,kind):
        self._sync_integrator(kind)
        integrator=self.integrator.currentText()
        modal=kind=="Modal"
        transient=kind=="Transient"
        push=kind=="Pushover"
        cyclic=kind=="Cyclic"
        static=kind=="Static"
        non_modal=not modal
        static_dc=static and integrator=="DisplacementControl"
        staged=push or cyclic or transient or static_dc

        # Identity and core solver configuration are common to every analysis.
        common={
            "tag","name","kind","constraints","numberer","system",
            "integrator","external_console",
        }
        visible=set(common)

        # Convergence/solution strategy is irrelevant to a pure eigen analysis.
        if non_modal:
            visible.update({
                "test","tol","max_iter","algorithm",
                "recovery","adaptive","live_convergence",
            })

        if static:
            visible.add("steps")
            if integrator=="LoadControl":
                visible.add("load_inc")
            elif integrator=="DisplacementControl":
                visible.update({
                    "control_node","control_dof","disp_inc",
                    "driver_mode",
                })
                if self.driver_mode.currentData() == "existing":
                    visible.add("driver_pattern")
                else:
                    visible.add("driver_distribution")
            elif integrator=="ArcLength":
                visible.update({"arc_length_s","arc_length_alpha"})
        elif push:
            visible.update({
                "steps","control_node","control_dof","disp_inc",
            })
        elif cyclic:
            visible.update({
                "control_node","control_dof",
                "cyclic_targets","cyclic_protocol_import","cyclic_inc",
            })
        elif transient:
            visible.update({
                "steps","dt","damping_ratio",
            })
            if integrator=="Newmark":
                visible.update({"gamma","beta"})
            elif integrator=="HHT":
                visible.add("hht_alpha")
            elif integrator=="GeneralizedAlpha":
                visible.update({
                    "generalized_alpha_m","generalized_alpha_f",
                })
            if self.damping_ratio.value() > 0.0:
                visible.update({"damping_mode_i","damping_mode_j"})
        elif modal:
            visible.update({"modes","eigen_solver"})

        if staged:
            visible.add("preload_gravity")
            if push or cyclic:
                visible.add("driver_mode")
                if self.driver_mode.currentData() == "existing":
                    visible.add("driver_pattern")
                else:
                    visible.add("driver_distribution")
            elif transient:
                visible.add("deferred_patterns")
            if self.preload_gravity.isChecked():
                visible.add("gravity_steps")

        if non_modal and self.adaptive.isChecked():
            visible.update({
                "cutback","min_factor","growth",
                "easy_iter","grow_after",
            })

        for key in self._row_widgets:
            self._set_row_visible(key,key in visible)
    def _apply_cyclic_protocol_text(
        self,
        text: str,
        *,
        mode: str,
    ) -> list[float]:
        if mode == "amplitude_cycles":
            rows = parse_cyclic_protocol_text(
                text,
                amplitude_column=1,
                cycles_column=2,
            )
            targets = expand_cyclic_protocol(
                rows,
                finish_at_zero=True,
            )
        else:
            targets = parse_cyclic_targets_text(
                text,
                column=1,
            )
        self.cyclic_targets.setText(
            ", ".join(f"{value:g}" for value in targets)
        )
        return targets

    def _import_cyclic_protocol(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Cyclic Protocol",
            "",
            "Protocol (*.csv *.txt *.dat);;All files (*)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(
                encoding="utf-8",
                errors="replace",
            )
            self._apply_cyclic_protocol_text(
                text,
                mode=str(
                    self.cyclic_protocol_mode.currentData()
                    or "targets"
                ),
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Import Cyclic Protocol",
                str(exc),
            )

    def driving_load_config(self) -> dict[str, object]:
        kind = self.kind.currentText()
        is_static_dc = (
            kind == "Static"
            and self.integrator.currentText() == "DisplacementControl"
        )
        if kind not in {"Pushover", "Cyclic"} and not is_static_dc:
            return {"mode": "none"}
        mode = str(self.driver_mode.currentData() or "auto")
        return {
            "mode": mode,
            "distribution": self.driver_distribution.currentText(),
            "pattern_tag": (
                int(self.driver_pattern.currentData())
                if (
                    mode == "existing"
                    and self.driver_pattern.currentData() is not None
                )
                else None
            ),
        }

    def data(self):
        cyclic_targets=[]
        for raw in self.cyclic_targets.text().replace(";", ",").split(","):
            value=raw.strip()
            if value:
                cyclic_targets.append(float(value))
        deferred_pattern_tags=[]
        kind = self.kind.currentText()
        integrator = self.integrator.currentText()
        preload_supported = (
            kind in {"Pushover", "Cyclic", "Transient"}
            or (kind == "Static" and integrator == "DisplacementControl")
        )
        preload_gravity = (
            preload_supported and self.preload_gravity.isChecked()
        )
        if kind == "Transient":
            for raw in (
                self.deferred_patterns.text()
                .replace(";", ",")
                .replace(" ", ",")
                .split(",")
            ):
                value=raw.strip()
                if value:
                    deferred_pattern_tags.append(int(value))
        elif (
            kind in {"Pushover", "Cyclic"}
            or (
                kind == "Static"
                and self.integrator.currentText() == "DisplacementControl"
            )
        ):
            driver = self.driving_load_config()
            if driver["mode"] == "existing":
                pattern_tag = driver.get("pattern_tag")
                if pattern_tag is None:
                    raise ValueError(
                        "Choose an existing Plain driving load pattern."
                    )
                deferred_pattern_tags.append(int(pattern_tag))
        return AnalysisSettingsData(
            tag=self.tag.value(),name=self.name.text().strip() or f"Analysis {self.tag.value()}",
            analysis_type=self.kind.currentText(),constraints_handler=self.constraints.currentText(),
            numberer=self.numberer.currentText(),system=self.system.currentText(),
            system_pivoting=(
                self.system_pivoting.isChecked()
                and self.system.currentText() == "SparseGeneral"
            ),
            test=self.test.currentText(),
            tolerance=self.tol.value(),max_iterations=self.max_iter.value(),algorithm=self.algorithm.currentText(),
            algorithm_initial=(
                self.algorithm_initial.isChecked()
                and self.algorithm.currentText() == "ModifiedNewton"
            ),
            integrator=self.integrator.currentText(),
            steps=self.steps.value(),load_increment=self.load_inc.value(),control_node=self.control_node.value(),
            control_dof=int(self.control_dof.currentData()),displacement_increment=self.disp_inc.value(),
            cyclic_targets=cyclic_targets,cyclic_increment=self.cyclic_inc.value(),
            dt=self.dt.value(),gamma=self.gamma.value(),beta=self.beta.value(),
            hht_alpha=self.hht_alpha.value(),
            generalized_alpha_m=self.generalized_alpha_m.value(),
            generalized_alpha_f=self.generalized_alpha_f.value(),
            arc_length_s=self.arc_length_s.value(),
            arc_length_alpha=self.arc_length_alpha.value(),
            rayleigh_damping_ratio=self.damping_ratio.value(),
            rayleigh_mode_i=self.damping_mode_i.value(),
            rayleigh_mode_j=self.damping_mode_j.value(),
            preload_gravity=preload_gravity,
            gravity_steps=self.gravity_steps.value(),
            deferred_pattern_tags=deferred_pattern_tags,
            num_modes=self.modes.value(),
            eigen_solver=str(self.eigen_solver.currentData()),
            recovery=self.recovery.isChecked(),
            adaptive_step=self.adaptive.isChecked(),
            adaptive_cutback_factor=self.cutback.value(),
            adaptive_min_factor=self.min_factor.value(),
            adaptive_growth_factor=self.growth.value(),
            adaptive_easy_iterations=self.easy_iter.value(),
            adaptive_growth_after=self.grow_after.value(),
            live_convergence=self.live_convergence.isChecked(),
            show_external_console=self.external_console.isChecked()
        )
