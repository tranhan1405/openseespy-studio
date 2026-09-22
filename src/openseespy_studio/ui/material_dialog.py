from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..project import (
    MATERIAL_CATEGORIES,
    MATERIAL_DEFAULTS,
    MATERIAL_ENGINEERING_DEFAULTS,
    MATERIAL_PARAMETER_KINDS,
    material_parameter_kind,
    MATERIAL_PARAMETER_ORDER,
    MaterialData,
)
from ..units import UnitSystem
from .material_test_dialog import MaterialTestDialog


PA_PER_MPA = 1.0e6

PREVIEW_MATERIAL_TYPES = {
    "Elastic",
    "Steel01",
    "Steel02",
    "Hardening",
    "ElasticPP",
    "ElasticBilin",
    "ReinforcingSteel",
    "Concrete01",
    "Concrete02",
    "Concrete04",
    "Hysteretic",
    "HystereticSmooth",
    "Pinching4",
    "Bond_SP01",
    "ElasticPPGap",
    "FRPConfinedConcrete02",
}

PARAMETER_LABELS = {
    "mode": "FRP definition",
    "dmgType": "Damage type",
    "damage": "Gap damage",
    "tfrp": "FRP jacket thickness tfrp",
    "R": "Column radius R",
    "Sy": "Yield slip Sy",
    "Su": "Ultimate slip Su",
    "eps_sh": "Strain at hardening eps_sh",
    "eps_ult": "Ultimate strain eps_ult",
    "sigmaY": "Yield stress σy",
    "H_iso": "Isotropic hardening modulus Hiso",
    "H_kin": "Kinematic hardening modulus Hkin",
    "epsyP": "Positive yield strain εy+",
    "epsyN": "Negative yield strain εy−",
    "eps0": "Initial strain ε0",
    "EP1": "Positive initial tangent EP1",
    "EP2": "Positive secondary tangent EP2",
    "epsP2": "Positive transition strain εP2",
    "EN1": "Negative initial tangent EN1",
    "EN2": "Negative secondary tangent EN2",
    "epsN2": "Negative transition strain εN2",
}

SWITCH_OPTIONS = {
    "mode": (("JacketC - circular FRP jacket", 0.0), ("Ultimate - user-defined fcu/ecu", 1.0)),
    "dmgType": (("cycle", 0.0), ("energy", 1.0)),
    "damage": (("noDamage", 0.0), ("damage", 1.0)),
}


