
import sys
import math
import re
import serial
import serial.tools.list_ports

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QComboBox,
    QPlainTextEdit
)


BG = "#090e0b"
PANEL = "#111b14"
GREEN = "#70ff9b"
DIM = "#426b50"
TEXT = "#d5ead9"
AMBER = "#ffc45c"
RED = "#ff5b55"


class RadarDisplay(QWidget):
    def __init__(self):
        super().__init__()
        self.angle = 0
        self.distance = 0
        self.detected_angle = 0
        self.has_target = False
        self.setMinimumSize(350, 350)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(35)

    def animate(self):
        self.angle = (self.angle + 2) % 360
        self.update()

    def set_data(self, distance, angle):
        self.distance = distance
        self.detected_angle = angle
        self.has_target = True
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        size = min(w, h) - 35
        cx, cy = w / 2, h / 2
        radius = size / 2

        p.fillRect(self.rect(), QColor(BG))

        p.setPen(QPen(QColor(DIM), 1))
        for factor in (0.25, 0.50, 0.75, 1.0):
            r = radius * factor
            p.drawEllipse(QRectF(cx-r, cy-r, 2*r, 2*r))

        p.drawLine(int(cx-radius), int(cy), int(cx+radius), int(cy))
        p.drawLine(int(cx), int(cy-radius), int(cx), int(cy+radius))

        for a in range(0, 360, 30):
            rad = math.radians(a)
            x = cx + math.sin(rad) * radius
            y = cy - math.cos(rad) * radius
            p.drawLine(int(cx), int(cy), int(x), int(y))

        sweep = math.radians(self.angle)
        p.setPen(QPen(QColor(GREEN), 3))
        p.drawLine(
            int(cx), int(cy),
            int(cx + math.sin(sweep) * radius),
            int(cy - math.cos(sweep) * radius)
        )

        if self.has_target and self.distance > 0:
            target_r = min(radius, radius * self.distance / 150)
            target_a = math.radians(self.detected_angle)
            tx = cx + math.sin(target_a) * target_r
            ty = cy - math.cos(target_a) * target_r
            p.setPen(QPen(QColor(AMBER), 3))
            p.setBrush(QColor(AMBER))
            p.drawEllipse(QRectF(tx-5, ty-5, 10, 10))

        p.setPen(QColor(GREEN))
        p.setFont(QFont("Consolas", 9))
        p.drawText(10, 20, "ACTIVE ULTRASONIC SCAN")
        p.drawText(10, h-10, "RANGE: 150 CM")


class CockpitWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HS RADAR SYSTEM X | COCKPIT EDITION")
        self.resize(1200, 800)

        self.bt = None
        self.distance = 0
        self.angle = 0

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {BG};
                color: {TEXT};
                font-family: Consolas;
            }}
            QFrame#panel {{
                background-color: {PANEL};
                border: 1px solid {DIM};
                border-radius: 7px;
            }}
            QLabel#heading {{
                color: {GREEN};
                font-size: 17px;
                font-weight: bold;
            }}
            QLabel#value {{
                color: {GREEN};
                font-size: 25px;
                font-weight: bold;
            }}
            QPushButton {{
                background-color: #1a2c20;
                color: {GREEN};
                border: 1px solid {DIM};
                padding: 10px;
                font-weight: bold;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #294a32;
                border: 1px solid {GREEN};
            }}
            QComboBox {{
                background-color: #18251c;
                color: {GREEN};
                border: 1px solid {DIM};
                padding: 7px;
            }}
            QPlainTextEdit {{
                background-color: #050907;
                color: {GREEN};
                border: 1px solid {DIM};
            }}
        """)

        self.build_ui()
        self.refresh_ports()

        self.read_timer = QTimer(self)
        self.read_timer.timeout.connect(self.read_bluetooth)
        self.read_timer.start(50)

    def panel(self, title):
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        label = QLabel(title)
        label.setObjectName("heading")
        layout.addWidget(label)
        return frame, layout

    def add_button(self, layout, label, command):
        button = QPushButton(label)
        button.clicked.connect(lambda: self.send(command))
        layout.addWidget(button)
        return button

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("HS RADAR SYSTEM X")
        title.setStyleSheet(
            f"font-size:25px;font-weight:bold;color:{GREEN};"
        )
        header.addWidget(title)
        header.addStretch()

        self.connection_label = QLabel("● DISCONNECTED")
        self.connection_label.setStyleSheet(f"color:{RED};font-weight:bold")
        header.addWidget(self.connection_label)
        root.addLayout(header)

        subtitle = QLabel(
            "ADVANCED AVIONICS CONTROL  //  COCKPIT EDITION  //  V1.0"
        )
        subtitle.setStyleSheet(f"color:{DIM};font-size:11px")
        root.addWidget(subtitle)

        body = QHBoxLayout()

        left, ll = self.panel("FLIGHT CONTROL")
        self.port_box = QComboBox()
        ll.addWidget(QLabel("BLUETOOTH SERIAL PORT"))
        ll.addWidget(self.port_box)

        self.add_button(ll, "↻ REFRESH PORTS", self.refresh_ports)
        self.add_button(ll, "CONNECT SYSTEM", self.connect_bt)
        self.add_button(ll, "DISCONNECT", self.disconnect_bt)

        ll.addWidget(QLabel("OPERATION MODE"))
        self.mode_box = QComboBox()
        self.mode_box.addItems(
            ["NORMAL", "AIR FORCE", "NAVY", "THERMAL", "ROBOT"]
        )
        self.mode_box.currentTextChanged.connect(self.change_mode)
        ll.addWidget(self.mode_box)

        self.add_button(ll, "AUTO SCAN", "AUTO")
        self.add_button(ll, "MANUAL MODE", "MANUAL")
        self.add_button(ll, "STOP SYSTEM", "STOP")
        self.add_button(ll, "SYSTEM STATUS", "STATUS")

        body.addWidget(left, 1)

        center, cl = self.panel("TACTICAL RADAR DISPLAY")
        self.radar = RadarDisplay()
        cl.addWidget(self.radar)
        body.addWidget(center, 2)

        right, rl = self.panel("SYSTEM TELEMETRY")

        self.distance_label = QLabel("0.0 CM")
        self.distance_label.setObjectName("value")
        rl.addWidget(QLabel("DETECTED DISTANCE"))
        rl.addWidget(self.distance_label)

        self.angle_label = QLabel("0°")
        self.angle_label.setObjectName("value")
        rl.addWidget(QLabel("SERVO ANGLE"))
        rl.addWidget(self.angle_label)

        self.status_label = QLabel("STANDBY")
        self.status_label.setStyleSheet(f"color:{AMBER};font-size:17px")
        rl.addWidget(QLabel("RADAR STATUS"))
        rl.addWidget(self.status_label)

        rl.addWidget(QLabel("SERVO CONTROL"))
        self.add_button(rl, "LEFT 0°", "LEFT")
        self.add_button(rl, "CENTER 90°", "CENTER")
        self.add_button(rl, "RIGHT 180°", "RIGHT")

        rl.addWidget(QLabel("INDICATOR CONTROL"))
        self.add_button(rl, "GREEN LED", "GREEN_ON")
        self.add_button(rl, "RED LED", "RED_ON")
        self.add_button(rl, "YELLOW LED", "YELLOW_ON")
        self.add_button(rl, "ALL LEDS OFF", "ALL_LEDS_OFF")
        self.add_button(rl, "BUZZER ON", "BUZZER_ON")
        self.add_button(rl, "BUZZER OFF", "BUZZER_OFF")

        body.addWidget(right, 1)
        root.addLayout(body, 1)

        bottom, bl = self.panel("COMMUNICATION LOG")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(115)
        bl.addWidget(self.log)
        root.addWidget(bottom)

        footer = QLabel(
            "HS RADAR SYSTEM X  |  EDUCATIONAL ULTRASONIC RADAR  |  "
            "BLUETOOTH SPP 9600 BAUD"
        )
        footer.setStyleSheet(f"color:{DIM};font-size:10px")
        root.addWidget(footer)

        self.log_message("COCKPIT INTERFACE INITIALIZED")
        self.log_message("WAITING FOR BLUETOOTH CONNECTION")

    def log_message(self, message):
        self.log.appendPlainText(message)

    def refresh_ports(self):
        current = self.port_box.currentText() if hasattr(
            self, "port_box"
        ) else ""
        if not hasattr(self, "port_box"):
            return
        self.port_box.clear()
        for port in serial.tools.list_ports.comports():
            self.port_box.addItem(f"{port.device} - {port.description}")
        index = self.port_box.findText(current)
        if index >= 0:
            self.port_box.setCurrentIndex(index)
        self.log_message("SERIAL PORT LIST REFRESHED")

    def connect_bt(self):
        if self.bt and self.bt.is_open:
            return
        selected = self.port_box.currentText()
        if not selected:
            self.log_message("ERROR: SELECT A SERIAL PORT")
            return
        port = selected.split(" - ")[0]
        try:
            self.bt = serial.Serial(port, 9600, timeout=0.05)
            self.connection_label.setText("● CONNECTED")
            self.connection_label.setStyleSheet(
                f"color:{GREEN};font-weight:bold"
            )
            self.log_message("CONNECTED TO " + port)
        except Exception as error:
            self.log_message("CONNECTION ERROR: " + str(error))

    def disconnect_bt(self):
        if self.bt:
            try:
                self.bt.close()
            except Exception:
                pass
        self.bt = None
        self.connection_label.setText("● DISCONNECTED")
        self.connection_label.setStyleSheet(
            f"color:{RED};font-weight:bold"
        )
        self.log_message("BLUETOOTH DISCONNECTED")

    def send(self, command):
        if not self.bt or not self.bt.is_open:
            self.log_message("NOT CONNECTED: " + command)
            return
        try:
            self.bt.write((command + "\n").encode("utf-8"))
            self.log_message("TX >> " + command)
        except Exception as error:
            self.log_message("SEND ERROR: " + str(error))

    def change_mode(self, mode):
        commands = {
            "NORMAL": "MODE_NORMAL",
            "AIR FORCE": "MODE_AIR_FORCE",
            "NAVY": "MODE_NAVY",
            "THERMAL": "MODE_THERMAL",
            "ROBOT": "MODE_ROBOTIC"
        }
        self.send(commands[mode])

    def read_bluetooth(self):
        if not self.bt or not self.bt.is_open:
            return
        try:
            while self.bt.in_waiting:
                line = self.bt.readline().decode(
                    "utf-8", errors="ignore"
                ).strip()
                if not line:
                    continue
                self.log_message("RX << " + line)

                distance = re.search(
                    r"(?:D|DIST)\s*[:=]\s*(\d+(?:\.\d+)?)",
                    line, re.I
                )
                angle = re.search(
                    r"(?:A|ANGLE)\s*[:=]\s*(\d+(?:\.\d+)?)",
                    line, re.I
                )

                if distance:
                    self.distance = float(distance.group(1))
                    self.distance_label.setText(
                        f"{self.distance:.1f} CM"
                    )
                if angle:
                    self.angle = float(angle.group(1))
                    self.angle_label.setText(
                        f"{self.angle:.0f}°"
                    )
                if distance and angle:
                    self.radar.set_data(
                        self.distance, self.angle
                    )

                upper = line.upper()
                if "MOVING" in upper:
                    self.status_label.setText("MOVING")
                    self.status_label.setStyleSheet(
                        f"color:{RED};font-size:17px"
                    )
                elif "STABLE" in upper:
                    self.status_label.setText("STABLE")
                    self.status_label.setStyleSheet(
                        f"color:{GREEN};font-size:17px"
                    )
                elif "SCANNING" in upper:
                    self.status_label.setText("SCANNING")
        except Exception as error:
            self.log_message("READ ERROR: " + str(error))

    def closeEvent(self, event):
        self.disconnect_bt()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CockpitWindow()
    window.showFullScreen()
    sys.exit(app.exec())
