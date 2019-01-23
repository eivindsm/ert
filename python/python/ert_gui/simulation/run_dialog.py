from threading import Thread
import sys

try:
    from PyQt4.QtCore import Qt, QTimer, QSize
    from PyQt4.QtGui import QDialog, QVBoxLayout, QLayout, QMessageBox, QPushButton, QHBoxLayout, QColor, QLabel, QListView, QStandardItemModel, QStandardItem
except ImportError:
    from PyQt5.QtCore import Qt, QTimer, QSize
    from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLayout, QMessageBox, QPushButton, QHBoxLayout, QLabel,  QListView
    from PyQt5.QtGui import QColor, QStandardItemModel, QStandardItem


from ert_gui.ertwidgets import resourceMovie, Legend
from ert_gui.simulation import Progress, SimpleProgress, DetailedProgressDialog
from ert_gui.simulation.models import BaseRunModel, SimulationsTracker
from ert_gui.tools.plot.plot_tool import PlotTool

from ecl.util.util import BoolVector

class RunDialog(QDialog):

    def __init__(self, run_model, parent):
        QDialog.__init__(self, parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModal)
        self.setWindowTitle("Simulations")

        assert isinstance(run_model, BaseRunModel)
        self._run_model = run_model

        layout = QVBoxLayout()
        layout.setSizeConstraint(QLayout.SetFixedSize)

        self.simulations_tracker = SimulationsTracker()
        states = self.simulations_tracker.getStates()

        self.total_progress = SimpleProgress()
        layout.addWidget(self.total_progress)

        status_layout = QHBoxLayout()
        status_layout.addStretch()
        self.__status_label = QLabel()
        status_layout.addWidget(self.__status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        self.progress = Progress()
        self.progress.setIndeterminateColor(self.total_progress.color)
        for state in states:
            self.progress.addState(state.state, QColor(*state.color), 100.0 * state.count / state.total_count)

        layout.addWidget(self.progress)

        self.detailed_progress = None

        legend_layout = QHBoxLayout()
        self.legends = {}
        for state in states:
            self.legends[state] = Legend("%s (%d/%d)", QColor(*state.color))
            self.legends[state].updateLegend(state.name, 0, 0)
            legend_layout.addWidget(self.legends[state])

        layout.addLayout(legend_layout)

        self.running_time = QLabel("")

        ert = None
        if isinstance(run_model, BaseRunModel):
            ert = run_model.ert()

        self.plot_tool = PlotTool()
        self.plot_tool.setParent(None)
        self.plot_button = QPushButton(self.plot_tool.getName())
        self.plot_button.clicked.connect(self.plot_tool.trigger)
        self.plot_button.setEnabled(ert is not None)

        self.kill_button = QPushButton("Kill simulations")
        self.done_button = QPushButton("Done")
        self.done_button.setHidden(True)
        self.restart_button = QPushButton("Restart")
        self.restart_button.setHidden(True)
        self.show_details_button = QPushButton("Details")

        self.realizations_view = QListView()
        self.realizations_view.setModel(QStandardItemModel(self.realizations_view))
        self.realizations_view.setVisible(False)

        button_layout = QHBoxLayout()

        size = 20
        spin_movie = resourceMovie("ide/loading.gif")
        spin_movie.setSpeed(60)
        spin_movie.setScaledSize(QSize(size, size))
        spin_movie.start()

        self.processing_animation = QLabel()
        self.processing_animation.setMaximumSize(QSize(size, size))
        self.processing_animation.setMinimumSize(QSize(size, size))
        self.processing_animation.setMovie(spin_movie)

        button_layout.addWidget(self.processing_animation)
        button_layout.addWidget(self.running_time)
        button_layout.addStretch()
        button_layout.addWidget(self.show_details_button)
        button_layout.addWidget(self.plot_button)
        button_layout.addWidget(self.kill_button)
        button_layout.addWidget(self.done_button)
        button_layout.addWidget(self.restart_button)

        layout.addStretch()
        layout.addLayout(button_layout)

        layout.addWidget(self.realizations_view)

        self.setLayout(layout)

        self.kill_button.clicked.connect(self.killJobs)
        self.done_button.clicked.connect(self.accept)
        self.restart_button.clicked.connect(self.restart_failed_realizations)
        self.show_details_button.clicked.connect(self.show_detailed_progress)

        self.__updating = False
        self.__update_queued = False
        self.__simulation_started = False

        self.__update_timer = QTimer(self)
        self.__update_timer.setInterval(500)
        self.__update_timer.timeout.connect(self.updateRunStatus)
        self._simulations_argments = {}

    def startSimulation(self, arguments):

        self._simulations_argments = arguments

        if not 'prev_successful_realizations' in self._simulations_argments:
            self._simulations_argments['prev_successful_realizations'] = 0
        self._run_model.reset()

        def run():
            self._run_model.startSimulations( self._simulations_argments )

        simulation_thread = Thread(name="ert_gui_simulation_thread")
        simulation_thread.setDaemon(True)
        simulation_thread.run = run
        simulation_thread.start()

        self.__update_timer.start()


    def checkIfRunFinished(self):
        if self._run_model.isFinished():

            self.update_realizations_view()
            self.hideKillAndShowDone()

            if self._run_model.hasRunFailed():
                error = self._run_model.getFailMessage()
                QMessageBox.critical(self, "Simulations failed!", "The simulation failed with the following error:\n\n%s" % error)
                self.reject()


    def updateRunStatus(self):
        self.checkIfRunFinished()

        self.total_progress.setProgress(self._run_model.getProgress())

        self.__status_label.setText(self._run_model.getPhaseName())

        states = self.simulations_tracker.getStates()

        if self._run_model.isIndeterminate():
            self.progress.setIndeterminate(True)

            for state in states:
                self.legends[state].updateLegend(state.name, 0, 0)

        else:
            if self.detailed_progress:
                self.detailed_progress.set_progress(*self._run_model.getDetailedProgress())

            self.progress.setIndeterminate(False)
            total_count = self._run_model.getQueueSize()
            queue_status = self._run_model.getQueueStatus()

            for state in states:
                state.count = 0
                state.total_count = total_count

            for state in states:
                for queue_state in queue_status:
                    if queue_state in state.state:
                        state.count += queue_status[queue_state]

                self.progress.updateState(state.state, 100.0 * state.count / state.total_count)
                self.legends[state].updateLegend(state.name, state.count, state.total_count)

        self.setRunningTime()


    def setRunningTime(self):
        days = 0
        hours = 0
        minutes = 0
        seconds = self._run_model.getRunningTime()

        if seconds >= 60:
            minutes, seconds = divmod(seconds, 60)

        if minutes >= 60:
            hours, minutes = divmod(minutes, 60)

        if hours >= 24:
            days, hours = divmod(hours, 24)

        if days > 0:
            self.running_time.setText("Running time: %d days %d hours %d minutes %d seconds" % (days, hours, minutes, seconds))
        elif hours > 0:
            self.running_time.setText("Running time: %d hours %d minutes %d seconds" % (hours, minutes, seconds))
        elif minutes > 0:
            self.running_time.setText("Running time: %d minutes %d seconds" % (minutes, seconds))
        else:
            self.running_time.setText("Running time: %d seconds" % seconds)


    def killJobs(self):
        kill_job = QMessageBox.question(self, "Kill simulations?", "Are you sure you want to kill the currently running simulations?", QMessageBox.Yes | QMessageBox.No )

        if kill_job == QMessageBox.Yes:
            if self._run_model.killAllSimulations():
                self.reject()


    def hideKillAndShowDone(self):
        self.__update_timer.stop()
        self.processing_animation.hide()
        self.kill_button.setHidden(True)
        self.done_button.setHidden(False)
        self.realizations_view.setVisible(True)
        self.restart_button.setVisible(self.has_failed_realizations() )
        self.restart_button.setEnabled(self._run_model.support_restart)


    def has_failed_realizations(self):
        completed = self._run_model.completed_realizations_mask
        initial = self._run_model.initial_realizations_mask
        for (index, successful) in enumerate(completed):
            if initial[index] and not successful:
                return True
        return False


    def count_successful_realizations(self):
        """
        Counts the realizations completed in the prevoius ensemble run
        :return:
        """
        completed = self._run_model.completed_realizations_mask
        return completed.count(True)

    def create_mask_from_failed_realizations(self):
        """
        Creates a BoolVector mask representing the failed realizations
        :return: Type BoolVector
        """
        completed = self._run_model.completed_realizations_mask
        initial = self._run_model.initial_realizations_mask
        inverted_mask = BoolVector(  default_value = False )
        for (index, successful) in enumerate(completed):
            inverted_mask[index] = initial[index] and not successful
        return inverted_mask


    def restart_failed_realizations(self):

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setText("Note that workflows will only be executed on the restarted realizations and that this might have unexpected consequences.")
        msg.setWindowTitle("Restart Failed Realizations")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        result = msg.exec_()

        if result == QMessageBox.Ok:
            active_realizations = self.create_mask_from_failed_realizations()
            self._simulations_argments['active_realizations'] = active_realizations
            self._simulations_argments['prev_successful_realizations'] += self.count_successful_realizations()
            self.startSimulation(self._simulations_argments)

    def update_realizations_view(self):
        completed = self._run_model.completed_realizations_mask
        for (index, successful) in enumerate(completed):
            items = self.realizations_view.model().findItems(str(index))
            if not items:
                item = QStandardItem(str(index))
                self.realizations_view.model().appendRow(item)
            else:
                item = items[0]
            item.setCheckState(successful or item.checkState())

    def show_detailed_progress(self):
        if not self.detailed_progress:
            self.detailed_progress = DetailedProgressDialog(self, self.simulations_tracker.getStates())
        self.detailed_progress.set_progress(*self._run_model.getDetailedProgress())
        self.detailed_progress.show()