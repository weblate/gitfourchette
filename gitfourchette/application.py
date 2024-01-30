from __future__ import annotations
import logging
import os

# Import as few internal modules as possible here to avoid premature initialization
# from cascading imports before the QApplication has booted.
from gitfourchette.qt import *

logger = logging.getLogger(__name__)


class GFApplication(QApplication):
    _installedTranslators: list

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

        self._installedTranslators = []

        self.mainWindow = None
        self.initialSession = None

        # Don't use app.setOrganizationName because it changes QStandardPaths.
        self.setApplicationName(APP_SYSTEM_NAME)  # used by QStandardPaths
        self.setApplicationDisplayName(APP_DISPLAY_NAME)  # user-friendly name
        self.setApplicationVersion(APP_VERSION)

        commandLine = GFApplication.makeCommandLineParser()
        commandLine.process(argv)

        from gitfourchette.toolbox import NonCriticalOperation
        from gitfourchette import settings

        with NonCriticalOperation("Asset search"):
            # Add asset search path relative to boot script
            assetSearchPath = os.path.join(os.path.dirname(bootScriptPath), "assets")
            QDir.addSearchPath("assets", assetSearchPath)

            if not MACOS:  # macOS automatically uses the .icns - it's designed to blend in well in a Mac environment
                self.setWindowIcon(QIcon("assets:gitfourchette.png"))

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
            settings.prefs.language = settings.LANGUAGES[0]
            assert settings.prefs.language.startswith("en")
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

        # Boot main window first thing when event loop starts
        if not settings.TEST_MODE:
            QTimer.singleShot(0, self.bootUi)

    def bootUi(self):
        from gitfourchette.mainwindow import MainWindow
        from gitfourchette.toolbox import bquo

        MainWindow.reloadStyleSheet()
        self.mainWindow = MainWindow()

        if self.initialSession:
            # To prevent flashing a window with incorrect dimensions,
            # restore the geometry BEFORE calling show()
            self.mainWindow.restoreGeometry(self.initialSession.windowGeometry)
            self.mainWindow.show()

            self.mainWindow.restoreSession(self.initialSession)
            self.initialSession = None

        if QT_BINDING_BOOTPREF and QT_BINDING_BOOTPREF.lower() != QT_BINDING.lower():
            QMessageBox.information(
                self.mainWindow,
                translate("Prefs", "Qt binding unavailable"),
                translate("Prefs", "Your preferred Qt binding {0} is not available.<br>Using {1} instead."
                          ).format(bquo(QT_BINDING_BOOTPREF), bquo(QT_BINDING.lower())))

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

    def flushTranslators(self):
        while self._installedTranslators:
            self.removeTranslator(self._installedTranslators.pop())

    def loadTranslator(self, locale, fileName: str, prefix: str = "", searchDelimiters: str = "", suffix: str = ""):
        newTranslator = QTranslator(self)

        if newTranslator.load(locale, fileName, prefix, searchDelimiters, suffix):
            self.installTranslator(newTranslator)
            self._installedTranslators.append(newTranslator)
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
        appTranslatorAssetParams = ["gitfourchette", "_", "assets:", ".qm"]
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
