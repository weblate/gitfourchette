from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING, Type
import logging

# Import as few internal modules as possible here to avoid premature initialization
# from cascading imports before the QApplication has booted.
from gitfourchette.qt import *

if TYPE_CHECKING:
    from gitfourchette.mainwindow import MainWindow
    from gitfourchette.settings import Session
    from gitfourchette.tasks import RepoTask
    from gitfourchette.porcelain import GitConfig

logger = logging.getLogger(__name__)


class GFApplication(QApplication):
    mainWindow: MainWindow | None
    initialSession: Session | None
    installedLocale: QLocale | None
    installedTranslators: list
    tempDir: QTemporaryDir
    sessionwideGitConfigPath: str
    sessionwideGitConfig: GitConfig

    @staticmethod
    def instance() -> GFApplication:
        me = QApplication.instance()
        assert isinstance(me, GFApplication)
        return me

    def __init__(self, argv: list[str], bootScriptPath: str = "", ):
        super().__init__(argv)
        self.setObjectName("GFApplication")

        if not bootScriptPath and argv:
            bootScriptPath = argv[0]

        self.mainWindow = None
        self.initialSession = None
        self.installedLocale = None
        self.installedTranslators = []

        # Don't use app.setOrganizationName because it changes QStandardPaths.
        self.setApplicationName(APP_SYSTEM_NAME)  # used by QStandardPaths
        self.setApplicationDisplayName(APP_DISPLAY_NAME)  # user-friendly name
        self.setApplicationVersion(APP_VERSION)
        self.setDesktopFileName(APP_IDENTIFIER)  # Wayland uses this to resolve window icons

        # Add asset search path relative to boot script
        assetSearchPath = str(Path(bootScriptPath).parent / "assets")
        QDir.addSearchPath("assets", assetSearchPath)

        # Set app icon
        # - Except in macOS app bundles, which automatically use the embedded .icns file
        # - The file extension must be spelled out in some environments (e.g. Windows)
        if not (MACOS and APP_FROZEN):
            self.setWindowIcon(QIcon("assets:icons/gitfourchette.png"))

        # Get system default style name before applying further styling
        self.platformDefaultStyleName = self.style().objectName()

        # Install translators for system language
        # (for command line parser to display localized text)
        self.installTranslators()

        # Process command line
        parser = QCommandLineParser()
        parser.setApplicationDescription(qAppName() + " - " + tr("The comfortable Git UI for Linux."))
        parser.addHelpOption()
        parser.addVersionOption()
        parser.addOptions([
            QCommandLineOption(["no-threads", "n"], self.tr("Turn off multithreading (run all tasks on UI thread).")),
            QCommandLineOption(["debug", "d"], self.tr("Enable expensive assertions and development features.")),
            QCommandLineOption(["test-mode"], self.tr("Prevent loading/saving user preferences. (implies --no-threads)")),
        ])
        parser.addPositionalArgument("repos", self.tr("Repository paths to open on launch."), "[repos...]")
        parser.process(argv)

        # Schedule cleanup on quit
        self.aboutToQuit.connect(self.endSession)

        from gitfourchette.globalshortcuts import GlobalShortcuts
        from gitfourchette.tasks import TaskBook, TaskInvoker
        from gitfourchette import settings

        # Set up global flags from command line
        if parser.isSet("debug"):
            settings.DEVDEBUG = True
        if parser.isSet("no-threads"):
            settings.SYNC_TASKS = True
        if parser.isSet("test-mode"):
            settings.TEST_MODE = True
            settings.SYNC_TASKS = True
            self.setApplicationName(APP_SYSTEM_NAME + "_TESTMODE")

        # Prepare session-wide temporary directory
        tempDirTemplate = Path(QDir.tempPath()) / (self.applicationName() + ".XXXXXX")
        self.tempDir = QTemporaryDir(str(tempDirTemplate))
        self.tempDir.setAutoRemove(True)

        # Prime singletons
        GlobalShortcuts.initialize()
        TaskBook.initialize()
        TaskInvoker.instance().invokeSignal.connect(self.onInvokeTask)

        # Get initial session tabs
        self.commandLinePaths = parser.positionalArguments()

    def beginSession(self, bootUi=True):
        from gitfourchette.toolbox.messageboxes import NonCriticalOperation
        from gitfourchette.porcelain import GitConfig
        from gitfourchette import settings

        # Make sure the temp dir exists
        tempDirPath = Path(self.tempDir.path())
        tempDirPath.mkdir(parents=True, exist_ok=True)

        # Prepare session-wide git config file
        self.sessionwideGitConfigPath = str(tempDirPath / "session.gitconfig")
        self.sessionwideGitConfig = GitConfig(self.sessionwideGitConfigPath)
        self.initializeSessionwideGitConfig()

        # Load prefs file
        settings.prefs.reset()
        with NonCriticalOperation("Loading prefs"):
            settings.prefs.load()

        # Load history file
        settings.history.reset()
        with NonCriticalOperation("Loading history"):
            settings.history.load()

        # Set logging level from prefs
        self.applyLoggingLevelPref()

        # Set language from prefs
        self.applyLanguagePref()

        # Load session file
        session = settings.Session()
        self.initialSession = session
        with NonCriticalOperation("Loading session"):
            session.load()
        if self.commandLinePaths:
            session.tabs += [str(Path(p).resolve()) for p in self.commandLinePaths]
            session.activeTabIndex = len(session.tabs) - 1

        # Boot main window first thing when event loop starts
        if bootUi:
            QTimer.singleShot(0, self.bootUi)

    def endSession(self):
        from gitfourchette import settings
        if settings.prefs.isDirty():
            settings.prefs.write()
        if settings.history.isDirty():
            settings.history.write()
        self.tempDir.remove()

    def bootUi(self):
        from gitfourchette.mainwindow import MainWindow
        from gitfourchette.toolbox import bquo
        from gitfourchette.settings import QtApiNames

        assert self.mainWindow is None, "already have a MainWindow"

        self.applyQtStylePref(forceApplyDefault=False)
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

        if QT_BINDING_BOOTPREF and QT_BINDING_BOOTPREF.lower() != QT_BINDING.lower():  # pragma: no cover
            try:
                QtApiNames(QT_BINDING_BOOTPREF.lower())  # raises ValueError if not recognized
                text = translate("Prefs", "Your preferred Qt binding {0} is not available on this machine.")
            except ValueError:
                text = translate("Prefs", "Your preferred Qt binding {0} is not recognized by {app}. (Supported values: {known})")
            text += "<p>" + translate("Prefs", "Using {1} instead.", "user's choice of Qt binding isn't available, falling back to default")
            text = text.format(bquo(QT_BINDING_BOOTPREF), bquo(QT_BINDING.lower()), app=qAppName(),
                               known=", ".join(e for e in QtApiNames if e))

            QMessageBox.information(self.mainWindow, translate("Prefs", "Qt binding unavailable"), text)

    def onMainWindowDestroyed(self):
        logger.debug("Main window destroyed")
        self.mainWindow = None

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

    def installTranslators(self, preferredLanguage: str = ""):
        from gitfourchette import settings

        if preferredLanguage:
            locale = QLocale(preferredLanguage)
        elif settings.TEST_MODE:
            # Fall back to English in unit tests regardless of the host machine's locale
            # because many unit tests look for pieces of text in dialogs.
            locale = QLocale(QLocale.Language.English)
        else:
            locale = QLocale()  # "Automatic" setting: Get system locale

        # Force English locale for RTL languages. RTL support isn't great for now,
        # and we have no localizations for RTL languages yet anyway.
        if locale.textDirection() != Qt.LayoutDirection.LeftToRight:
            locale = QLocale(QLocale.Language.English)

        # Set default locale
        QLocale.setDefault(locale)
        previousLocale = self.installedLocale
        self.installedLocale = locale

        if previousLocale is not None and locale.language() == previousLocale.language() and locale.country() == previousLocale.country():
            logger.debug("Previous locale is similar enough to new locale, not reloading translators")
            return

        # Flush all installed translators
        while self.installedTranslators:
            self.removeTranslator(self.installedTranslators.pop())

        # Try to load app translators for the preferred language first.
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

    def applyLanguagePref(self):
        from gitfourchette import settings
        from gitfourchette.trtables import TrTables
        from gitfourchette.tasks.taskbook import TaskBook

        self.installTranslators(settings.prefs.language)

        # Regenerate rosetta stones
        TrTables.retranslate()
        TaskBook.retranslate()

    def applyQtStylePref(self, forceApplyDefault: bool):
        from gitfourchette import settings

        if settings.prefs.qtStyle:
            self.setStyle(settings.prefs.qtStyle)
        elif forceApplyDefault:
            self.setStyle(self.platformDefaultStyleName)

        if MACOS:
            isNativeStyle = settings.qtIsNativeMacosStyle()
            self.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, isNativeStyle)

    def applyLoggingLevelPref(self):
        from gitfourchette import settings

        logging.root.setLevel(settings.prefs.verbosity.value)

    # -------------------------------------------------------------------------

    def processEventsNoInput(self):
        self.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    # -------------------------------------------------------------------------

    def initializeSessionwideGitConfig(self):
        # On Windows, core.autocrlf is usually set to true in the system config.
        # However, libgit2 cannot find the system config if git wasn't installed
        # with the official installer, e.g. via scoop. If a repo was cloned with
        # autocrlf=true, GF's staging area would be unusable on Windows without
        # setting autocrlf=true in the config.
        if WINDOWS:
            self.sessionwideGitConfig["core.autocrlf"] = "true"
