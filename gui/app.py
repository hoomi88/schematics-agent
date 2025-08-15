from __future__ import annotations
import sys
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QThread
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel, QTextEdit, QFileDialog, QCheckBox
from core.ingest import load_circuit_spec
from agents.orchestrator import run_orchestration


class WorkerSignals(QObject):
    message = Signal(str)
    done = Signal(Path)
    error = Signal(str)


class PipelineWorker(QThread):
    def __init__(self, input_path: Path, out_dir: Path, iters: int, use_llm: bool):
        super().__init__()
        self.input_path = input_path
        self.out_dir = out_dir
        self.iters = iters
        self.use_llm = use_llm
        self.signals = WorkerSignals()

    def _log(self, msg: str) -> None:
        self.signals.message.emit(msg)

    def run(self):
        try:
            self._log("Reading input JSON...")
            circuit = load_circuit_spec(self.input_path)
            sch = run_orchestration(circuit, self.out_dir, max_iters=self.iters, progress_cb=self._log, use_llm=self.use_llm)
            self._log(f"Schematic written: {sch}")
            self.signals.done.emit(sch)
        except Exception as e:
            self.signals.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Schematic Agent")
        container = QWidget()
        layout = QVBoxLayout(container)

        self.btn_select = QPushButton("Select JSON...")
        self.label_file = QLabel("No file selected")
        self.chk_llm = QCheckBox("Enable GPT-assisted placement")
        self.btn_run = QPushButton("Run")
        self.btn_run.setEnabled(False)
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        layout.addWidget(self.btn_select)
        layout.addWidget(self.label_file)
        layout.addWidget(self.chk_llm)
        layout.addWidget(self.btn_run)
        layout.addWidget(self.log)
        self.setCentralWidget(container)

        self.btn_select.clicked.connect(self.select_file)
        self.btn_run.clicked.connect(self.run_pipeline)

        self.input_path: Path | None = None

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select JSON", str(Path.cwd()), "JSON Files (*.json)")
        if file_path:
            self.input_path = Path(file_path)
            self.label_file.setText(str(self.input_path))
            self.btn_run.setEnabled(True)

    def append_log(self, text: str):
        self.log.append(text)

    def run_pipeline(self):
        if not self.input_path:
            return
        out_dir = Path.cwd() / "output"
        self.worker = PipelineWorker(self.input_path, out_dir, iters=3, use_llm=self.chk_llm.isChecked())
        self.worker.signals.message.connect(self.append_log)
        self.worker.signals.error.connect(lambda e: self.append_log(f"Error: {e}"))
        self.worker.signals.done.connect(lambda p: self.append_log(f"Done: {p}"))
        self.append_log("Starting pipeline...")
        self.worker.start()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(800, 600)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
