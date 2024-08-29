from __future__ import annotations

import logging
import os
import re
from bisect import bisect_left, bisect_right

from gitfourchette import colors
from gitfourchette import settings
from gitfourchette.application import GFApplication
from gitfourchette.diffview.diffdocument import DiffDocument, LineData
from gitfourchette.diffview.diffgutter import DiffGutter
from gitfourchette.diffview.diffrubberband import DiffRubberBand
from gitfourchette.exttools import openPrefsDialog
from gitfourchette.forms.searchbar import SearchBar
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.nav import NavLocator, NavContext, NavFlags
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.subpatch import extractSubpatch
from gitfourchette.tasks import ApplyPatch, RevertPatch
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)


class DiffSearchHighlighter(QSyntaxHighlighter):
    def __init__(self, parent):
        super().__init__(parent)

        self.highlightFormat = QTextCharFormat()
        self.highlightFormat.setBackground(colors.yellow)
        self.highlightFormat.setFontWeight(QFont.Weight.Bold)

    def highlightBlock(self, text: str):
        searchBar = self.parent().searchBar
        if not searchBar.isVisible():
            return

        term = searchBar.searchTerm
        if not term:
            return
        termLength = len(term)

        text = text.lower()
        textLength = len(text)

        index = 0
        while index < textLength:
            index = text.find(term, index)
            if index < 0:
                break
            self.setFormat(index, termLength, self.highlightFormat)
            index += termLength