class MaterialEnvelopePreview(QWidget):
    """Lightweight live envelope preview for research-oriented materials."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 180)
        self._material_type = ""
        self._parameters: dict[str, float] = {}

    def set_material(self, material_type: str, parameters: dict[str, float]) -> None:
        self._material_type = str(material_type)
        self._parameters = dict(parameters)
        self.update()

    def _curve(
        self,
    ) -> tuple[
        list[tuple[float, float]],
        str,
        list[tuple[float, float, str]],
    ]:
        """Return a compact engineering diagram from the current inputs.

        The preview is intentionally a parameter diagram. For path-dependent
        materials, the exact OpenSees response remains available through
        Material Test, while the editor diagram highlights the meaning and
        relative location of the entered parameters.
        """
        p = self._parameters
        material_type = self._material_type

        if material_type == "Elastic":
            modulus = p.get("E", 0.0)
            eps = 0.002
            pts = [(-eps, -modulus * eps), (0.0, 0.0), (eps, modulus * eps)]
            return pts, "Linear stress-strain diagram · slope = E", [
                (eps * 0.62, modulus * eps * 0.62, "E"),
            ]

        if material_type == "Steel01":
            fy = abs(p.get("Fy", 0.0))
            e0 = abs(p.get("E0", 0.0))
            b = p.get("b", 0.0)
            if e0 <= 1.0e-15:
                return [], "E0 must be non-zero to draw the Steel01 diagram.", []
            ey = fy / e0
            emax = max(6.0 * ey, 0.01)
            def stress(eps: float) -> float:
                sign = -1.0 if eps < 0.0 else 1.0
                value = abs(eps)
                if value <= ey:
                    return e0 * eps
                return sign * (fy + b * e0 * (value - ey))
            samples = [-emax, -ey, 0.0, ey, emax]
            pts = [(eps, stress(eps)) for eps in samples]
            return pts, (
                "Steel01 bilinear backbone · a1-a4 control cyclic isotropic hardening"
            ), [
                (ey, fy, "Fy, εy=Fy/E0"),
                (emax, stress(emax), "b·E0"),
            ]

        if material_type == "Steel02":
            fy = abs(p.get("Fy", 0.0))
            e0 = abs(p.get("E0", 0.0))
            b = p.get("b", 0.0)
            r0 = max(abs(p.get("R0", 20.0)), 1.0e-6)
            if e0 <= 1.0e-15 or fy <= 1.0e-15:
                return [], "Fy and E0 must be non-zero to draw Steel02.", []
            ey = fy / e0
            emax = max(6.0 * ey, 0.01)
            pts = []
            for index in range(41):
                eps = -emax + 2.0 * emax * index / 40.0
                ratio = abs(e0 * eps / fy)
                transition = (1.0 + ratio**r0) ** (1.0 / r0)
                sigma = b * e0 * eps + (1.0 - b) * e0 * eps / transition
                pts.append((eps, sigma))
            return pts, (
                "Steel02 Menegotto-Pinto monotonic guide · R0/cR1/cR2 govern cyclic transition"
            ), [
                (ey, fy, "Fy / E0"),
                (0.62 * emax, dict(pts).get(0.62 * emax, 0.0), "b"),
            ]

        if material_type == "RambergOsgoodSteel":
            fy = abs(p.get("fy", 0.0))
            e0 = abs(p.get("E0", 0.0))
            a = abs(p.get("a", 0.0))
            n = max(abs(p.get("n", 0.0)), 1.0e-9)
            if e0 <= 1.0e-15 or fy <= 1.0e-15:
                return [], (
                    "fy and E0 must be non-zero to draw RambergOsgoodSteel."
                ), []
            smax = 1.5 * fy
            pts = []
            for index in range(61):
                sigma = -smax + 2.0 * smax * index / 60.0
                ratio = abs(sigma) / fy
                plastic = a * ratio**n
                eps = sigma / e0
                eps += -plastic if sigma < 0.0 else plastic
                pts.append((eps, sigma))
            ey = fy / e0 + a
            return pts, (
                "Ramberg-Osgood monotonic guide · a is the direct strain "
                "coefficient used by OpenSees"
            ), [
                (ey, fy, "fy"),
                (-ey, -fy, "-fy"),
            ]

        if material_type == "Hardening":
            e = abs(p.get("E", 0.0))
            fy = abs(p.get("sigmaY", 0.0))
            h_iso = max(p.get("H_iso", 0.0), 0.0)
            h_kin = max(p.get("H_kin", 0.0), 0.0)
            if e <= 1.0e-15 or fy <= 1.0e-15:
                return [], "E and sigmaY must be non-zero to draw Hardening.", []
            ey = fy / e
            h = h_iso + h_kin
            ep = e * h / (e + h) if h > 0.0 else 0.0
            emax = max(6.0 * ey, 0.01)
            def stress_value(eps: float) -> float:
                sign = -1.0 if eps < 0.0 else 1.0
                value = abs(eps)
                if value <= ey:
                    return e * eps
                return sign * (fy + ep * (value - ey))
            pts = [
                (-emax, stress_value(-emax)),
                (-ey, -fy),
                (0.0, 0.0),
                (ey, fy),
                (emax, stress_value(emax)),
            ]
            return pts, (
                "Hardening monotonic guide · Hiso + Hkin control post-yield "
                "plastic hardening; use Material Test for cyclic translation/expansion"
            ), [
                (ey, fy, "σy"),
                (emax, stress_value(emax), "Et"),
            ]

        if material_type == "ElasticPP":
            e = abs(p.get("E", 0.0))
            eps_p = abs(p.get("epsyP", 0.0))
            eps_n = p.get("epsyN", -eps_p)
            eps0 = p.get("eps0", 0.0)
            if e <= 1.0e-15 or eps_p <= 1.0e-15:
                return [], "E and epsyP must be non-zero to draw ElasticPP.", []
            eps_n = eps_n if eps_n < 0.0 else -abs(eps_n)
            emax = max(2.5 * eps_p, 2.5 * abs(eps_n), 0.005)
            fy_p = e * eps_p
            fy_n = e * eps_n
            pts = [
                (-emax + eps0, fy_n),
                (eps_n + eps0, fy_n),
                (eps0, 0.0),
                (eps_p + eps0, fy_p),
                (emax + eps0, fy_p),
            ]
            return pts, "ElasticPP elastic-perfectly-plastic backbone", [
                (eps_n + eps0, fy_n, "εy−"),
                (eps_p + eps0, fy_p, "εy+"),
                (eps0, 0.0, "ε0"),
            ]

        if material_type == "ElasticBilin":
            ep1 = p.get("EP1", 0.0)
            ep2 = p.get("EP2", 0.0)
            epsp2 = p.get("epsP2", 0.0)
            en1 = p.get("EN1", ep1)
            en2 = p.get("EN2", ep2)
            epsn2 = p.get("epsN2", -epsp2)
            if abs(epsp2) <= 1.0e-15 or abs(epsn2) <= 1.0e-15:
                return [], "epsP2 and epsN2 must be non-zero to draw ElasticBilin.", []
            xmax = max(2.5 * abs(epsp2), 0.005)
            xmin = -max(2.5 * abs(epsn2), 0.005)
            yp2 = ep1 * epsp2
            yn2 = en1 * epsn2
            pts = [
                (xmin, yn2 + en2 * (xmin - epsn2)),
                (epsn2, yn2),
                (0.0, 0.0),
                (epsp2, yp2),
                (xmax, yp2 + ep2 * (xmax - epsp2)),
            ]
            return pts, (
                "ElasticBilin path-independent bilinear guide · unloading follows "
                "the loading curve exactly"
            ), [
                (epsn2, yn2, "εN2"),
                (epsp2, yp2, "εP2"),
            ]

        if material_type == "HystereticSmooth":
            ka = p.get("ka", 0.0)
            kb = p.get("kb", 0.0)
            fbar = abs(p.get("fbar", 0.0))
            if abs(ka) <= 1.0e-15:
                return [], "ka must be non-zero to draw HystereticSmooth.", []
            uy = fbar / max(abs(ka - kb), 1.0e-12)
            umax = max(3.0 * uy, 0.01)
            pts = [
                (-umax, -fbar - kb * max(umax - uy, 0.0)),
                (-uy, -fbar),
                (0.0, 0.0),
                (uy, fbar),
                (umax, fbar + kb * max(umax - uy, 0.0)),
            ]
            return pts, (
                "HystereticSmooth engineering guide · ka/kb/fbar define the "
                "smooth bilinear scale; exact cyclic loop is shown in Material Test"
            ), [
                (uy, fbar, "fbar"),
            ]

        if material_type == "ReinforcingSteel":
            fy = abs(p.get("fy", 0.0))
            fu = abs(p.get("fu", fy))
            es = abs(p.get("Es", 0.0))
            esh = p.get("Esh", 0.0)
            eps_sh = max(p.get("eps_sh", 0.0), 0.0)
            eps_ult = max(p.get("eps_ult", eps_sh), eps_sh)
            if es <= 1.0e-15:
                return [], "Es must be non-zero to draw ReinforcingSteel.", []
            ey = fy / es
            yield_plateau_end = max(eps_sh, ey)
            sigma_sh = fy
            sigma_ult = min(fu, sigma_sh + esh * max(eps_ult - yield_plateau_end, 0.0))
            pts = [
                (0.0, 0.0),
                (ey, fy),
                (yield_plateau_end, sigma_sh),
                (eps_ult, sigma_ult),
            ]
            return pts, "Rebar tension backbone · elastic, yield, hardening and ultimate regions", [
                (ey, fy, "fy"),
                (yield_plateau_end, sigma_sh, "eps_sh"),
                (eps_ult, sigma_ult, "eps_ult / fu"),
            ]

        if material_type in {"Concrete01", "Concrete02"}:
            fpc = p.get("fpc", 0.0)
            epsc0 = p.get("epsc0", 0.0)
            fpcu = p.get("fpcu", fpc)
            eps_u = p.get("epsU", epsc0)
            if abs(epsc0) <= 1.0e-15:
                return [], "epsc0 must be non-zero to draw the concrete diagram.", []

            compression = []
            # Descending branch, ordered from ultimate strain toward peak.
            for index in range(7):
                t = index / 6.0
                eps = eps_u + t * (epsc0 - eps_u)
                sigma = fpcu + t * (fpc - fpcu)
                compression.append((eps, sigma))
            # Parabolic ascending branch from peak back to the origin.
            for index in range(1, 10):
                t = index / 9.0
                eps = epsc0 * (1.0 - t)
                ratio = eps / epsc0
                sigma = fpc * (2.0 * ratio - ratio * ratio)
                compression.append((eps, sigma))

            annotations = [
                (epsc0, fpc, "epsc0 / fpc"),
                (eps_u, fpcu, "epsU / fpcu"),
            ]
            note = "Concrete compression parameter diagram"
            if material_type == "Concrete02":
                ft = max(p.get("ft", 0.0), 0.0)
                ets = abs(p.get("Ets", 0.0))
                ec0 = abs(2.0 * fpc / epsc0)
                eps_t = ft / ec0 if ec0 > 1.0e-15 else 0.0
                eps_zero = eps_t + (ft / ets if ets > 1.0e-15 else max(eps_t, 0.001))
                compression.extend([(eps_t, ft), (eps_zero, 0.0)])
                annotations.extend([
                    (eps_t, ft, "ft"),
                    (eps_zero, 0.0, "Ets"),
                ])
                note = (
                    "Concrete02 compression + tension guide · λ affects unloading/reloading"
                )
            return compression, note, annotations

        if material_type == "Concrete04":
            fc = p.get("fc", 0.0)
            epsc = p.get("epsc", 0.0)
            epscu = p.get("epscu", epsc)
            ec = abs(p.get("Ec", 0.0))
            fct = max(p.get("fct", 0.0), 0.0)
            et = max(p.get("et", 0.0), 0.0)
            beta = max(p.get("beta", 0.0), 0.0)
            if abs(epsc) <= 1.0e-15:
                return [], "epsc must be non-zero to draw Concrete04.", []
            pts = [(epscu, beta * fc), (epsc, fc), (0.0, 0.0)]
            if fct > 0.0:
                eps_t = et if et > 0.0 else (fct / ec if ec > 1.0e-15 else 0.0001)
                pts.extend([(eps_t, fct), (5.0 * eps_t, beta * fct)])
            return pts, (
                "Concrete04 key-point diagram · use Material Test for the exact Popovics response"
            ), [
                (epsc, fc, "epsc / fc"),
                (epscu, beta * fc, "epscu"),
                *(([(eps_t, fct, "et / fct")] if fct > 0.0 else [])),
            ]

        if material_type == "Bond_SP01":
            fy = p.get("Fy", 0.0)
            sy = abs(p.get("Sy", 0.0))
            fu = p.get("Fu", fy)
            su = abs(p.get("Su", sy))
            pts = [
                (-su, -fu),
                (-sy, -fy),
                (0.0, 0.0),
                (sy, fy),
                (su, fu),
            ]
            return pts, "Bond_SP01 stress-slip backbone · b and R shape the transition", [
                (sy, fy, "Sy / Fy"),
                (su, fu, "Su / Fu"),
            ]

        if material_type == "ElasticPPGap":
            e = p.get("E", 0.0)
            fy = p.get("Fy", 0.0)
            gap = p.get("gap", 0.0)
            eta = p.get("eta", 0.0)
            dy = abs(fy / e) if abs(e) > 1.0e-15 else 1.0
            sign = -1.0 if fy < 0.0 else 1.0
            x1 = gap
            x2 = gap + sign * dy
            x3 = gap + sign * 2.5 * dy
            y3 = fy + eta * e * (x3 - x2)
            pts = [(0.0, 0.0), (gap, 0.0), (x2, fy), (x3, y3)]
            return pts, "ElasticPPGap force-deformation parameter diagram", [
                (gap, 0.0, "gap"),
                (x2, fy, "Fy"),
                (x3, y3, "η·E"),
            ]

        if material_type == "Hysteretic":
            pts = [
                (p.get("e3n", 0.0), p.get("s3n", 0.0)),
                (p.get("e2n", 0.0), p.get("s2n", 0.0)),
                (p.get("e1n", 0.0), p.get("s1n", 0.0)),
                (0.0, 0.0),
                (p.get("e1p", 0.0), p.get("s1p", 0.0)),
                (p.get("e2p", 0.0), p.get("s2p", 0.0)),
                (p.get("e3p", 0.0), p.get("s3p", 0.0)),
            ]
            return pts, "Hysteretic envelope · cyclic pinching/damage parameters act on this backbone", [
                (p.get("e1p", 0.0), p.get("s1p", 0.0), "e1p/s1p"),
                (p.get("e2p", 0.0), p.get("s2p", 0.0), "e2p/s2p"),
                (p.get("e3p", 0.0), p.get("s3p", 0.0), "e3p/s3p"),
            ]

        if material_type == "Pinching4":
            pts = [
                (p.get("eNd4", 0.0), p.get("eNf4", 0.0)),
                (p.get("eNd3", 0.0), p.get("eNf3", 0.0)),
                (p.get("eNd2", 0.0), p.get("eNf2", 0.0)),
                (p.get("eNd1", 0.0), p.get("eNf1", 0.0)),
                (0.0, 0.0),
                (p.get("ePd1", 0.0), p.get("ePf1", 0.0)),
                (p.get("ePd2", 0.0), p.get("ePf2", 0.0)),
                (p.get("ePd3", 0.0), p.get("ePf3", 0.0)),
                (p.get("ePd4", 0.0), p.get("ePf4", 0.0)),
            ]
            return pts, "Pinching4 envelope · pinching/degradation rules use this backbone", [
                (p.get("ePd1", 0.0), p.get("ePf1", 0.0), "P1"),
                (p.get("ePd4", 0.0), p.get("ePf4", 0.0), "P4"),
            ]

        if material_type == "FRPConfinedConcrete02":
            fc0 = p.get("fc0", 0.0)
            ec0 = p.get("ec0", 0.0)
            pts = [(0.0, 0.0), (ec0, fc0)]
            annotations = [(ec0, fc0, "ec0 / fc0")]
            if p.get("mode", 0.0) >= 0.5:
                ecu = p.get("ecu", ec0)
                fcu = p.get("fcu", fc0)
                pts.append((ecu, fcu))
                annotations.append((ecu, fcu, "ecu / fcu"))
            return pts, (
                "FRP concrete input backbone · jacket parameters define confinement in JacketC mode"
            ), annotations

        return [], "No independent material-response diagram for this wrapper/composite.", []

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fbfcfe"))
        painter.setPen(QPen(QColor("#ccd6df"), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        title_rect = QRectF(14, 10, self.width() - 28, 28)
        painter.setPen(QColor("#17356d"))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, self._material_type or "Material Preview")

        points, note, annotations = self._curve()
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#647486"))
        painter.drawText(
            QRectF(14, self.height() - 54, self.width() - 28, 42),
            Qt.AlignLeft | Qt.TextWordWrap,
            note,
        )

        plot = QRectF(48, 48, max(80, self.width() - 76), max(90, self.height() - 126))
        painter.setPen(QPen(QColor("#d8e0e8"), 1))
        painter.drawRect(plot)

        if len(points) < 2:
            painter.setPen(QColor("#7b8997"))
            painter.drawText(plot, Qt.AlignCenter, "No envelope preview for this material.")
            return

        xs = [float(x) for x, _ in points]
        ys = [float(y) for _, y in points]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if abs(xmax - xmin) <= 1.0e-15:
            xmin -= 1.0
            xmax += 1.0
        if abs(ymax - ymin) <= 1.0e-15:
            ymin -= 1.0
            ymax += 1.0
        padx = 0.08 * (xmax - xmin)
        pady = 0.08 * (ymax - ymin)
        xmin -= padx
        xmax += padx
        ymin -= pady
        ymax += pady

        def map_point(x: float, y: float) -> QPointF:
            px = plot.left() + (x - xmin) / (xmax - xmin) * plot.width()
            py = plot.bottom() - (y - ymin) / (ymax - ymin) * plot.height()
            return QPointF(px, py)

        if xmin <= 0.0 <= xmax:
            p0 = map_point(0.0, ymin)
            p1 = map_point(0.0, ymax)
            painter.setPen(QPen(QColor("#bac5d0"), 1))
            painter.drawLine(p0, p1)
        if ymin <= 0.0 <= ymax:
            p0 = map_point(xmin, 0.0)
            p1 = map_point(xmax, 0.0)
            painter.setPen(QPen(QColor("#bac5d0"), 1))
            painter.drawLine(p0, p1)

        path = QPainterPath()
        first = map_point(*points[0])
        path.moveTo(first)
        for point in points[1:]:
            path.lineTo(map_point(*point))
        painter.setPen(QPen(QColor("#c62828"), 2.2))
        painter.drawPath(path)

        painter.setBrush(QColor("#17356d"))
        painter.setPen(Qt.NoPen)
        for point in points:
            q = map_point(*point)
            painter.drawEllipse(q, 3.2, 3.2)

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#40566c"), 1))
        small_font = painter.font()
        small_font.setPointSize(max(7, small_font.pointSize() - 1))
        painter.setFont(small_font)
        for x, y, label in annotations:
            q = map_point(float(x), float(y))
            text_rect = QRectF(
                min(q.x() + 6.0, plot.right() - 112.0),
                max(plot.top(), q.y() - 20.0),
                108.0,
                18.0,
            )
            painter.drawText(
                text_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                str(label),
            )


class MaterialDialog(QDialog):
    def __init__(
        self,
        material: MaterialData | None = None,
        *,
        next_tag: int = 1,
        units=None,
        materials: dict[int, MaterialData] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Material Editor")
        self.setModal(True)
        self.resize(920, 680)
        self.unit_system = UnitSystem.from_mapping(units)
        self._editing_existing = material is not None
        self.materials = dict(materials or {})
        self._pending_materials: list[MaterialData] = []
        if material is not None:
            self.materials.pop(material.tag, None)

        root = QVBoxLayout(self)

        form = QFormLayout()
        self.tag = QSpinBox()
        self.tag.setRange(1, 2_147_483_647)
        self.tag.setValue(material.tag if material else next_tag)

        self.name = QLineEdit()
        self.name.setText(material.name if material else f"Material {next_tag}")

        self.material_type = QComboBox()
        reference_only_types = {"RambergOsgoodSteel"}
        ordered_types = sorted(
            (
                name
                for name in MATERIAL_PARAMETER_ORDER
                if (
                    name not in reference_only_types
                    or (
                        material is not None
                        and material.material_type == name
                    )
                )
            ),
            key=lambda name: (MATERIAL_CATEGORIES.get(name, ""), name),
        )
        for name in ordered_types:
            category = MATERIAL_CATEGORIES.get(name, "General")
            self.material_type.addItem(f"{category} · {name}", name)
        if material:
            index = self.material_type.findData(material.material_type)
            if index >= 0:
                self.material_type.setCurrentIndex(index)

        form.addRow("Tag:", self.tag)
        form.addRow("Name:", self.name)
        form.addRow("Type:", self.material_type)

        current_type = material.material_type if material else str(self.material_type.currentData())
        engineering_defaults = MATERIAL_ENGINEERING_DEFAULTS[current_type]

        self.poisson_ratio = QDoubleSpinBox()
        self.poisson_ratio.setDecimals(6)
        self.poisson_ratio.setRange(-0.99, 0.499999)
        self.poisson_ratio.setSingleStep(0.01)
        self.poisson_ratio.setValue(
            material.poisson_ratio if material is not None else engineering_defaults["poisson_ratio"]
        )

        self.density = QDoubleSpinBox()
        self.density.setDecimals(6)
        self.density.setRange(0.0, 1.0e12)
        self.density.setValue(
            self.unit_system.engineering_density_from_kg_per_m3(
                material.density
                if material is not None
                else engineering_defaults["density"]
            )
        )

        form.addRow("Poisson ratio ν:", self.poisson_ratio)
        form.addRow(
            f"Density ρ [{self.unit_system.engineering_density_label}]:",
            self.density,
        )
        root.addLayout(form)

        manual_note = QLabel(
            "New Material uses editable initialization values, not a verified "
            "published parameter set. Use Material Library... when a "
            "reference-backed baseline is required."
        )
        manual_note.setWordWrap(True)
        manual_note.setStyleSheet(
            "padding: 7px; background: #fff4df; color: #7a5600;"
        )
        if material is not None and material.source:
            manual_note.hide()
        root.addWidget(manual_note)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.parameter_widget = QWidget()
        self.parameter_form = QFormLayout(self.parameter_widget)
        self.parameter_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        scroll.setWidget(self.parameter_widget)
        splitter.addWidget(scroll)

        self.preview_host = QWidget()
        preview_layout = QVBoxLayout(self.preview_host)
        preview_layout.setContentsMargins(6, 0, 0, 0)
        self.preview_title = QLabel("Material response / parameter diagram")
        self.preview_title.setStyleSheet(
            "font-weight: 700; color: #17356d;"
        )
        preview_layout.addWidget(self.preview_title)
        self.preview = MaterialEnvelopePreview()
        preview_layout.addWidget(self.preview, 1)
        splitter.addWidget(self.preview_host)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(1, True)
        splitter.setSizes([650, 270])

        # Keep material guidance available without forcing a permanent preview
        # pane.  Materials without a meaningful live envelope use the full
        # editor width and show only this compact note.
        self.material_note = QLabel()
        self.material_note.setWordWrap(True)
        self.material_note.setStyleSheet(
            "padding: 7px; background: #f2f5f8; color: #526578;"
        )
        root.addWidget(self.material_note)

        self.source_note = QLabel()
        self.source_note.setWordWrap(True)
        self.source_note.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.source_note.setStyleSheet(
            "padding: 7px; background: #fff8e8; color: #5d4a16;"
        )
        self._show_source_metadata(material)
        root.addWidget(self.source_note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.load_library_button = buttons.addButton(
            "Load Verified Preset...",
            QDialogButtonBox.ActionRole,
        )
        self.load_library_button.clicked.connect(
            self._load_verified_preset
        )
        self.test_material_button = buttons.addButton(
            "Test Material...",
            QDialogButtonBox.ActionRole,
        )
        self.test_material_button.clicked.connect(self._open_material_test)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._parameter_widgets: dict[str, QWidget] = {}
        # Backward-compatible handle used by engineering-unit tests and a few
        # internal callers; switch parameters live only in _parameter_widgets.
        self._parameter_spins: dict[str, QDoubleSpinBox] = {}
        self._initial_material = material
        self._frp_jacket_group: QGroupBox | None = None
        self._frp_ultimate_group: QGroupBox | None = None
        self._base_material_combo: QComboBox | None = None
        self._component_table: QTableWidget | None = None

        self.material_type.currentIndexChanged.connect(
            lambda _index: self._material_type_changed(str(self.material_type.currentData()))
        )
        self._rebuild_parameters(str(self.material_type.currentData()))

    def _material_type_changed(self, material_type: str) -> None:
        self._initial_material = None
        self.source_note.hide()
        self._rebuild_parameters(material_type)
        defaults = MATERIAL_ENGINEERING_DEFAULTS[material_type]
        self.poisson_ratio.setValue(defaults["poisson_ratio"])
        self.density.setValue(
            self.unit_system.engineering_density_from_kg_per_m3(
                defaults["density"]
            )
        )

    def _clear_parameter_form(self) -> None:
        while self.parameter_form.rowCount():
            self.parameter_form.removeRow(0)
        self._parameter_widgets.clear()
        self._parameter_spins.clear()
        self._frp_jacket_group = None
        self._frp_ultimate_group = None
        self._base_material_combo = None
        self._component_table = None

    def _parameter_kind(self, material_type: str, key: str) -> str:
        if (
            self._initial_material is not None
            and self._initial_material.material_type == material_type
        ):
            return material_parameter_kind(
                self._initial_material,
                key,
            )
        return MATERIAL_PARAMETER_KINDS.get(
            material_type,
            {},
        ).get(key, "raw")

    def _display_value(
        self,
        material_type: str,
        key: str,
        stored: float,
    ) -> float:
        kind = self._parameter_kind(material_type, key)
        if kind == "stress":
            return self.unit_system.engineering_stress_from_pa(stored)
        if kind == "length":
            return self.unit_system.length_from_m(stored)
        if kind == "force":
            return self.unit_system.force_from_n(stored)
        if kind == "moment":
            return self.unit_system.moment_from_nm(stored)
        return stored

    def _stored_value(
        self,
        material_type: str,
        key: str,
        display: float,
    ) -> float:
        kind = self._parameter_kind(material_type, key)
        if kind == "stress":
            return self.unit_system.engineering_stress_to_pa(display)
        if kind == "length":
            return self.unit_system.length_to_m_value(display)
        if kind == "force":
            return self.unit_system.force_to_n_value(display)
        if kind == "moment":
            return self.unit_system.moment_to_nm_value(display)
        return display

    def _parameter_label(self, material_type: str, key: str) -> str:
        base = PARAMETER_LABELS.get(key, key)
        if material_type == "Hardening" and key == "eta":
            base = "Viscoplastic coefficient η"
        elif material_type == "ElasticPPGap" and key == "eta":
            base = "Hardening ratio η"
        kind = self._parameter_kind(material_type, key)
        if kind == "stress":
            return (
                f"{base} "
                f"[{self.unit_system.engineering_stress_label}]:"
            )
        if kind == "length":
            return f"{base} [{self.unit_system.length}]:"
        if kind == "force":
            return f"{base} [{self.unit_system.force}]:"
        if kind == "moment":
            return f"{base} [{self.unit_system.moment_label}]:"
        if kind == "rotation":
            return f"{base} [rad]:"
        if kind == "strain":
            return f"{base} [strain]:"
        if material_type == "MinMax":
            self._add_base_material_selector(material_type)
            self._add_group(
                "Failure strain limits",
                material_type,
                ("min", "max"),
            )
        elif material_type == "Fatigue":
            self._add_base_material_selector(material_type)
            self._add_group(
                "Coffin-Manson fatigue / global limits",
                material_type,
                ("E0", "m", "min", "max"),
            )
        elif material_type in {"Parallel", "Series"}:
            self._add_composite_selector(material_type)
        elif material_type == "Hysteretic":
            if key.startswith("s"):
                return f"{key} response:"
            if key.startswith("e"):
                return f"{key} deformation:"
        if material_type == "Pinching4":
            if "f" in key and key.startswith(("eP", "eN")):
                return f"{key} response:"
            if "d" in key and key.startswith(("eP", "eN")):
                return f"{key} deformation:"
        return f"{base}:"

    def _initial_value(self, material_type: str, key: str) -> float:
        defaults = MATERIAL_DEFAULTS[material_type]
        if (
            self._initial_material is not None
            and self._initial_material.material_type == material_type
        ):
            stored = float(self._initial_material.parameters.get(key, defaults[key]))
        else:
            stored = float(defaults[key])
        return self._display_value(material_type, key, stored)

    def _make_widget(self, material_type: str, key: str) -> QWidget:
        if key in SWITCH_OPTIONS:
            combo = QComboBox()
            for label, value in SWITCH_OPTIONS[key]:
                combo.addItem(label, value)
            initial = self._initial_value(material_type, key)
            index = 0
            for candidate in range(combo.count()):
                if abs(float(combo.itemData(candidate)) - initial) < 0.5:
                    index = candidate
                    break
            combo.setCurrentIndex(index)
            combo.currentIndexChanged.connect(self._parameter_changed)
            self._parameter_widgets[key] = combo
            return combo

        spin = QDoubleSpinBox()
        kind = self._parameter_kind(material_type, key)
        spin.setDecimals(6 if kind == "stress" else 10)
        spin.setRange(-1.0e20, 1.0e20)
        spin.setSingleStep(1.0 if kind == "stress" else 0.01)
        spin.setValue(self._initial_value(material_type, key))
        spin.valueChanged.connect(self._parameter_changed)
        self._parameter_widgets[key] = spin
        self._parameter_spins[key] = spin
        return spin

    def _widget_value(self, key: str) -> float:
        widget = self._parameter_widgets[key]
        if isinstance(widget, QComboBox):
            return float(widget.currentData())
        if isinstance(widget, QDoubleSpinBox):
            return float(widget.value())
        raise TypeError(f"Unsupported parameter widget for {key}")

    def _add_group(self, title: str, material_type: str, keys: tuple[str, ...]) -> QGroupBox:
        group = QGroupBox(title)
        form = QFormLayout(group)
        for key in keys:
            form.addRow(self._parameter_label(material_type, key), self._make_widget(material_type, key))
        self.parameter_form.addRow(group)
        return group

    def _reference_material_combo(
        self,
        selected_tag: int | None = None,
    ) -> QComboBox:
        combo = QComboBox()
        for tag in sorted(self.materials):
            item = self.materials[tag]
            combo.addItem(
                f"{tag} - {item.name} ({item.material_type})",
                tag,
            )
        if selected_tag is not None:
            index = combo.findData(int(selected_tag))
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.currentIndexChanged.connect(self._parameter_changed)
        return combo

    def _add_base_material_selector(self, material_type: str) -> None:
        group = QGroupBox("Wrapped material")
        form = QFormLayout(group)
        selected = (
            self._initial_material.base_material_tag
            if (
                self._initial_material is not None
                and self._initial_material.material_type == material_type
            )
            else None
        )
        self._base_material_combo = self._reference_material_combo(selected)
        if self._base_material_combo.count() == 0:
            self._base_material_combo.addItem(
                "No base material available",
                None,
            )
            self._base_material_combo.setEnabled(False)

        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(self._base_material_combo, 1)
        create_base = QPushButton("New Base Material...")
        create_base.clicked.connect(self._create_dependency_material)
        row.addWidget(create_base)
        form.addRow("Base material:", holder)
        self.parameter_form.addRow(group)

    def _add_component_row(
        self,
        material_tag: int | None = None,
        factor: float = 1.0,
    ) -> None:
        table = self._component_table
        if table is None:
            return
        row = table.rowCount()
        table.insertRow(row)

        combo = self._reference_material_combo(material_tag)
        if combo.count() == 0:
            combo.addItem("No materials available", None)
            combo.setEnabled(False)
        table.setCellWidget(row, 0, combo)

        if str(self.material_type.currentData()) == "Parallel":
            spin = QDoubleSpinBox()
            spin.setDecimals(8)
            spin.setRange(-1.0e12, 1.0e12)
            spin.setValue(float(factor))
            spin.valueChanged.connect(self._parameter_changed)
            table.setCellWidget(row, 1, spin)
        else:
            table.setItem(row, 1, QTableWidgetItem("—"))

        self._parameter_changed()

    def _remove_component_rows(self) -> None:
        table = self._component_table
        if table is None:
            return
        rows = sorted(
            {index.row() for index in table.selectedIndexes()},
            reverse=True,
        )
        for row in rows:
            table.removeRow(row)
        self._parameter_changed()

    def _add_composite_selector(self, material_type: str) -> None:
        group = QGroupBox(
            "Parallel components"
            if material_type == "Parallel"
            else "Series components"
        )
        layout = QVBoxLayout(group)
        self._component_table = QTableWidget(0, 2)
        self._component_table.setHorizontalHeaderLabels(
            ["Material", "Factor" if material_type == "Parallel" else "Series"]
        )
        self._component_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.Stretch,
        )
        self._component_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeToContents,
        )
        layout.addWidget(self._component_table)

        buttons = QHBoxLayout()
        add_button = QPushButton("Add Material")
        new_material_button = QPushButton("New Component Material...")
        remove_button = QPushButton("Remove Selected")
        add_button.clicked.connect(lambda: self._add_component_row())
        new_material_button.clicked.connect(
            self._create_dependency_material
        )
        remove_button.clicked.connect(self._remove_component_rows)
        buttons.addWidget(add_button)
        buttons.addWidget(new_material_button)
        buttons.addWidget(remove_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.parameter_form.addRow(group)

        tags: list[int] = []
        factors: list[float] = []
        if (
            self._initial_material is not None
            and self._initial_material.material_type == material_type
        ):
            tags = list(self._initial_material.material_tags)
            factors = list(self._initial_material.factors)
        if not tags and self.materials:
            tags = [next(iter(sorted(self.materials)))]
        for index, tag in enumerate(tags):
            factor = (
                factors[index]
                if index < len(factors)
                else 1.0
            )
            self._add_component_row(tag, factor)

    def _next_dependency_material_tag(self) -> int:
        used = set(self.materials)
        used.add(int(self.tag.value()))
        return max(used, default=0) + 1

    def pending_materials(self) -> list[MaterialData]:
        return [
            MaterialData.from_dict(material.to_dict())
            for material in self._pending_materials
        ]

    def _refresh_dependency_selectors(
        self,
        *,
        select_tag: int | None = None,
    ) -> None:
        if self._base_material_combo is not None:
            current = self._base_material_combo.currentData()
            self._base_material_combo.blockSignals(True)
            self._base_material_combo.clear()
            for tag in sorted(self.materials):
                material = self.materials[tag]
                suffix = (
                    " · new"
                    if any(
                        item.tag == tag
                        for item in self._pending_materials
                    )
                    else ""
                )
                self._base_material_combo.addItem(
                    f"{tag} - {material.name} "
                    f"({material.material_type}){suffix}",
                    tag,
                )
            wanted = select_tag if select_tag is not None else current
            if wanted is not None:
                index = self._base_material_combo.findData(int(wanted))
                if index >= 0:
                    self._base_material_combo.setCurrentIndex(index)
            self._base_material_combo.setEnabled(
                self._base_material_combo.count() > 0
            )
            self._base_material_combo.blockSignals(False)

        table = self._component_table
        if table is not None:
            for row in range(table.rowCount()):
                combo = table.cellWidget(row, 0)
                if not isinstance(combo, QComboBox):
                    continue
                current = combo.currentData()
                combo.blockSignals(True)
                combo.clear()
                for tag in sorted(self.materials):
                    material = self.materials[tag]
                    suffix = (
                        " · new"
                        if any(
                            item.tag == tag
                            for item in self._pending_materials
                        )
                        else ""
                    )
                    combo.addItem(
                        f"{tag} - {material.name} "
                        f"({material.material_type}){suffix}",
                        tag,
                    )
                wanted = (
                    select_tag
                    if select_tag is not None and row == table.rowCount() - 1
                    else current
                )
                if wanted is not None:
                    index = combo.findData(int(wanted))
                    if index >= 0:
                        combo.setCurrentIndex(index)
                combo.setEnabled(combo.count() > 0)
                combo.blockSignals(False)
        self._parameter_changed()

    def _create_dependency_material(self) -> None:
        dialog = MaterialDialog(
            next_tag=self._next_dependency_material_tag(),
            units=self.unit_system.as_mapping(),
            materials=self.materials,
            parent=self,
        )
        if not dialog.exec():
            return

        try:
            staged = dialog.pending_materials()
            material = dialog.material_data()
            candidates = list(staged) + [material]
            used = set(self.materials)
            for candidate in candidates:
                if candidate.tag in used:
                    raise ValueError(
                        f"Material tag {candidate.tag} already exists."
                    )
                used.add(candidate.tag)
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Material Dependency",
                str(exc),
            )
            return

        for candidate in candidates:
            copied = MaterialData.from_dict(candidate.to_dict())
            self.materials[copied.tag] = copied
            self._pending_materials.append(copied)
        self._refresh_dependency_selectors(
            select_tag=material.tag,
        )

    def _wrapper_references(
        self,
        material_type: str,
    ) -> tuple[int | None, list[int], list[float]]:
        if material_type in {"MinMax", "Fatigue"}:
            base = (
                None
                if self._base_material_combo is None
                else self._base_material_combo.currentData()
            )
            return (
                None if base is None else int(base),
                [],
                [],
            )

        if material_type not in {"Parallel", "Series"}:
            return None, [], []

        tags: list[int] = []
        factors: list[float] = []
        table = self._component_table
        if table is None:
            return None, tags, factors
        for row in range(table.rowCount()):
            combo = table.cellWidget(row, 0)
            if not isinstance(combo, QComboBox) or combo.currentData() is None:
                continue
            tags.append(int(combo.currentData()))
            if material_type == "Parallel":
                factor = table.cellWidget(row, 1)
                factors.append(
                    float(factor.value())
                    if isinstance(factor, QDoubleSpinBox)
                    else 1.0
                )
        return None, tags, factors

    def _rebuild_parameters(self, material_type: str) -> None:
        self._clear_parameter_form()

        if material_type == "Hardening":
            self._add_group(
                "Elastic and yield",
                material_type,
                ("E", "sigmaY"),
            )
            self._add_group(
                "Combined hardening",
                material_type,
                ("H_iso", "H_kin"),
            )
            self._add_group(
                "Optional viscoplasticity",
                material_type,
                ("eta",),
            )
        elif material_type == "ElasticPP":
            self._add_group(
                "Elastic-perfectly plastic",
                material_type,
                ("E", "epsyP", "epsyN", "eps0"),
            )
        elif material_type == "ElasticBilin":
            self._add_group(
                "Positive branch",
                material_type,
                ("EP1", "EP2", "epsP2"),
            )
            self._add_group(
                "Negative branch",
                material_type,
                ("EN1", "EN2", "epsN2"),
            )
        elif material_type == "HystereticSmooth":
            self._add_group(
                "Smooth hysteresis",
                material_type,
                ("ka", "kb", "fbar", "beta"),
            )
        elif material_type == "Hysteretic":
            self._add_group(
                "Positive envelope",
                material_type,
                ("s1p", "e1p", "s2p", "e2p", "s3p", "e3p"),
            )
            self._add_group(
                "Negative envelope",
                material_type,
                ("s1n", "e1n", "s2n", "e2n", "s3n", "e3n"),
            )
            self._add_group(
                "Pinching and degradation",
                material_type,
                ("pinchX", "pinchY", "damage1", "damage2", "beta"),
            )
        elif material_type == "Pinching4":
            self._add_group(
                "Positive envelope · 4 points",
                material_type,
                ("ePf1", "ePd1", "ePf2", "ePd2", "ePf3", "ePd3", "ePf4", "ePd4"),
            )
            self._add_group(
                "Negative envelope · 4 points",
                material_type,
                ("eNf1", "eNd1", "eNf2", "eNd2", "eNf3", "eNd3", "eNf4", "eNd4"),
            )
            self._add_group(
                "Pinching",
                material_type,
                ("rDispP", "rForceP", "uForceP", "rDispN", "rForceN", "uForceN"),
            )
            self._add_group(
                "Unloading stiffness degradation",
                material_type,
                ("gK1", "gK2", "gK3", "gK4", "gKLim"),
            )
            self._add_group(
                "Reloading stiffness degradation",
                material_type,
                ("gD1", "gD2", "gD3", "gD4", "gDLim"),
            )
            self._add_group(
                "Strength degradation",
                material_type,
                ("gF1", "gF2", "gF3", "gF4", "gFLim"),
            )
            self._add_group("Energy / damage rule", material_type, ("gE", "dmgType"))
        elif material_type == "FRPConfinedConcrete02":
            self._add_group("Unconfined concrete", material_type, ("fc0", "Ec", "ec0"))
            self._add_group("Confinement definition", material_type, ("mode",))
            self._frp_jacket_group = self._add_group(
                "Circular FRP jacket · JacketC",
                material_type,
                ("tfrp", "Efrp", "erup", "R"),
            )
            self._frp_ultimate_group = self._add_group(
                "User-defined confined ultimate point",
                material_type,
                ("fcu", "ecu"),
            )
            self._add_group("Tension", material_type, ("ft", "Ets"))
        else:
            for key in MATERIAL_PARAMETER_ORDER[material_type]:
                self.parameter_form.addRow(
                    self._parameter_label(material_type, key),
                    self._make_widget(material_type, key),
                )

        self._sync_special_visibility()
        self._update_preview()

    def _parameter_changed(self, *args) -> None:
        self._sync_special_visibility()
        self._update_preview()

    def _sync_special_visibility(self) -> None:
        if "mode" not in self._parameter_widgets:
            return
        jacket = self._widget_value("mode") < 0.5
        if self._frp_jacket_group is not None:
            self._frp_jacket_group.setVisible(jacket)
        if self._frp_ultimate_group is not None:
            self._frp_ultimate_group.setVisible(not jacket)

    def _display_parameter_values(self) -> dict[str, float]:
        return {
            key: self._widget_value(key)
            for key in self._parameter_widgets
        }

    def _update_preview(self) -> None:
        material_type = str(self.material_type.currentData())
        values = self._display_parameter_values()

        preview_available = material_type in PREVIEW_MATERIAL_TYPES
        self.preview_host.setVisible(preview_available)
        if preview_available:
            self.preview.set_material(material_type, values)

        if material_type in {
            "FRPConfinedConcrete",
            "FRPConfinedConcrete02",
        }:
            unit_ok = (
                self.unit_system.length == "mm"
                and self.unit_system.force == "N"
            )
            if unit_ok:
                model_note = (
                    "FRPConfinedConcrete is the Megalooikonomou-Monti-Santini "
                    "circular RC confinement model. Some stock OpenSeesPy builds "
                    "(including 3.8.0 used by Studio CI) omit this legacy material "
                    "from the compiled runtime; import/edit/export remains available."
                    if material_type == "FRPConfinedConcrete"
                    else (
                        "FRPConfinedConcrete02 represents the wrap through the "
                        "concrete constitutive law; do not create a duplicate "
                        "column element."
                    )
                )
                self.material_note.setText(
                    f"{material_type} uses the OpenSees SI metric convention "
                    f"(N, mm, MPa). {model_note}"
                )
                self.material_note.setStyleSheet(
                    "padding: 7px; background: #eaf6ee; color: #276738;"
                )
            else:
                self.material_note.setText(
                    f"{material_type} is unit-sensitive. For research-safe "
                    "generation use project units mm - N - s (stress = MPa). "
                    "Studio will block generation in other unit systems."
                )
                self.material_note.setStyleSheet(
                    "padding: 7px; background: #fff4df; color: #7a5600;"
                )
        elif material_type in {"MinMax", "Fatigue"}:
            base, _, _ = self._wrapper_references(material_type)
            base_text = (
                f"material {base}"
                if base is not None
                else "no base material selected"
            )
            self.material_note.setText(
                f"{material_type} wraps {base_text}. The wrapped material must "
                "already exist; Studio generates dependencies before wrappers "
                "and blocks circular references."
            )
            self.material_note.setStyleSheet(
                "padding: 7px; background: #eef4fb; color: #40566c;"
            )
        elif material_type in {"Parallel", "Series"}:
            _, tags, factors = self._wrapper_references(material_type)
            factor_text = (
                " with explicit linear-combination factors"
                if material_type == "Parallel"
                else ""
            )
            self.material_note.setText(
                f"{material_type} combines {len(tags)} referenced material(s)"
                f"{factor_text}. Use Material Test to exercise the assembled "
                "OpenSees constitutive object."
            )
            self.material_note.setStyleSheet(
                "padding: 7px; background: #eef4fb; color: #40566c;"
            )
        elif material_type == "Hardening":
            self.material_note.setText(
                "Hardening uses combined linear isotropic + kinematic hardening. "
                "Hiso=0 gives purely kinematic hardening; Hkin=0 gives purely "
                "isotropic hardening; eta=0 gives the rate-independent model. "
                "Studio treats E, sigmaY, Hiso, Hkin and eta as stress-based "
                "engineering inputs for steel/fiber use."
            )
            self.material_note.setStyleSheet(
                "padding: 7px; background: #eef4fb; color: #40566c;"
            )
        elif material_type in {"Hysteretic", "HystereticSmooth", "Pinching4"}:
            self.material_note.setText(
                "Envelope points are shown live. These materials may represent "
                "stress-strain or force-deformation response depending on where "
                "they are assigned (fiber vs zeroLength/link)."
            )
            self.material_note.setStyleSheet(
                "padding: 7px; background: #eef4fb; color: #40566c;"
            )
        elif material_type in {
            "Steel01",
            "Steel02",
            "Hardening",
            "ElasticPP",
            "ElasticBilin",
            "ReinforcingSteel",
            "Concrete01",
            "Concrete02",
            "Concrete04",
            "Bond_SP01",
            "Elastic",
            "ElasticPPGap",
        }:
            response_name = (
                "stress-slip"
                if material_type == "Bond_SP01"
                else "force-deformation"
                if material_type == "ElasticPPGap"
                else "stress-strain"
            )
            self.material_note.setText(
                f"The diagram is a live {response_name} parameter guide built "
                "from the current inputs. For cyclic/path-dependent behavior "
                "and exact OpenSees constitutive response, use Test Material."
            )
            self.material_note.setStyleSheet(
                "padding: 7px; background: #eef4fb; color: #40566c;"
            )
        else:
            self.material_note.setText(
                "Parameters are stored internally in SI and displayed in "
                f"{self.unit_system.engineering_stress_label} for stress/modulus "
                f"and {self.unit_system.engineering_density_label} for density."
            )
            self.material_note.setStyleSheet(
                "padding: 7px; background: #f2f5f8; color: #526578;"
            )

    def _show_source_metadata(
        self,
        material: MaterialData | None,
    ) -> None:
        if material is None or not material.source:
            self.source_note.clear()
            self.source_note.hide()
            return
        reference = dict(
            material.source.get("primary_reference", {})
        )
        evidence = dict(
            material.source.get("parameter_evidence", {})
        )
        source_units = dict(
            material.source.get("source_units", {})
        )
        unit_text = " / ".join(
            str(value) for value in source_units.values()
        )
        response_quantity = str(
            material.source.get("response_quantity", "")
        ).strip()
        context_text = (
            f"\nResponse: {response_quantity} · published units: "
            f"{unit_text}"
            if response_quantity
            else ""
        )
        self.source_note.setText(
            "Reference-backed material · "
            f"status: {material.source.get('status', 'unknown')}\n"
            f"{reference.get('title', '')}\n"
            f"DOI: {reference.get('doi', '')}\n"
            f"Evidence: {evidence.get('location', '')}"
            f"{context_text}\n"
            "The verified status applies to the cited constitutive "
            "parameters. Editing those values will mark this project "
            "material as modified_from_verified."
        )
        self.source_note.show()

    def _load_verified_preset(self) -> None:
        # Local import avoids a module cycle: the library dialog reuses this
        # module's lightweight material preview widget.
        from .material_library_dialog import MaterialLibraryDialog

        try:
            dialog = MaterialLibraryDialog(
                next_tag=self.tag.value(),
                units=self.unit_system.as_mapping(),
                materials=self.materials,
                accept_label="Load into Editor",
                parent=self,
            )
        except (OSError, TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Material Library",
                f"Could not load the verified material library:\n\n{exc}",
            )
            return
        if not dialog.exec():
            return

        try:
            preset = dialog.material_data()
        except ValueError as exc:
            QMessageBox.warning(self, "Material Library", str(exc))
            return

        preset.tag = self.tag.value()
        self._initial_material = preset

        index = self.material_type.findData(preset.material_type)
        if index < 0:
            QMessageBox.warning(
                self,
                "Material Library",
                f"Material model {preset.material_type!r} is not available "
                "in this editor.",
            )
            return

        self.material_type.blockSignals(True)
        self.material_type.setCurrentIndex(index)
        self.material_type.blockSignals(False)
        self._rebuild_parameters(preset.material_type)

        if not self._editing_existing:
            self.name.setText(preset.name)
            defaults = MATERIAL_ENGINEERING_DEFAULTS[
                preset.material_type
            ]
            self.poisson_ratio.setValue(defaults["poisson_ratio"])
            self.density.setValue(
                self.unit_system.engineering_density_from_kg_per_m3(
                    defaults["density"]
                )
            )

        self._show_source_metadata(preset)

    def _open_material_test(self) -> None:
        try:
            material = self.material_data()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Material Test Lab",
                str(exc),
            )
            return

        test_materials = dict(self.materials)
        test_materials[material.tag] = material
        dialog = MaterialTestDialog(
            material,
            units=self.unit_system.as_mapping(),
            materials=test_materials,
            parent=self,
        )
        dialog.exec()

    def material_data(self) -> MaterialData:
        material_type = str(self.material_type.currentData())
        base_material_tag, material_tags, factors = (
            self._wrapper_references(material_type)
        )
        if (
            material_type in {"MinMax", "Fatigue"}
            and base_material_tag is None
        ):
            raise ValueError(
                f"{material_type} requires a base material. "
                "Use 'New Base Material...' to create one here."
            )
        if (
            material_type in {"Parallel", "Series"}
            and not material_tags
        ):
            raise ValueError(
                f"{material_type} requires at least one component material. "
                "Use 'New Component Material...' to create one here."
            )
        parameters = {
            key: self._stored_value(
                material_type,
                key,
                self._widget_value(key),
            )
            for key in MATERIAL_PARAMETER_ORDER[material_type]
        }

        source = (
            dict(self._initial_material.source)
            if self._initial_material is not None
            else {}
        )
        if source and self._initial_material is not None:
            original_parameters = dict(self._initial_material.parameters)
            verified_keys = {
                str(key)
                for key in source.get("verified_parameters", [])
            }
            changed = (
                material_type != self._initial_material.material_type
                or any(
                    key not in parameters
                    or not math.isclose(
                        float(parameters[key]),
                        float(original_parameters.get(key, float("nan"))),
                        rel_tol=1.0e-12,
                        abs_tol=1.0e-12,
                    )
                    for key in verified_keys
                )
            )
            if changed:
                source["status"] = "modified_from_verified"
                source["modified"] = True

        return MaterialData(
            tag=self.tag.value(),
            name=self.name.text().strip() or f"Material {self.tag.value()}",
            material_type=material_type,
            parameters=parameters,
            poisson_ratio=self.poisson_ratio.value(),
            density=self.unit_system.engineering_density_to_kg_per_m3(
                self.density.value()
            ),
            base_material_tag=base_material_tag,
            material_tags=material_tags,
            factors=factors,
            source=source,
        )
