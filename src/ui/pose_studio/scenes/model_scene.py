"""Model scene — train selection, Model/Epoch tree, loss + in-panel progress."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ui.pose_studio.chrome.scene_shell import PoseSceneShell
from ui.pose_studio.chrome.task_progress_bar import TaskProgressBar


class ModelScene(QWidget):
    """
    Model / train scene shell.

    Side: model/epoch tree host, training dataset, train controls.
    Main: ``plot_host`` (loss curve) + ``progress`` (TaskProgressBar) + status.
    """

    create_model_requested = pyqtSignal()
    upload_model_requested = pyqtSignal()
    train_requested = pyqtSignal()
    stop_train_requested = pyqtSignal()
    dataset_selection_changed = pyqtSignal()

    _SOURCE_ID_ROLE = Qt.UserRole

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ModelScene")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.shell = PoseSceneShell(show_context_bar=True, side_width=460)
        QTimer.singleShot(0, self.shell.fit_side_to_content)
        self.shell.set_advanced_visible(False)
        root.addWidget(self.shell)

        self._build_side_panel()
        self._build_main_panel()

    def _build_side_panel(self) -> None:
        model_box = QGroupBox("Model / Epoch")
        model_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        ml = QVBoxLayout(model_box)
        ml.setContentsMargins(8, 8, 8, 8)
        ml.setSpacing(4)

        self.model_epoch_host = QWidget()
        self.model_epoch_host.setObjectName("ModelEpochHost")
        self.model_epoch_layout = QVBoxLayout(self.model_epoch_host)
        self.model_epoch_layout.setContentsMargins(0, 0, 0, 0)
        self.model_epoch_layout.setSpacing(4)
        ml.addWidget(self.model_epoch_host)

        self.upload_model_btn = QPushButton("Upload model…")
        self.upload_model_btn.setToolTip(
            "Import an existing DeepLabCut model into this project"
        )
        self.upload_model_btn.clicked.connect(self.upload_model_requested.emit)
        ml.addWidget(self.upload_model_btn)
        self.shell.add_side_widget(model_box)

        dataset_box = QGroupBox("Training dataset")
        dataset_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        dl = QVBoxLayout(dataset_box)
        self.dataset_list = QListWidget()
        self.dataset_list.setObjectName("TrainingDatasetList")
        self.dataset_list.setSelectionMode(QListWidget.NoSelection)
        self.dataset_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.dataset_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.dataset_list.setMinimumHeight(72)
        self.dataset_list.setMaximumHeight(160)
        self.dataset_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.dataset_list.setToolTip(
            "Check one or more videos whose human labels go into this training run"
        )
        self.dataset_list.itemChanged.connect(self._on_dataset_item_changed)
        dl.addWidget(self.dataset_list)
        self.select_all_btn = QPushButton("Select all")
        self.select_all_btn.setToolTip("Include every listed video in the training dataset")
        self.select_all_btn.clicked.connect(self.select_all_training_sources)
        dl.addWidget(self.select_all_btn)
        self.select_none_btn = QPushButton("Select none")
        self.select_none_btn.setToolTip("Clear training-dataset selection")
        self.select_none_btn.clicked.connect(self.clear_training_source_selection)
        dl.addWidget(self.select_none_btn)
        self.shell.add_side_widget(dataset_box)

        train_box = QGroupBox("Train")
        train_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        form = QFormLayout(train_box)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.max_epochs_combo = QComboBox()
        self.max_epochs_combo.setObjectName("MaxEpochsCombo")
        for epochs in range(5, 201, 5):
            self.max_epochs_combo.addItem(str(epochs), epochs)
        self.max_epochs_combo.setCurrentIndex(self.max_epochs_combo.findData(50))
        self.max_epochs_combo.setToolTip("Maximum training epochs (multiples of 5)")
        form.addRow("Max Epochs", self.max_epochs_combo)

        save_row = QHBoxLayout()
        save_row.setContentsMargins(0, 0, 0, 0)
        self.save_every_spin = QSpinBox()
        self.save_every_spin.setObjectName("SaveEverySpin")
        self.save_every_spin.setRange(1, 200)
        self.save_every_spin.setValue(5)
        self.save_every_spin.setToolTip(
            "Save a weight checkpoint every N epochs during training "
            "(values under 5 use more disk space)"
        )
        self.save_every_spin.valueChanged.connect(self._update_save_every_warning)
        save_row.addWidget(self.save_every_spin)
        self._save_every_warn = QLabel()
        self._save_every_warn.setObjectName("SaveEveryWarnIcon")
        self._save_every_warn.setPixmap(
            self.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(16, 16)
        )
        self._save_every_warn.setToolTip(
            "Saving more often than every 5 epochs uses significantly more disk space"
        )
        save_row.addWidget(self._save_every_warn)
        save_row.addStretch(1)
        save_wrap = QWidget()
        save_wrap.setLayout(save_row)
        form.addRow("Save every N epochs", save_wrap)
        self._update_save_every_warning(self.save_every_spin.value())

        self.gpu_check = QCheckBox("Use GPU (NVIDIA CUDA)")
        self.gpu_check.setObjectName("GpuCheck")
        self.gpu_check.setToolTip(
            "Requires an NVIDIA GPU with CUDA-enabled PyTorch in the DLC conda env"
        )
        form.addRow(self.gpu_check)

        self.reset_progress_btn = QPushButton("Reset training progress")
        self.reset_progress_btn.setToolTip(
            "Delete DLC checkpoints and the loss log so the next train starts at epoch 1"
        )
        form.addRow(self.reset_progress_btn)

        self.train_btn = QPushButton("Train")
        self.train_btn.setToolTip("Start training with the selected dataset and options")
        self.train_btn.clicked.connect(self.train_requested.emit)
        form.addRow(self.train_btn)
        self.stop_train_btn = QPushButton("Stop")
        self.stop_train_btn.setToolTip("Stop after the current epoch")
        self.stop_train_btn.setEnabled(False)
        self.stop_train_btn.clicked.connect(self.stop_train_requested.emit)
        form.addRow(self.stop_train_btn)
        self.shell.add_side_widget(train_box)

    def _build_main_panel(self) -> None:
        self.plot_host = QWidget()
        self.plot_host.setObjectName("ModelPlotHost")
        self.plot_layout = QVBoxLayout(self.plot_host)
        self.plot_layout.setContentsMargins(0, 0, 0, 0)
        self.plot_layout.setSpacing(4)

        self.stats_lbl = QLabel("")
        self.stats_lbl.setObjectName("SettingsHintLabel")
        self.stats_lbl.setWordWrap(False)
        self.stats_lbl.setTextFormat(Qt.PlainText)
        self.stats_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.stats_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.plot_layout.addWidget(self.stats_lbl)

        self.plot_inner = QWidget()
        self.plot_inner_layout = QVBoxLayout(self.plot_inner)
        self.plot_inner_layout.setContentsMargins(0, 0, 0, 0)
        self.plot_inner_layout.setSpacing(0)
        self.plot_layout.addWidget(self.plot_inner, stretch=1)

        self.shell.add_main_widget(self.plot_host, stretch=1)

        self.progress = TaskProgressBar()
        self.progress.set_progress(0, 50, activity="Training Progress", unit="Epochs")
        self.shell.add_main_widget(self.progress, stretch=0)

        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("ModelSceneStatus")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.shell.add_main_widget(self.status_lbl, stretch=0)

    def _update_save_every_warning(self, value: int) -> None:
        self._save_every_warn.setVisible(int(value) < 5)

    def set_model_tree_widget(self, widget: QWidget) -> None:
        """Place the Model/Epoch tree into the side host."""
        while self.model_epoch_layout.count():
            item = self.model_epoch_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self.model_epoch_layout.addWidget(widget)

    # --- Training dataset ---

    def _on_dataset_item_changed(self, item: QListWidgetItem) -> None:
        del item
        self.dataset_selection_changed.emit()

    def set_training_sources(
        self,
        items: list[tuple[str, str]],
        *,
        selected_ids: list[str] | None = None,
    ) -> None:
        """Populate the training-dataset list. Each item is ``(source_id, label)``."""
        self.dataset_list.blockSignals(True)
        self.dataset_list.clear()
        want = set(selected_ids) if selected_ids is not None else None
        for source_id, label in items:
            item = QListWidgetItem(label)
            item.setData(self._SOURCE_ID_ROLE, source_id)
            item.setFlags(
                (item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                & ~Qt.ItemIsSelectable
            )
            checked = want is None or source_id in want
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            self.dataset_list.addItem(item)
        self.dataset_list.blockSignals(False)

    def selected_training_source_ids(self) -> list[str]:
        ids: list[str] = []
        for i in range(self.dataset_list.count()):
            item = self.dataset_list.item(i)
            if item is None or item.checkState() != Qt.Checked:
                continue
            source_id = item.data(self._SOURCE_ID_ROLE)
            if source_id:
                ids.append(str(source_id))
        return ids

    def select_all_training_sources(self) -> None:
        self.dataset_list.blockSignals(True)
        for i in range(self.dataset_list.count()):
            self.dataset_list.item(i).setCheckState(Qt.Checked)
        self.dataset_list.blockSignals(False)
        self.dataset_selection_changed.emit()

    def clear_training_source_selection(self) -> None:
        self.dataset_list.blockSignals(True)
        for i in range(self.dataset_list.count()):
            self.dataset_list.item(i).setCheckState(Qt.Unchecked)
        self.dataset_list.blockSignals(False)
        self.dataset_selection_changed.emit()

    # --- Train options ---

    def max_epochs(self) -> int:
        data = self.max_epochs_combo.currentData()
        return int(data) if data is not None else 50

    def set_max_epochs(self, epochs: int) -> None:
        idx = self.max_epochs_combo.findData(int(epochs))
        if idx >= 0:
            self.max_epochs_combo.setCurrentIndex(idx)

    def save_every_n_epochs(self) -> int:
        return int(self.save_every_spin.value())

    def use_gpu(self) -> bool:
        return self.gpu_check.isChecked()

    def set_use_gpu(self, checked: bool) -> None:
        self.gpu_check.setChecked(bool(checked))

    def set_gpu_enabled(self, enabled: bool) -> None:
        self.gpu_check.setEnabled(bool(enabled))

    def set_gpu_status(self, text: str) -> None:
        """Put GPU probe detail on the checkbox tooltip (no inline prose)."""
        tip = (text or "").strip() or (
            "Requires an NVIDIA GPU with CUDA-enabled PyTorch in the DLC conda env"
        )
        self.gpu_check.setToolTip(tip)

    def set_train_button_text(self, text: str) -> None:
        self.train_btn.setText(text)

    def set_train_controls_enabled(self, *, train: bool, stop: bool) -> None:
        self.train_btn.setEnabled(train)
        self.stop_train_btn.setEnabled(stop)

    # --- Main panel ---

    def set_plot_widget(self, widget: QWidget) -> None:
        """Replace the loss-plot host contents (e.g. ``TrainingLossPlot``)."""
        while self.plot_inner_layout.count():
            item = self.plot_inner_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self.plot_inner_layout.addWidget(widget, stretch=1)

    def set_content_widget(self, widget: QWidget) -> None:
        """Alias for ``set_plot_widget``."""
        self.set_plot_widget(widget)

    def set_stats(self, text: str, *, tooltip: str | None = None) -> None:
        self.stats_lbl.setText(text)
        tip = tooltip if tooltip is not None else text
        self.stats_lbl.setToolTip(tip)

    def set_status(self, text: str, *, tooltip: str | None = None) -> None:
        self.status_lbl.setText(text)
        tip = tooltip if tooltip is not None else text
        self.status_lbl.setToolTip(tip)
