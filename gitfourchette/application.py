from __future__ import annotations
from typing import TYPE_CHECKING, Type
import logging
import os

# Import as few internal modules as possible here to avoid premature initialization
# from cascading imports before the QApplication has booted.
from gitfourchette.qt import *

if TYPE_CHECKING:
    from gitfourchette.mainwindow import MainWindow
    from gitfourchette.settings import Session
    from gitfourchette.tasks import RepoTask

logger = logging.getLogger(__name__)


class GFApplication(QApplication):
    mainWindow: MainWindow | None
    initialSession: Session | None
    installedTranslators: list

    @staticmethod
    def instance() -> GFApplication:
        me = QApplication.instance()
        assert isinstance(me, GFApplication)
        return me

    def __init__(self, argv: list[str], bootScriptPath: str = "", ):
        super().__init__(argv)

        if not bootScriptPath and argv:
            bootScriptPath = argv[0]

        self.setObjectName("GFApplication")

        self.mainWindow = None
        self.initialSession = None
        self.installedTranslators = []

        # Don't use app.setOrganizationName because it changes QStandardPaths.
        self.setApplicationName(APP_SYSTEM_NAME)  # used by QStandardPaths
        self.setApplicationDisplayName(APP_DISPLAY_NAME)  # user-friendly name
        self.setApplicationVersion(APP_VERSION)
        self.setDesktopFileName(APP_IDENTIFIER)  # Wayland uses this to resolve window icons

        commandLine = GFApplication.makeCommandLineParser()
        commandLine.process(argv)

        from gitfourchette.toolbox import NonCriticalOperation
        from gitfourchette.globalshortcuts import GlobalShortcuts
        from gitfourchette.tasks import TaskBook, TaskInvoker
        from gitfourchette import settings

        with NonCriticalOperation("Asset search"):
            # Add asset search path relative to boot script
            assetSearchPath = os.path.join(os.path.dirname(bootScriptPath), "assets")
            QDir.addSearchPath("assets", assetSearchPath)

            if not (MACOS and APP_FROZEN):  # macOS app bundle automatically uses the .icns - it's designed to blend in well in a Mac environment
                self.setWindowIcon(QIcon("assets:icons/gitfourchette.png"))

        # Get system default style name before applying further styling
        with NonCriticalOperation("Get system default style name"):
            self.PLATFORM_DEFAULT_STYLE_NAME = self.style().objectName()

        # Initialize settings
        if commandLine.isSet("debug"):
            settings.DEVDEBUG = True

        if commandLine.isSet("no-threads"):
            settings.SYNC_TASKS = True

        if commandLine.isSet("test-mode"):
            settings.TEST_MODE = True
            settings.SYNC_TASKS = True

            # Force English in unit tests regardless of the host machine's locale
            # because many unit tests look for pieces of text in dialogs.
            settings.prefs.language = "en"
        else:
            # Load settings
            with NonCriticalOperation(F"Loading prefs"):
                settings.prefs.load()
                self.applyQtStylePref(forceApplyDefault=False)

            # Load history
            with NonCriticalOperation(F"Loading history"):
                settings.history.load()

        if settings.TEST_MODE:
            self.setApplicationName(APP_SYSTEM_NAME + "_unittest")

        # Set logging level
        self.applyLoggingLevelPref()

        # Set language
        with NonCriticalOperation("Loading language"):
            self.applyLanguagePref()

        # Initialize session
        session = settings.Session()
        if not settings.TEST_MODE:
            with NonCriticalOperation(F"Loading session"):
                session.load()

        # Open paths passed in via the command line
        pathList = commandLine.positionalArguments()
        if pathList:
            session.tabs += [os.path.abspath(p) for p in pathList]
            session.activeTabIndex = len(session.tabs) - 1

        # Keep track of initial session
        self.initialSession = session

        # Initialize global shortcuts
        GlobalShortcuts.initialize()

        # Initialize task book
        TaskBook.initialize()
        TaskInvoker.instance().invokeSignal.connect(self.onInvokeTask)

        # Boot main window first thing when event loop starts
        if not settings.TEST_MODE:
            QTimer.singleShot(0, self.bootUi)

    def bootUi(self):
        from gitfourchette.mainwindow import MainWindow
        from gitfourchette.toolbox import bquo
        from gitfourchette.settings import QtApiNames

        assert self.mainWindow is None, "already have a MainWindow"

        self.aboutToQuit.connect(self.onAboutToQuit)

        MainWindow.reloadStyleSheet()
        self.mainWindow = MainWindow()
        self.mainWindow.destroyed.connect(self.onMainWindowDestroyed)

        if self.initialSession is None:
            self.mainWindow.show()
        else:
            # To prevent flashing a window with incorrect dimensions,
            # restore the geometry BEFORE calling show()
            self.mainWindow.restoreGeometry(self.initialSession.windowGeometry)
            self.mainWindow.show()

            self.mainWindow.restoreSession(self.initialSession)
            self.initialSession = None

        if QT_BINDING_BOOTPREF and QT_BINDING_BOOTPREF.lower() != QT_BINDING.lower():
            try:
                QtApiNames(QT_BINDING_BOOTPREF.lower())  # raises ValueError if not recognized
                text = translate("Prefs", "Your preferred Qt binding {0} is not available on this machine.")
            except ValueError:
                text = translate("Prefs", "Your preferred Qt binding {0} is not recognized by {app}. "
                                          "(Supported values: {known})")
            text += "<p>"
            text += translate("Prefs", "Using {1} instead.", "falling back to default Qt binding instead of the user's choice")
            text = text.format(bquo(QT_BINDING_BOOTPREF), bquo(QT_BINDING.lower()), app=qAppName(),
                               known=", ".join(e for e in QtApiNames if e))

            QMessageBox.information(self.mainWindow, translate("Prefs", "Qt binding unavailable"), text)

    def onMainWindowDestroyed(self):
        logger.debug("Main window destroyed")
        self.mainWindow = None

    def onAboutToQuit(self):
        from gitfourchette import settings
        if settings.prefs.isDirty():
            settings.prefs.write()
        if settings.history.isDirty():
            settings.history.write()

    @staticmethod
    def makeCommandLineParser() -> QCommandLineParser:
        parser = QCommandLineParser()
        parser.addHelpOption()
        parser.addVersionOption()
        parser.addOption(QCommandLineOption(["no-threads", "n"], "Turn off multithreading (run all tasks on UI thread)."))
        parser.addOption(QCommandLineOption(["debug", "d"], "Enable expensive assertions and development features."))
        parser.addOption(QCommandLineOption(["test-mode"], "Prevent loading/saving user preferences."))
        parser.addPositionalArgument("repos", "Repository paths to open on launch.", "[repos...]")
        return parser

    # -------------------------------------------------------------------------

    def onInvokeTask(self, invoker: QObject, taskType: Type[RepoTask], args: tuple, kwargs: dict) -> RepoTask | None:
        from gitfourchette.mainwindow import MainWindow
        from gitfourchette.repowidget import RepoWidget
        from gitfourchette.toolbox import showInformation

        if self.mainWindow is None:
            logging.warning(f"Ignoring task request {taskType.__name__} because we don't have a window")
            return

        assert isinstance(invoker, QObject)
        if invoker.signalsBlocked():
            logger.debug("Ignoring task request {0} from invoker with blocked signals: {1}"
                         .format(taskType.__name__, invoker.objectName() or invoker.__class__.__name__))
            return

        # Find parent in hierarchy
        candidate = invoker
        while candidate is not None:
            if isinstance(candidate, (RepoWidget, MainWindow)):
                break
            candidate = candidate.parent()

        if isinstance(candidate, RepoWidget):
            repoWidget = candidate
        elif isinstance(candidate, MainWindow):
            repoWidget = candidate.currentRepoWidget()
            if repoWidget is None:
                showInformation(candidate, taskType.name(),
                                self.tr("Please open a repository before performing this action."))
                return
        else:
            repoWidget = None

        if repoWidget is None:
            assert False, "RepoTasks must be invoked from a child of RepoWidget or MainWindow"
            return

        return repoWidget.runTask(taskType, *args, **kwargs)

    # -------------------------------------------------------------------------

    def flushTranslators(self):
        while self.installedTranslators:
            self.removeTranslator(self.installedTranslators.pop())

    def loadTranslator(self, locale, fileName: str, prefix: str = "", searchDelimiters: str = "", suffix: str = ""):
        newTranslator = QTranslator(self)

        if newTranslator.load(locale, fileName, prefix, searchDelimiters, suffix):
            self.installTranslator(newTranslator)
            self.installedTranslators.append(newTranslator)
            return True
        else:
            # logger.info(f"The app does not support your locale: {locale.uiLanguages()}")
            newTranslator.deleteLater()
            return False

    def applyLanguagePref(self):
        from gitfourchette import settings

        self.flushTranslators()

        preferredLanguage = settings.prefs.language

        if preferredLanguage:
            locale = QLocale(preferredLanguage)
        else:
            locale = QLocale()  # "Automatic" setting: Get system locale

        # Force English locale for RTL languages. RTL support isn't great for now,
        # and we have no localizations for RTL languages yet anyway.
        if locale.textDirection() != Qt.LayoutDirection.LeftToRight:
            locale = QLocale(QLocale.Language.English)

        # Set default locale
        QLocale.setDefault(locale)

        # Try to load app translations for the preferred language first.
        # If that failed, load the English translations for proper numerus forms.
        appTranslatorAssetParams = ["gitfourchette", "_", "assets:lang/", ".qm"]
        if not self.loadTranslator(locale, *appTranslatorAssetParams):
            self.loadTranslator(QLocale(QLocale.Language.English), *appTranslatorAssetParams)

        # Load Qt base translation
        if not QT5:  # Do this on Qt 6 and up only
            try:
                qtTranslationsDir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
                self.loadTranslator(locale, "qtbase", "_", qtTranslationsDir)
            except Exception:
                logger.warning(f"Failed to load Qt base translation for language: {preferredLanguage}", exc_info=True)

        # Retranslate TrTables
        from gitfourchette.trtables import TrTables
        TrTables.retranslateAll()

    def applyQtStylePref(self, forceApplyDefault: bool):
        from gitfourchette import settings

        if settings.prefs.qtStyle:
            self.setStyle(settings.prefs.qtStyle)
        elif forceApplyDefault:
            self.setStyle(self.PLATFORM_DEFAULT_STYLE_NAME)

        if MACOS:
            isNativeStyle = settings.qtIsNativeMacosStyle()
            self.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, isNativeStyle)

    def applyLoggingLevelPref(self):
        from gitfourchette import settings

        logging.root.setLevel(settings.prefs.debug_verbosity.value)

    # -------------------------------------------------------------------------

    def processEventsNoInput(self):
        self.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

