from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,QComboBox,QDialog,QDialogButtonBox,QDoubleSpinBox,QFormLayout,
    QLineEdit,QSpinBox,QVBoxLayout
)
from ..project import AnalysisSettingsData

def fs(value,low=-1e20,high=1e20):
    w=QDoubleSpinBox(); w.setDecimals(10); w.setRange(low,high); w.setValue(float(value)); return w

class AnalysisDialog(QDialog):
    def __init__(self, analysis=None, *, next_tag=1, default_node=1, parent=None):
        super().__init__(parent); self.setWindowTitle("Analysis Settings"); self.setModal(True); self.resize(430,520)
        root=QVBoxLayout(self); form=QFormLayout()
        self.tag=QSpinBox(); self.tag.setRange(1,2147483647); self.tag.setValue(analysis.tag if analysis else next_tag)
        self.name=QLineEdit(analysis.name if analysis else f"Analysis {next_tag}")
        self.kind=QComboBox(); self.kind.addItems(["Static","Pushover","Transient","Modal"]); self.kind.setCurrentText(analysis.analysis_type if analysis else "Static")
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
        for i,n in enumerate(("UX","UY","UZ","RX","RY","RZ"),1): self.control_dof.addItem(f"{n} ({i})",i)
        if analysis:
            i=self.control_dof.findData(analysis.control_dof)
            if i>=0:self.control_dof.setCurrentIndex(i)
        self.disp_inc=fs(analysis.displacement_increment if analysis else 0.001,-1e20,1e20)
        self.dt=fs(analysis.dt if analysis else 0.01,1e-12,1e20)
        self.gamma=fs(analysis.gamma if analysis else 0.5)
        self.beta=fs(analysis.beta if analysis else 0.25)
        self.modes=QSpinBox(); self.modes.setRange(1,10000); self.modes.setValue(analysis.num_modes if analysis else 3)
        self.recovery=QCheckBox("Try NewtonLineSearch / ModifiedNewton / Newton on failed step"); self.recovery.setChecked(analysis.recovery if analysis else True)
        fields=(("Tag",self.tag),("Name",self.name),("Analysis type",self.kind),("Constraints",self.constraints),("Numberer",self.numberer),("System",self.system),("Test",self.test),("Tolerance",self.tol),("Max iterations",self.max_iter),("Algorithm",self.algorithm),("Steps",self.steps),("Load increment",self.load_inc),("Control node",self.control_node),("Control DOF",self.control_dof),("Disp. increment",self.disp_inc),("Time step dt",self.dt),("Newmark gamma",self.gamma),("Newmark beta",self.beta),("Number of modes",self.modes))
        for label,w in fields: form.addRow(label+":",w)
        form.addRow("Recovery:",self.recovery); root.addLayout(form)
        b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); root.addWidget(b)
        self.kind.currentTextChanged.connect(self._sync); self._sync(self.kind.currentText())
    def _sync(self,kind):
        modal=kind=="Modal"; transient=kind=="Transient"; push=kind=="Pushover"; static=kind=="Static"
        for w in (self.test,self.tol,self.max_iter,self.algorithm,self.steps,self.recovery): w.setEnabled(not modal)
        self.load_inc.setEnabled(static); self.control_node.setEnabled(push); self.control_dof.setEnabled(push); self.disp_inc.setEnabled(push)
        self.dt.setEnabled(transient); self.gamma.setEnabled(transient); self.beta.setEnabled(transient); self.modes.setEnabled(modal)
    def data(self):
        return AnalysisSettingsData(
            tag=self.tag.value(),name=self.name.text().strip() or f"Analysis {self.tag.value()}",
            analysis_type=self.kind.currentText(),constraints_handler=self.constraints.currentText(),
            numberer=self.numberer.currentText(),system=self.system.currentText(),test=self.test.currentText(),
            tolerance=self.tol.value(),max_iterations=self.max_iter.value(),algorithm=self.algorithm.currentText(),
            steps=self.steps.value(),load_increment=self.load_inc.value(),control_node=self.control_node.value(),
            control_dof=int(self.control_dof.currentData()),displacement_increment=self.disp_inc.value(),
            dt=self.dt.value(),gamma=self.gamma.value(),beta=self.beta.value(),num_modes=self.modes.value(),
            recovery=self.recovery.isChecked()
        )
