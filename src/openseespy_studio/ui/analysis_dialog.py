from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,QComboBox,QDialog,QDialogButtonBox,QDoubleSpinBox,QFormLayout,
    QLineEdit,QScrollArea,QSpinBox,QVBoxLayout,QWidget
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
        self.system=QComboBox(); self.system.addItems(["UmfPack","BandGeneral","ProfileSPD"]); self.system.setCurrentText(analysis.system if analysis else "UmfPack")
        self.test=QComboBox(); self.test.addItems(["NormDispIncr","NormUnbalance","EnergyIncr"]); self.test.setCurrentText(analysis.test if analysis else "NormDispIncr")
        self.tol=fs(analysis.tolerance if analysis else 1e-8,1e-16,1e10)
        self.max_iter=QSpinBox(); self.max_iter.setRange(1,100000); self.max_iter.setValue(analysis.max_iterations if analysis else 50)
        self.algorithm=QComboBox(); self.algorithm.addItems(["Newton","NewtonLineSearch","ModifiedNewton"]); self.algorithm.setCurrentText(analysis.algorithm if analysis else "Newton")
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
        self.cyclic_inc=fs(
            analysis.cyclic_increment if analysis else 0.001,
            1e-12,
            1e20,
        )
        self.cyclic_inc.setToolTip(
            "Maximum absolute displacement increment used to subdivide each branch."
        )
        self.dt=fs(analysis.dt if analysis else 0.01,1e-12,1e20)
        self.gamma=fs(analysis.gamma if analysis else 0.5)
        self.beta=fs(analysis.beta if analysis else 0.25)
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
            ("test","Test",self.test),
            ("tol","Tolerance",self.tol),
            ("max_iter","Max iterations",self.max_iter),
            ("algorithm","Algorithm",self.algorithm),
            ("steps","Steps",self.steps),
            ("load_inc","Load increment",self.load_inc),
            ("control_node","Control node",self.control_node),
            ("control_dof","Control DOF",self.control_dof),
            ("disp_inc","Disp. increment",self.disp_inc),
            ("cyclic_targets","Cyclic targets",self.cyclic_targets),
            ("cyclic_inc","Cyclic max increment",self.cyclic_inc),
            ("dt","Time step dt",self.dt),
            ("gamma","Newmark gamma",self.gamma),
            ("beta","Newmark beta",self.beta),
            ("damping_ratio","Rayleigh damping ratio",self.damping_ratio),
            ("damping_mode_i","Rayleigh mode i",self.damping_mode_i),
            ("damping_mode_j","Rayleigh mode j",self.damping_mode_j),
            ("modes","Number of modes",self.modes),
            ("eigen_solver","Eigen solver",self.eigen_solver),
            ("preload_gravity","Gravity preload",self.preload_gravity),
            ("gravity_steps","Gravity preload steps",self.gravity_steps),
            ("deferred_patterns","Driving pattern tag(s)",self.deferred_patterns),
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
        self.preload_gravity.toggled.connect(
            lambda _checked: self._sync(self.kind.currentText())
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

    def _sync(self,kind):
        modal=kind=="Modal"
        transient=kind=="Transient"
        push=kind=="Pushover"
        cyclic=kind=="Cyclic"
        static=kind=="Static"
        non_modal=not modal
        staged=push or cyclic or transient

        # Identity and core solver configuration are common to every analysis.
        common={
            "tag","name","kind","constraints","numberer","system",
            "external_console",
        }
        visible=set(common)

        # Convergence/solution strategy is irrelevant to a pure eigen analysis.
        if non_modal:
            visible.update({
                "test","tol","max_iter","algorithm",
                "recovery","adaptive","live_convergence",
            })

        if static:
            visible.update({"steps","load_inc"})
        elif push:
            visible.update({
                "steps","control_node","control_dof","disp_inc",
            })
        elif cyclic:
            visible.update({
                "control_node","control_dof",
                "cyclic_targets","cyclic_inc",
            })
        elif transient:
            visible.update({
                "steps","dt","gamma","beta",
                "damping_ratio",
            })
            if self.damping_ratio.value() > 0.0:
                visible.update({"damping_mode_i","damping_mode_j"})
        elif modal:
            visible.update({"modes","eigen_solver"})

        if staged:
            visible.update({"preload_gravity","deferred_patterns"})
            if self.preload_gravity.isChecked():
                visible.add("gravity_steps")

        if non_modal and self.adaptive.isChecked():
            visible.update({
                "cutback","min_factor","growth",
                "easy_iter","grow_after",
            })

        for key in self._row_widgets:
            self._set_row_visible(key,key in visible)
    def data(self):
        cyclic_targets=[]
        for raw in self.cyclic_targets.text().replace(";", ",").split(","):
            value=raw.strip()
            if value:
                cyclic_targets.append(float(value))
        deferred_pattern_tags=[]
        for raw in (
            self.deferred_patterns.text()
            .replace(";", ",")
            .replace(" ", ",")
            .split(",")
        ):
            value=raw.strip()
            if value:
                deferred_pattern_tags.append(int(value))
        return AnalysisSettingsData(
            tag=self.tag.value(),name=self.name.text().strip() or f"Analysis {self.tag.value()}",
            analysis_type=self.kind.currentText(),constraints_handler=self.constraints.currentText(),
            numberer=self.numberer.currentText(),system=self.system.currentText(),test=self.test.currentText(),
            tolerance=self.tol.value(),max_iterations=self.max_iter.value(),algorithm=self.algorithm.currentText(),
            steps=self.steps.value(),load_increment=self.load_inc.value(),control_node=self.control_node.value(),
            control_dof=int(self.control_dof.currentData()),displacement_increment=self.disp_inc.value(),
            cyclic_targets=cyclic_targets,cyclic_increment=self.cyclic_inc.value(),
            dt=self.dt.value(),gamma=self.gamma.value(),beta=self.beta.value(),
            rayleigh_damping_ratio=self.damping_ratio.value(),
            rayleigh_mode_i=self.damping_mode_i.value(),
            rayleigh_mode_j=self.damping_mode_j.value(),
            preload_gravity=self.preload_gravity.isChecked(),
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