class DiffView(QPlainTextEdit):
    DetachedWindowObjectName = "DiffViewDetachedWindow"

    contextualHelp = Signal(str)
    selectionActionable = Signal(bool)

    lineData: list[LineData]
    lineCursorStartCache: list[int]
    lineHunkIDCache: list[int]
    currentLocator: NavLocator
    currentPatch: Patch | None
    currentWorkdirFileStat: os.stat_result | None
    repo: Repo | None
    isDetachedWindow: bool

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setReadOnly(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)

        # First-time init so callbacks don't crash looking for missing attributes
        self.lineData = []
        self.lineCursorStartCache = []
        self.lineHunkIDCache = []
        self.currentLocator = NavLocator()
        self.currentPatch = None
        self.repo = None
        self.isDetachedWindow = False

        # Highlighter for search terms
        self.highlighter = DiffSearchHighlighter(self)

        self.gutter = DiffGutter(self)
        self.gutter.customContextMenuRequested.connect(lambda p: self.execContextMenu(self.gutter.mapToGlobal(p)))
        self.updateRequest.connect(self.gutter.onParentUpdateRequest)
        # self.blockCountChanged.connect(self.updateGutterWidth)
        self.syncViewportMarginsWithGutter()

        # Emit contextual help with non-empty selection
        self.cursorPositionChanged.connect(self.emitSelectionHelp)
        self.selectionChanged.connect(self.emitSelectionHelp)
        self.cursorPositionChanged.connect(self.updateRubberBand)
        self.selectionChanged.connect(self.updateRubberBand)

        self.searchBar = SearchBar(self, self.tr("Find in Diff"))
        # self.searchBar.textChanged.connect(self.onSearchTextChanged)
        self.searchBar.textChanged.connect(self.highlighter.rehighlight)
        self.searchBar.searchNext.connect(lambda: self.search(SearchBar.Op.NEXT))
        self.searchBar.searchPrevious.connect(lambda: self.search(SearchBar.Op.PREVIOUS))
        self.searchBar.visibilityChanged.connect(lambda: self.highlighter.rehighlight())
        self.searchBar.hide()

        self.rubberBand = DiffRubberBand(self.viewport())
        self.rubberBand.hide()

        # Initialize font & styling
        self.refreshPrefs()
        GFApplication.instance().restyle.connect(self.refreshPrefs)

    # ---------------------------------------------
    # Qt events

    def contextMenuEvent(self, event: QContextMenuEvent):
        self.execContextMenu(event.globalPos())

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.resizeGutter()
        self.updateRubberBand()

    def keyPressEvent(self, event: QKeyEvent):
        # In a detached window, we can't rely on the main window's menu bar to
        # dispatch shortcuts to us (except on macOS, which has a global main menu).
        if self.isDetachedWindow and self.processSearchKeys(event):
            return

        k = event.key()
        navContext = self.currentLocator.context
        if k in GlobalShortcuts.stageHotkeys:
            if navContext == NavContext.UNSTAGED:
                self.stageSelection()
            else:
                QApplication.beep()
        elif k in GlobalShortcuts.discardHotkeys:
            if navContext == NavContext.STAGED:
                self.unstageSelection()
            elif navContext == NavContext.UNSTAGED:
                self.discardSelection()
            else:
                QApplication.beep()
        elif k == Qt.Key.Key_Escape:
            if self.searchBar.isVisible():  # close search bar if it doesn't have focus
                self.searchBar.hide()
            else:
                QApplication.beep()
        else:
            super().keyPressEvent(event)

    def processSearchKeys(self, event: QKeyEvent):
        if keyEventMatchesMultiShortcut(event, GlobalShortcuts.find):
            self.search(SearchBar.Op.START)
        elif event.matches(QKeySequence.StandardKey.FindPrevious):
            self.search(SearchBar.Op.PREVIOUS)
        elif event.matches(QKeySequence.StandardKey.FindNext):
            self.search(SearchBar.Op.NEXT)
        else:
            return False
        return True

    # ---------------------------------------------
    # Document replacement

    def clear(self):  # override
        # Clear info about the current patch - necessary for document reuse detection to be correct when the user
        # clears the selection in a FileList and then reselects the last-displayed document.
        self.currentLocator = NavLocator()
        self.currentPatch = None

        # Clear the actual contents
        super().clear()

    def replaceDocument(self, repo: Repo, patch: Patch, locator: NavLocator, newDoc: DiffDocument):
        oldDocument = self.document()

        # Detect if we're trying to load exactly the same patch - common occurrence when moving the app back to the
        # foreground. In that case, don't change the document to prevent losing any selected text.
        if self.canReuseCurrentDocument(locator, patch, newDoc):
            if settings.DEVDEBUG:  # this check can be pretty expensive!
                assert patch.data == self.currentPatch.data

            # Delete new document
            assert newDoc.document is not oldDocument  # make sure it's not in use before deleting
            newDoc.document.deleteLater()
            newDoc.document = None  # prevent any callers from using a stale object

            # Bail now - don't change the document
            logger.debug("Don't need to regenerate diff document.")
            return

        if oldDocument:
            oldDocument.deleteLater()  # avoid leaking memory/objects, even though we do set QTextDocument's parent to this QTextEdit

        self.repo = repo
        self.currentPatch = patch
        self.currentLocator = locator

        newDoc.document.setParent(self)
        self.setDocument(newDoc.document)
        self.highlighter.setDocument(newDoc.document)

        self.lineData = newDoc.lineData
        self.lineCursorStartCache = [ld.cursorStart for ld in self.lineData]
        self.lineHunkIDCache = [ld.hunkPos.hunkID for ld in self.lineData]

        # now reset defaults that are lost when changing documents
        self.refreshPrefs()

        if self.currentPatch and len(self.currentPatch.hunks) > 0:
            lastHunk = self.currentPatch.hunks[-1]
            maxNewLine = lastHunk.new_start + lastHunk.new_lines
            maxOldLine = lastHunk.old_start + lastHunk.old_lines
            maxLine = max(maxNewLine, maxOldLine)
        else:
            maxLine = 0
        self.gutter.setMaxLineNumber(maxLine)
        self.syncViewportMarginsWithGutter()

        # Now restore cursor/scrollbar positions
        self.restorePosition(locator)

    @benchmark
    def canReuseCurrentDocument(self, newLocator: NavLocator, newPatch: Patch, newDocument: DiffDocument
                                ) -> bool:
        """Detect if we're trying to reload the same patch that's already being displayed"""

        if not self.currentLocator.isSimilarEnoughTo(newLocator):
            return False

        of1: DiffFile = self.currentPatch.delta.old_file
        nf1: DiffFile = self.currentPatch.delta.new_file
        of2: DiffFile = newPatch.delta.old_file
        nf2: DiffFile = newPatch.delta.new_file

        if not DiffFile_compare(of1, of2):
            return False

        if not DiffFile_compare(nf1, nf2):
            return False

        # Changing amount of context lines?
        if len(newDocument.lineData) != len(self.lineData):
            return False

        # All IDs must be valid
        assert of1.flags & DiffFlag.VALID_ID
        assert nf1.flags & DiffFlag.VALID_ID
        assert of2.flags & DiffFlag.VALID_ID
        assert nf2.flags & DiffFlag.VALID_ID

        return True

    # ---------------------------------------------
    # Restore position

    def restorePosition(self, locator: NavLocator):
        pos = locator.diffCursor
        lineNo = locator.diffLineNo

        # Get position at start of line
        try:
            sol = self.lineCursorStartCache[lineNo]
        except IndexError:
            sol = self.lineCursorStartCache[-1]

        # Get position at end of line
        try:
            eol = self.lineCursorStartCache[lineNo+1]
        except IndexError:
            eol = self.getMaxPosition()

        # If cursor position still falls within the same line, keep that position.
        # Otherwise, snap cursor position to start of line.
        if not (sol <= pos < eol):
            pos = sol

        # Unholy kludge to stabilize scrollbar position when QPlainTextEdit has wrapped lines
        vsb = self.verticalScrollBar()
        scrollTo = locator.diffScroll
        if self.lineWrapMode() != QPlainTextEdit.LineWrapMode.NoWrap and locator.diffScroll != 0:
            topCursor = self.textCursor()
            topCursor.setPosition(locator.diffScrollTop)
            self.setTextCursor(topCursor)
            self.centerCursor()
            scrolls = 0
            corner = self.getStableTopLeftCorner()
            while scrolls < 500 and self.cursorForPosition(corner).position() < locator.diffScrollTop:
                scrolls += 1
                scrollTo = vsb.value() + 1
                vsb.setValue(scrollTo)
            # logger.info(f"Stabilized in {scrolls} iterations - final scroll {scrollTo} vs {locator.diffScroll})"
            #               f" - char pos {self.cursorForPosition(corner).position()} vs {locator.diffScrollTop}")

        # Move text cursor
        newTextCursor = self.textCursor()
        newTextCursor.setPosition(pos)
        self.setTextCursor(newTextCursor)

        # Finally, restore the scrollbar
        vsb.setValue(scrollTo)

    def getStableTopLeftCorner(self):
        return QPoint(0, self.fontMetrics().height() // 2)

    def getPreciseLocator(self):
        corner = self.getStableTopLeftCorner()
        cfp: QTextCursor = self.cursorForPosition(corner)

        diffCursor = self.textCursor().position()
        diffLineNo = self.findLineDataIndexAt(diffCursor)
        diffScroll = self.verticalScrollBar().value()
        diffScrollTop = cfp.position()
        locator = self.currentLocator.coarse().replace(
            diffCursor=diffCursor,
            diffLineNo=diffLineNo,
            diffScroll=diffScroll,
            diffScrollTop=diffScrollTop)

        # log.info("DiffView", f"getPreciseLocator: {diffScrollTop} - {cfp.positionInBlock()}"
        #                      f" - {cfp.block().text()[cfp.positionInBlock():]}")
        return locator

    # ---------------------------------------------
    # Prefs

    def refreshPrefs(self):
        monoFont = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        if settings.prefs.font:
            monoFont.fromString(settings.prefs.font)
        self.setFont(monoFont)

        currentDocument = self.document()
        if currentDocument:
            currentDocument.setDefaultFont(monoFont)

        tabWidth = settings.prefs.tabSpaces
        self.setTabStopDistance(QFontMetricsF(monoFont).horizontalAdvance(' ' * tabWidth))
        self.refreshWordWrap()
        self.setCursorWidth(2)

        self.gutter.setFont(monoFont)
        self.syncViewportMarginsWithGutter()

        self.setProperty("dark", "true" if isDarkTheme() else "false")
        self.setStyleSheet(self.styleSheet())

    def refreshWordWrap(self):
        if settings.prefs.wordWrap:
            wrapMode = QPlainTextEdit.LineWrapMode.WidgetWidth
        else:
            wrapMode = QPlainTextEdit.LineWrapMode.NoWrap
        self.setLineWrapMode(wrapMode)

    def toggleWordWrap(self):
        settings.prefs.wordWrap = not settings.prefs.wordWrap
        settings.prefs.write()
        self.refreshWordWrap()

    # ---------------------------------------------
    # Context menu

    def contextMenu(self, globalPos: QPoint):
        # Don't show the context menu if we're empty
        if self.document().isEmpty():
            return None

        # Get position of click in document
        clickedPosition = self.cursorForPosition(self.mapFromGlobal(globalPos)).position()

        cursor: QTextCursor = self.textCursor()
        hasSelection = cursor.hasSelection()

        # Find hunk at click position
        clickedHunkID = self.findHunkIDAt(clickedPosition)
        shortHunkHeader = ""
        if clickedHunkID >= 0:
            hunk: DiffHunk = self.currentPatch.hunks[clickedHunkID]
            headerMatch = re.match(r"@@ ([^@]+) @@.*", hunk.header)
            shortHunkHeader = headerMatch.group(1) if headerMatch else f"#{clickedHunkID}"

        actions = []

        navContext = self.currentLocator.context

        if navContext == NavContext.COMMITTED:
            if hasSelection:
                actions = [
                    ActionDef(self.tr("Export Lines as Patch..."), self.exportSelection),
                    ActionDef(self.tr("Revert Lines..."), self.revertSelection),
                ]
            else:
                actions = [
                    ActionDef(self.tr("Export Hunk {0} as Patch...").format(shortHunkHeader), lambda: self.exportHunk(clickedHunkID)),
                    ActionDef(self.tr("Revert Hunk..."), lambda: self.revertHunk(clickedHunkID)),
                ]

        elif navContext == NavContext.UNTRACKED:
            if hasSelection:
                actions = [
                    ActionDef(self.tr("Export Lines as Patch..."), self.exportSelection),
                ]
            else:
                actions = [
                    ActionDef(self.tr("Export Hunk as Patch..."), lambda: self.exportHunk(clickedHunkID)),
                ]

        elif navContext == NavContext.UNSTAGED:
            if hasSelection:
                actions = [
                    ActionDef(
                        self.tr("Stage Lines"),
                        self.stageSelection,
                        "git-stage-lines",
                        shortcuts=GlobalShortcuts.stageHotkeys,
                    ),
                    ActionDef(
                        self.tr("Discard Lines"),
                        self.discardSelection,
                        "git-discard-lines",
                        shortcuts=GlobalShortcuts.discardHotkeys,
                    ),
                    ActionDef(
                        self.tr("Export Lines as Patch..."),
                        self.exportSelection
                    ),
                ]
            else:
                actions = [
                    ActionDef(
                        self.tr("Stage Hunk {0}").format(shortHunkHeader),
                        lambda: self.stageHunk(clickedHunkID),
                        "git-stage-lines",
                    ),
                    ActionDef(
                        self.tr("Discard Hunk"),
                        lambda: self.discardHunk(clickedHunkID),
                        "git-discard-lines",
                    ),
                    ActionDef(self.tr("Export Hunk as Patch..."), lambda: self.exportHunk(clickedHunkID)),
                ]

        elif navContext == NavContext.STAGED:
            if hasSelection:
                actions = [
                    ActionDef(
                        self.tr("Unstage Lines"),
                        self.unstageSelection,
                        "git-unstage-lines",
                        shortcuts=GlobalShortcuts.discardHotkeys,
                    ),
                    ActionDef(
                        self.tr("Export Lines as Patch..."),
                        self.exportSelection,
                    ),
                ]
            else:
                actions = [
                    ActionDef(
                        self.tr("Unstage Hunk {0}").format(shortHunkHeader),
                        lambda: self.unstageHunk(clickedHunkID),
                        "git-unstage-lines",
                    ),
                    ActionDef(
                        self.tr("Export Hunk as Patch..."),
                        lambda: self.exportHunk(clickedHunkID),
                    ),
                ]

        actions += [
            ActionDef.SEPARATOR,
            ActionDef(self.tr("&Word Wrap"), self.toggleWordWrap, checkState=1 if settings.prefs.wordWrap else -1),
            ActionDef(self.tr("Configure Appearance..."), lambda: openPrefsDialog(self, "font"), icon="configure"),
        ]

        bottom: QMenu = self.createStandardContextMenu()
        menu = ActionDef.makeQMenu(self, actions, bottom)
        bottom.deleteLater()  # don't need this menu anymore
        menu.setObjectName("DiffViewContextMenu")
        return menu

    def execContextMenu(self, globalPos: QPoint):  # pragma: no cover
        try:
            menu = self.contextMenu(globalPos)
            if not menu:
                return
            menu.exec(globalPos)
            menu.deleteLater()
        except Exception as exc:
            # Avoid exceptions in contextMenuEvent at all costs to prevent a crash
            excMessageBox(exc, message="Failed to create DiffView context menu")

    # ---------------------------------------------
    # Patch

    def findLineDataIndexAt(self, cursorPosition: int, firstLineDataIndex: int = 0):
        if not self.lineData:
            return -1
        index = bisect_right(self.lineCursorStartCache, cursorPosition, firstLineDataIndex)
        return index - 1

    def findHunkIDAt(self, cursorPosition: int):
        clickLineDataIndex = self.findLineDataIndexAt(cursorPosition)
        try:
            return self.lineData[clickLineDataIndex].hunkPos.hunkID
        except IndexError:
            return -1

    def getSelectedLineExtents(self):
        cursor: QTextCursor = self.textCursor()
        posStart = cursor.selectionStart()
        posEnd = cursor.selectionEnd()

        if posStart < 0 or posEnd < 0:
            return -1, -1

        # If line 1 is completely selected and the cursor has landed at the very beginning of line 2,
        # don't select line 2.
        if posEnd - posStart > 0:
            posEnd -= 1

        # Find indices of first and last LineData objects given the current selection
        biStart = self.findLineDataIndexAt(posStart)
        biEnd = self.findLineDataIndexAt(posEnd, biStart)

        return biStart, biEnd

    def isSelectionActionable(self):
        start, end = self.getSelectedLineExtents()
        if start < 0:
            return False
        for i in range(start, end+1):
            ld = self.lineData[i]
            if ld.diffLine and ld.diffLine.origin in "+-":
                return True
        return False

    def extractSelection(self, reverse=False) -> bytes:
        start, end = self.getSelectedLineExtents()
        return extractSubpatch(
            self.currentPatch,
            self.lineData[start].hunkPos,
            self.lineData[end].hunkPos,
            reverse)

    def extractHunk(self, hunkID: int, reverse=False) -> bytes:
        # Find indices of first and last LineData objects given the current hunk
        hunkFirstLineIndex = bisect_left(self.lineHunkIDCache, hunkID, 0)
        hunkLastLineIndex = bisect_left(self.lineHunkIDCache, hunkID+1, hunkFirstLineIndex) - 1

        return extractSubpatch(
            self.currentPatch,
            self.lineData[hunkFirstLineIndex].hunkPos,
            self.lineData[hunkLastLineIndex].hunkPos,
            reverse)

    def exportPatch(self, patchData: bytes):
        if not patchData:
            QApplication.beep()
            return

        def dump(path: str):
            with open(path, "wb") as file:
                file.write(patchData)

        name = os.path.basename(self.currentPatch.delta.new_file.path) + "[partial].patch"
        qfd = PersistentFileDialog.saveFile(self, "SaveFile", self.tr("Export selected lines"), name)
        qfd.fileSelected.connect(dump)
        qfd.show()

    def fireRevert(self, patchData: bytes):
        RevertPatch.invoke(self, self.currentPatch, patchData)

    def fireApplyLines(self, purpose: PatchPurpose):
        purpose |= PatchPurpose.LINES
        reverse = not (purpose & PatchPurpose.STAGE)
        patchData = self.extractSelection(reverse)
        ApplyPatch.invoke(self, self.currentPatch, patchData, purpose)

    def fireApplyHunk(self, hunkID: int, purpose: PatchPurpose):
        purpose |= PatchPurpose.HUNK
        reverse = not (purpose & PatchPurpose.STAGE)
        patchData = self.extractHunk(hunkID, reverse)
        ApplyPatch.invoke(self, self.currentPatch, patchData, purpose)

    def stageSelection(self):
        self.fireApplyLines(PatchPurpose.STAGE)

    def unstageSelection(self):
        self.fireApplyLines(PatchPurpose.UNSTAGE)

    def discardSelection(self):
        self.fireApplyLines(PatchPurpose.DISCARD)

    def exportSelection(self):
        patchData = self.extractSelection()
        self.exportPatch(patchData)

    def revertSelection(self):
        patchData = self.extractSelection(reverse=True)
        self.fireRevert(patchData)

    def stageHunk(self, hunkID: int):
        self.fireApplyHunk(hunkID, PatchPurpose.STAGE)

    def unstageHunk(self, hunkID: int):
        self.fireApplyHunk(hunkID, PatchPurpose.UNSTAGE)

    def discardHunk(self, hunkID: int):
        self.fireApplyHunk(hunkID, PatchPurpose.DISCARD)

    def exportHunk(self, hunkID: int):
        patchData = self.extractHunk(hunkID)
        self.exportPatch(patchData)

    def revertHunk(self, hunkID: int):
        patchData = self.extractHunk(hunkID, reverse=True)
        self.fireRevert(patchData)

    # ---------------------------------------------
    # Gutter

    def resizeGutter(self):
        cr: QRect = self.contentsRect()
        cr.setWidth(self.gutter.calcWidth())
        self.gutter.setGeometry(cr)

    def syncViewportMarginsWithGutter(self):
        gutterWidth = self.gutter.calcWidth()

        # Prevent Qt freeze if margin width exceeds widget width, e.g. when window is very narrow
        # (especially prevalent with word wrap?)
        self.setMinimumWidth(gutterWidth * 2)

        self.setViewportMargins(gutterWidth, 0, 0, 0)

    # ---------------------------------------------
    # Rubberband

    def updateRubberBand(self):
        textCursor: QTextCursor = self.textCursor()
        start = textCursor.selectionStart()
        end = textCursor.selectionEnd()
        assert start <= end

        if start == end == 0:
            self.rubberBand.hide()
            return

        textCursor.setPosition(start)
        textCursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)  # for wrapped lines
        top = self.cursorRect(textCursor).top()

        textCursor.setPosition(end)
        textCursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)  # for wrapped lines
        bottom = self.cursorRect(textCursor).bottom()

        pad = 4
        self.rubberBand.setGeometry(0, top-pad, self.viewport().width(), bottom-top+1+pad*2)
        self.rubberBand.show()

    # ---------------------------------------------
    # Cursor/selection

    def getMaxPosition(self):
        lastBlock = self.document().lastBlock()
        return lastBlock.position() + max(0, lastBlock.length() - 1)

    def getAnchorHomeLinePosition(self):
        cursor: QTextCursor = self.textCursor()

        # Snap anchor to start of home line
        cursor.setPosition(cursor.anchor(), QTextCursor.MoveMode.MoveAnchor)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfLine, QTextCursor.MoveMode.MoveAnchor)

        return cursor.anchor()

    def getStartOfLineAt(self, point: QPoint):
        clickedCursor: QTextCursor = self.cursorForPosition(point)
        clickedCursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
        return clickedCursor.position()

    def replaceCursor(self, cursor: QTextCursor):
        """Replace the cursor without moving the horizontal scroll bar"""
        with QScrollBackupContext(self.horizontalScrollBar()):
            self.setTextCursor(cursor)

    def selectWholeLineAt(self, point: QPoint):
        clickedPosition = self.getStartOfLineAt(point)

        cursor: QTextCursor = self.textCursor()
        cursor.setPosition(clickedPosition)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)

        self.replaceCursor(cursor)

    def selectWholeLinesTo(self, point: QPoint):
        homeLinePosition = self.getAnchorHomeLinePosition()
        clickedPosition = self.getStartOfLineAt(point)

        cursor: QTextCursor = self.textCursor()

        if homeLinePosition <= clickedPosition:
            # Move anchor to START of home line
            cursor.setPosition(homeLinePosition, QTextCursor.MoveMode.MoveAnchor)
            # Move cursor to END of clicked line
            cursor.setPosition(clickedPosition, QTextCursor.MoveMode.KeepAnchor)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        else:
            # Move anchor to END of home line
            cursor.setPosition(homeLinePosition, QTextCursor.MoveMode.MoveAnchor)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.MoveAnchor)
            # Move cursor to START of clicked line
            cursor.setPosition(clickedPosition, QTextCursor.MoveMode.KeepAnchor)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine, QTextCursor.MoveMode.KeepAnchor)

        self.replaceCursor(cursor)

    def selectClumpOfLinesAt(self, clickPoint: QPoint = None, textCursorPosition: int = -1):
        assert bool(textCursorPosition >= 0) ^ bool(clickPoint)
        if textCursorPosition < 0:
            textCursorPosition = self.getStartOfLineAt(clickPoint)

        ldList = self.lineData
        i = self.findLineDataIndexAt(textCursorPosition)
        ld = ldList[i]

        if ld.hunkPos.hunkLineNum < 0:
            # Hunk header line, select whole hunk
            start = i
            end = i
            while end < len(ldList)-1 and ldList[end+1].hunkPos.hunkID == ld.hunkPos.hunkID:
                end += 1
        elif ld.clumpID < 0:
            # Context line
            QApplication.beep()
            return
        else:
            # Get clump boundaries
            start = i
            end = i
            while start > 0 and ldList[start-1].clumpID == ld.clumpID:
                start -= 1
            while end < len(ldList)-1 and ldList[end+1].clumpID == ld.clumpID:
                end += 1

        startPosition = ldList[start].cursorStart
        endPosition = min(self.getMaxPosition(), ldList[end].cursorEnd + 1)  # +1 to select empty lines

        cursor: QTextCursor = self.textCursor()
        cursor.setPosition(startPosition, QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(endPosition, QTextCursor.MoveMode.KeepAnchor)
        self.replaceCursor(cursor)

    # ---------------------------------------------
    # Selection help

    def emitSelectionHelp(self):
        if self.currentLocator.context in [NavContext.COMMITTED, NavContext.EMPTY]:
            return

        if not self.isSelectionActionable():
            self.contextualHelp.emit("")
            self.selectionActionable.emit(False)
            return

        start, end = self.getSelectedLineExtents()
        numLines = end - start + 1

        if self.currentLocator.context == NavContext.UNSTAGED:
            if numLines <= 1:
                help = self.tr("Hit {stagekey} to stage the current line, or {discardkey} to discard it.")
            else:
                help = self.tr("Hit {stagekey} to stage the selected lines, or {discardkey} to discard them.")
        elif self.currentLocator.context == NavContext.STAGED:
            if numLines <= 1:
                help = self.tr("Hit {unstagekey} to unstage the current line.")
            else:
                help = self.tr("Hit {unstagekey} to unstage the selected lines.")
        else:
            return

        help = help.format(
            stagekey=QKeySequence(GlobalShortcuts.stageHotkeys[0]).toString(QKeySequence.SequenceFormat.NativeText),
            unstagekey=QKeySequence(GlobalShortcuts.discardHotkeys[0]).toString(QKeySequence.SequenceFormat.NativeText),
            discardkey=QKeySequence(GlobalShortcuts.discardHotkeys[0]).toString(QKeySequence.SequenceFormat.NativeText))

        self.contextualHelp.emit("💡 " + help)
        self.selectionActionable.emit(True)

    # ---------------------------------------------
    # Search

    def search(self, op: SearchBar.Op):
        assert isinstance(op, SearchBar.Op)
        self.searchBar.popUp(forceSelectAll=op == SearchBar.Op.START)

        if op == SearchBar.Op.START:
            return

        message = self.searchBar.searchTerm
        if not message:
            QApplication.beep()
            return

        doc: QTextDocument = self.document()

        if op == SearchBar.Op.NEXT:
            newCursor = doc.find(message, self.textCursor())
        else:
            newCursor = doc.find(message, self.textCursor(), QTextDocument.FindFlag.FindBackward)

        if newCursor and not newCursor.isNull():  # extra isNull check needed for PyQt5 & PyQt6
            self.setTextCursor(newCursor)
            return

        def wrapAround():
            tc = self.textCursor()
            if op == SearchBar.Op.NEXT:
                tc.movePosition(QTextCursor.MoveOperation.Start)
            else:
                tc.movePosition(QTextCursor.MoveOperation.End)
            self.setTextCursor(tc)
            self.search(op)

        prompt = [
            self.tr("End of diff reached.") if op == SearchBar.Op.NEXT
            else self.tr("Top of diff reached."),
            self.tr("No more occurrences of {0} found.").format(bquo(message))
        ]
        askConfirmation(self, self.tr("Find in Diff"), paragraphs(prompt), okButtonText=self.tr("Wrap Around"),
                        messageBoxIcon="information", callback=wrapAround)

