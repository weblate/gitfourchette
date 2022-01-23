from allqt import *
from widgets.diffmodel import DiffModelError
import html


class RichDiffView(QTextBrowser):
    def replaceDocument(self, newDocument: QTextDocument):
        if self.document():
            self.document().deleteLater()

        self.setDocument(newDocument)
        self.clearHistory()

    def displayDiffModelError(self, dme: DiffModelError):
        document = QTextDocument()

        pixmap = QApplication.style().standardIcon(dme.icon).pixmap(48, 48)
        document.addResource(QTextDocument.ImageResource, QUrl("icon"), pixmap)

        document.setHtml(
            "<table width='100%'>"
            "<tr>"
            "<td><img src='icon'/></td>"
            "<td width=8></td>"
            F"<td width='100%'><big>{dme.message}</big><br/>{dme.details}</td>"
            "</tr>"
            "</table>"
            F"<pre>{html.escape(dme.preformatted)}</pre>")

        self.replaceDocument(document)