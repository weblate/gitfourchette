import os

from gitfourchette.qt import *
from gitfourchette.toolbox import NonCriticalOperation
from gitfourchette import settings
from gitfourchette import log


class GFApplication(QApplication):
    def __init__(self, argv: list[str], bootScriptPath: str):
        super().__init__(argv)

        self.setObjectName("GFApplication")

        self.mainWindow = None
        self.initialSession = None

        # Don't use app.setOrganizationName because it changes QStandardPaths.
        self.setApplicationName(APP_NAME)  # used by QStandardPaths
        self.setApplicationDisplayName(APP_DISPLAY_NAME)  # user-friendly name
        self.setApplicationVersion(APP_VERSION)

        commandLine = GFApplication.makeCommandLineParser()
        commandLine.process(argv)

        with NonCriticalOperation("Asset search"):
            # Add asset search path relative to boot script
            QDir.addSearchPath("assets", os.path.join(os.path.dirname(bootScriptPath), "assets"))

            if not MACOS:  # macOS automatically uses the .icns - it's designed to blend in well in a Mac environment
                self.setWindowIcon(QIcon("assets:gitfourchette.png"))

        # Get system default style name before applying further styling
        with NonCriticalOperation("Get system default style name"):
            self.PLATFORM_DEFAULT_STYLE_NAME = self.style().objectName()

        # Initialize settings
        if commandLine.isSet("sync-tasks"):
            settings.SYNC_TASKS = True

        if commandLine.isSet("test-mode"):
            settings.TEST_MODE = True
            settings.SYNC_TASKS = True
        else:
            # Load settings
            with NonCriticalOperation(F"Loading {settings.prefs.filename}"):
                settings.prefs.load()
                settings.applyQtStylePref(forceApplyDefault=False)

            # Load history
            with NonCriticalOperation(F"Loading {settings.history.filename}"):
                settings.history.load()

        log.setVerbosity(settings.prefs.debug_verbosity.value)

        # Set language
        with NonCriticalOperation("Loading language"):
            settings.applyLanguagePref()

        # Initialize session
        session = settings.Session()
        if not settings.TEST_MODE:
            with NonCriticalOperation(F"Loading {session.filename}"):
                session.load()

        # Open paths passed in via the command line
        pathList = commandLine.positionalArguments()
        if pathList:
            session.tabs += [os.path.abspath(p) for p in pathList]
            session.activeTabIndex = len(session.tabs) - 1

        # Keep track of initial session
        self.initialSession = session

        # Boot main window first thing when event loop starts
        QTimer.singleShot(0, self.bootUi)

    def bootUi(self):
        from gitfourchette.mainwindow import MainWindow

        MainWindow.reloadStyleSheet()
        self.mainWindow = MainWindow()
        self.mainWindow.show()

        if self.initialSession:
            self.mainWindow.restoreSession(self.initialSession)
            self.initialSession = None

        if qtBindingBootPref and qtBindingBootPref.lower() != qtBindingName.lower():
            QMessageBox.information(
                self.mainWindow,
                translate("Prefs", "Qt binding unavailable"),
                translate("Prefs", "Your preferred Qt binding “{0}” is not available.\nUsing “{1}” instead."
                          ).format(qtBindingBootPref, qtBindingName.lower()))

    @staticmethod
    def makeCommandLineParser() -> QCommandLineParser:
        parser = QCommandLineParser()
        parser.addHelpOption()
        parser.addVersionOption()
        parser.addOption(QCommandLineOption(["test-mode"], "Prevents loading/saving of user preferences."))
        parser.addOption(QCommandLineOption(["sync-tasks"], "Run tasks synchronously on UI thread."))
        parser.addPositionalArgument("repos", "Paths to repositories to open on launch.", "[repos...]")
        return parser
