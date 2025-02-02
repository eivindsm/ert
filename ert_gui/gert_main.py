#  Copyright (C) 2011  Equinor ASA, Norway.
#
#  The file 'gert_main.py' is part of ERT - Ensemble based Reservoir Tool.
#
#  ERT is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  ERT is distributed in the hope that it will be useful, but WITHOUT ANY
#  WARRANTY; without even the implied warranty of MERCHANTABILITY or
#  FITNESS FOR A PARTICULAR PURPOSE.
#
#  See the GNU General Public License at <http://www.gnu.org/licenses/gpl.html>
#  for more details.

# --------------------------------------------------------------------------------
# This file is the main script of the ert with graphical UI, e.g. gert or
# ert_gui. To run successfully the ert GUI requires a quite well prepared
# environment. This includes the following:
#
#  1. A Python interpreter with the the ctypes library available.
#
#  2. The program must be able to locate all the required shared libraries with
#     no fuss. This includes:
#
#       o The ert libraries libecl.so, libenkf.so, libutil.so, librms.so,
#         libsched.so, libconfig.so
#
#       o The libraries used by the ert libraries, this includes liblapack.so,
#         libz.so, libblas.so, libpthread.so and in some cases the libg2c.so
#         library.
#
#       o The lsf libraries libbat, liblsf and also libnsl. In the current
#         implementation the dependance on the lsf libraries is hard, this should
#         be relaxed so that the lsf libraries are not linked before an attempt to
#         actually use lsf is made.
#         When an attempt is actually made to use LSF the additional environment
#         variables LSF_LIBDIR, XLSF_UIDDIR, LSF_SERVERDIR, LSF_ENVDIR and
#         LSF_BINDIR must also be set. That is an LSF requirement and not
#         related to ert as such. These variables can naturally be set from the
#         site config file.
#
#
#  3. The program must be able to locate all the necessary Python modules, in
#     short this means that the directory containing the ert/ and ert_gui/
#     directories must be on Python path, i.e. the import statements
#
#        import ert
#        import ert_gui
#
#     should just work.
#
#  4. The environment variable GERT_SHARE_PATH should be set to point to the
#     /share directory of the current gert installation. The /share directory
#     contains html help files and images/icons.
#
#  5. The environment variable ERT_SITE_CONFIG must be set to point to the site
#     wide configuration file.
#
#
# Now the important point is that this python script WILL NOT PERFORM ANY
# SPECIAL HOOPS TO TRY TO LOCATE THE REQUIRED FILES, i.e. the environment must
# be fully prepared prior to invoking this script. This will typically involve:
#
#  1. Update the LD_LIBRARY_PATH variable to contain directories with all the
#     required shared libraries.
#
#  2. Update the PYTHONPATH variable to contain the directory containg ert/ and
#     ert_gui/ directories.
#
#  3. Set the environment variabel GERT_SHARE_PATH to point to the directory
#     containg the /share files for the current gert installation.
#
#  4. Set the environment variable ERT_SITE_CONFIG to point to the location of
#     the site configuration file.
#
# An example shell script achieving this could look like:
#
# -------------------- <Example shell script> --------------------
#  #!/bin/bash
#
#  # The LSF libraries are installed in directory /site/LSF/7.0/linux/lib, this
#  # directory must be included in the LD_LIBRARY_PATH variable. Furthermore we
#  # assume that the ERT libraries like libecl.so and libenkf.so are located in
#  # /opt/ert/lib, then LD_LIBRARY_PATH will be updated as:
#
#  export LD_LIBRARY_PATH=/site/LSF/7.0/linux/lib:/opt/ert/lib:$LD_LIBRARY_PATH
#
#  # The python modules ert and ert_gui are located in /opt/ert/python, so we
#  # update PYTHONPATH as:
#
#  export PYTHONPATH=/opt/ert/python:$PYTHONPATH
#
#  # The shared gert files are installed in /opt/ert/share; this directory can
#  # in principle be shared among gert versions built for different operating
#  # system versions:
#
#  export ERT_SHARE_PATH=/opt/ert/share
#
#  # The ERT site configuration file is assumed to be in
#  # /opt/ert/etc/site-config, i.e. we set the variable ERT_SITE_CONFIG as:
#
#  export ERT_SITE_CONFIG=/opt/ert/etc/site-config
#
#  # Now the environment should be fully initialized, and we are ready to invoke
#  # the gert_main.py script, i.e. this file:
#
#  exec python /opt/ert/python/ert_gui/gert_main.py $@
#
# -------------------- </Example shell script> --------------------
import sys

try:
  from PyQt4.QtCore import Qt, QLocale
  from PyQt4.QtGui import QApplication, QFileDialog, QMessageBox
except ImportError:
  from PyQt5.QtCore import Qt, QLocale
  from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox


