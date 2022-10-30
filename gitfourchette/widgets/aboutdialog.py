from gitfourchette.qt import *
import pygit2
import sys


def getPygit2FeatureStrings():
    featureNames = {
        pygit2.GIT_FEATURE_SSH: "ssh",
        pygit2.GIT_FEATURE_HTTPS: "https",
        pygit2.GIT_FEATURE_THREADS: "threads"
    }
    featureList = []
    for mask, name in featureNames.items():
        if pygit2.features & mask:
            featureList.append(name)
    return featureList


def showAboutDialog(parent: QWidget):
    try:
        import gitfourchette._buildconstants
        buildDateLine = (translate("AboutDialog", "Built on:", "when the software was built") +
                         " <b>" + gitfourchette._buildconstants.buildDate + "</b><br/>")
    except ImportError:
        buildDateLine = ""

    appName = QApplication.applicationDisplayName()
    appVersion = QApplication.applicationVersion()

    tagLine = translate("AboutDialog", "The comfy Git UI for Linux.")
    haveFun = translate("AboutDialog", "Have fun!")
    title = translate("AboutDialog", "About {0} {1}").format(appName, appVersion)
    supportMe = translate("AboutDialog", "Support me on Ko-fi")

    aboutText = F"""\
        <span style="font-size: xx-large">
            {appName}
            <b>{appVersion}</b>
        </span>
        <p>
            {tagLine}
            <br><a href="https://github.com/jorio/gitfourchette">https://github.com/jorio/gitfourchette</a>
        </p>
        <p>
            &copy; 2020-2022 Iliyas Jorio
        </p>
        <p><small>
            {buildDateLine}
            libgit2         <b>{pygit2.LIBGIT2_VERSION}</b><br>
            pygit2          <b>{pygit2.__version__}</b> (with {', '.join(getPygit2FeatureStrings())})<br>
            Qt              <b>{qVersion()}</b><br>
            {qtBindingName} <b>{qtBindingVersion}</b><br>
            Python          <b>{'.'.join(str(i) for i in sys.version_info)}</b>
        </small></p>
        <p>
            {haveFun}
        </p>
        <p>
            <a href="https://ko-fi.com/jorio"><img src="assets:kofi.png" height="32" alt="{supportMe}"></a>
        </p>
        """

    QMessageBox.about(parent, title, aboutText)
