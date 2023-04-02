from gitfourchette.qt import *
from gitfourchette.toolbox import excMessageBox, NonCriticalOperation
import os
import signal
import sys


def excepthook(exctype, value, tb):
    sys.__excepthook__(exctype, value, tb)  # run default excepthook
    excMessageBox(value, printExc=False)


def makeCommandLineParser() -> QCommandLineParser:
    parser = QCommandLineParser()
    parser.addHelpOption()
    parser.addVersionOption()
    parser.addOption(QCommandLineOption(["test-mode"], "Prevents loading/saving of user preferences."))
    parser.addPositionalArgument("repos", "Paths to repositories to open on launch.", "[repos...]")
    return parser


def main():
    # Quit app cleanly on Ctrl+C (all repos and associated file handles will be freed)
    signal.signal(signal.SIGINT, lambda *args: QApplication.quit())

    # inject our own exception hook to show an error dialog in case of unhandled exceptions
    # (note that this may get overridden when running under a debugger)
    sys.excepthook = excepthook

    # initialize Qt before importing app modules so fonts are loaded correctly
    app = QApplication(sys.argv)
    app.setApplicationName("GitFourchette")  # used by QStandardPaths
    # Don't use app.setOrganizationName because it changes QStandardPaths.
    app.setApplicationVersion("1.0.0")

    # Force Python interpreter to run every now and then so it can run the Ctrl+C signal handler
    # (Otherwise the app won't actually die until the window regains focus, see https://stackoverflow.com/q/4938723)
    if __debug__:
        timer = QTimer()
        timer.start(300)
        timer.timeout.connect(lambda: None)

    # Initialize command line options
    commandLine = makeCommandLineParser()
    commandLine.process(app)

    # Initialize assets
    with NonCriticalOperation("Initialize assets"):
        QDir.addSearchPath("assets", os.path.join(os.path.dirname(__file__), "assets"))
        app.setWindowIcon(QIcon("assets:gitfourchette.png"))

    from gitfourchette import settings
    from gitfourchette import log

    # Get system default style name before applying further styling
    with NonCriticalOperation("Get system default style name"):
        app.PLATFORM_DEFAULT_STYLE_NAME = app.style().objectName()

    # Initialize settings
    if commandLine.isSet("test-mode"):
        settings.TEST_MODE = True
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

    # Initialize global shortcuts
    from gitfourchette.globalshortcuts import GlobalShortcuts
    GlobalShortcuts.initialize()

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

    def bootMainWindow():
        from gitfourchette.widgets.mainwindow import MainWindow
        MainWindow.reloadStyleSheet()
        window = MainWindow()
        window.show()
        window.restoreSession(session)

    # Boot main window first thing when event loop starts
    QTimer.singleShot(0, bootMainWindow)

    # Keep the app running
    app.exec()


if __name__ == "__main__":
    main()