from ert_gui.ert_splash import ErtSplash
from ert_gui.ertwidgets import SummaryPanel, resourceIcon
import ert_gui.ertwidgets
from ert_gui.main_window import GertMainWindow
from ert_gui.newconfig import NewConfigurationDialog
from ert_gui.simulation.simulation_panel import SimulationPanel
from ert_gui.tools import HelpCenter
from ert_gui.tools.export import ExportTool
from ert_gui.tools.help import HelpTool
from ert_gui.tools.ide import IdeTool
from ert_gui.tools.load_results import LoadResultsTool
from ert_gui.tools.manage_cases import ManageCasesTool
from ert_gui.tools.plot import PlotTool
from ert_gui.tools.plugins import PluginHandler, PluginsTool
from ert_gui.tools.run_analysis import RunAnalysisTool
from ert_gui.tools.workflows import WorkflowsTool
import os
from res.enkf import EnKFMain, ResConfig
from res.util import ResLog

import res
import ecl
import sys
import time


def main(argv):
    app = QApplication(argv)  # Early so that QT is initialized before other imports
    app.setWindowIcon(resourceIcon("application/window_icon_cutout"))

    # There seems to be a setlocale() call deep down in the initialization of
    # QApplication, if the user has set the LC_NUMERIC environment variables to
    # a locale with decimalpoint different from "." the application will fail
    # hard quite quickly.
    current_locale = QLocale()
    decimal_point = str(current_locale.decimalPoint())
    if decimal_point != ".":
        msg = """
** WARNING: You are using a locale with decimalpoint: '{}' - the ert application is
            written with the assumption that '.' is used as decimalpoint, and chances
            are that something will break if you continue with this locale. It is highly
            reccomended that you set the decimalpoint to '.' using one of the environment
            variables 'LANG', LC_ALL', or 'LC_NUMERIC' to either the 'C' locale or
            alternatively a locale which uses '.' as decimalpoint.\n""".format(decimal_point)

        sys.stderr.write(msg)


    if len(argv) == 1:
        config_file = QFileDialog.getOpenFileName(None, "Open Configuration File")

        config_file = str(config_file)

        if len(config_file) == 0:
            print("-----------------------------------------------------------------")
            print("-- You must supply the name of configuration file as the first --")
            print("-- commandline argument:                                       --")
            print("--                                                             --")
            print("-- bash%  gert <config_file>                                   --")
            print("--                                                             --")
            print("-- If the configuration file does not exist, gert will create  --")
            print("-- create a new configuration file.                            --")
            print("-----------------------------------------------------------------")

            sys.exit(1)
    else:
        config_file = argv[1]

    help_center = HelpCenter("ERT")
    help_center.setHelpMessageLink("welcome_to_ert")

    strict = True

    verbose = False
    verbose_var = os.getenv("ERT_VERBOSE", "False")
    lower_verbose_var = verbose_var.lower()
    if lower_verbose_var == "true":
        verbose = True

    if not os.path.exists(config_file):
        print("Trying to start new config")
        new_configuration_dialog = NewConfigurationDialog(config_file)
        success = new_configuration_dialog.exec_()
        if not success:
            print("Can not run without a configuration file.")
            sys.exit(1)
        else:
            config_file = new_configuration_dialog.getConfigurationPath()
            dbase_type = new_configuration_dialog.getDBaseType()
            num_realizations = new_configuration_dialog.getNumberOfRealizations()
            storage_path = new_configuration_dialog.getStoragePath()

            EnKFMain.createNewConfig(config_file, storage_path, dbase_type, num_realizations)
            strict = False

    if os.path.isdir(config_file):
        print("The specified configuration file is a directory!")
        sys.exit(1)

    splash = ErtSplash()
    splash.version = "Version %s" % ert_gui.__version__

    splash.show()
    splash.repaint()

    now = time.time()

    res_config = ResConfig(config_file)
    os.chdir( res_config.config_path )
    ert = EnKFMain(res_config, strict=strict, verbose=verbose)
    ert_gui.configureErtNotifier(ert, config_file)

    window = GertMainWindow()
    window.setWidget(SimulationPanel())

    plugin_handler = PluginHandler(ert, ert.getWorkflowList().getPluginJobs(), window)

    help_tool = HelpTool("ERT", window)

    window.addDock("Configuration Summary", SummaryPanel(), area=Qt.BottomDockWidgetArea)
    window.addTool(IdeTool(os.path.basename(config_file), help_tool))
    window.addTool(PlotTool())
    window.addTool(ExportTool())
    window.addTool(WorkflowsTool())
    window.addTool(ManageCasesTool())
    window.addTool(PluginsTool(plugin_handler))
    window.addTool(RunAnalysisTool())
    window.addTool(LoadResultsTool())
    window.addTool(help_tool)
    window.adjustSize()
    sleep_time = 2 - (time.time() - now)

    if sleep_time > 0:
        time.sleep(sleep_time)

    window.show()
    splash.finish(window)
    window.activateWindow()
    window.raise_()
    ResLog.log(3, "Versions: ecl:%s    res:%s    ert:%s" % (ecl.__version__, res.__version__, ert_gui.__version__))
    
    if not ert._real_enkf_main().have_observations():
        em = QMessageBox.warning(window, "Warning!", "No observations loaded. Model update algorithms disabled!")
        
    
    finished_code = app.exec_()
    sys.exit(finished_code)


if __name__ == "__main__":
    main(sys.argv)
