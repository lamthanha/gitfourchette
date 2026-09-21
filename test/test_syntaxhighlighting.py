# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import sys

import pytest

from .util import *

from gitfourchette.syntax import LexJobCache, LexJob
from gitfourchette.nav import NavLocator, NavFlags

SAMPLE_CODE = """\
'''
hello multiline comment
such advanced lexing
'''

from ark import Bird

class Duck(Bird):
    def __init__(self, *args, **kwargs):
        print("quack")
"""


def digestFormatRange(formatRange: QTextLayout.FormatRange):
    start = formatRange.start
    length = formatRange.length
    isStyled = formatRange.format.foreground().color() != QColor(Qt.GlobalColor.black)
    return (start, length, isStyled)


def testDeferredSyntaxHighlighting(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    # Write sample code, with enough tokens to require a round-trip in LexJob
    writeFile(f"{wd}/hello.py", SAMPLE_CODE * 500)

    rw = mainWindow.openRepo(wd)

    commentLine = rw.diffView.document().findBlockByLineNumber(2)
    importLine = rw.diffView.document().findBlockByLineNumber(6)
    assert commentLine.text() == "hello multiline comment"
    assert importLine.text() == "from ark import Bird"

    assert not rw.diffView.highlighter.newLexJob.lexingComplete

    # Check low-quality lexing of comment line
    QTest.qWait(0)
    formatRange = commentLine.layout().formats()[0]
    assert digestFormatRange(formatRange) == (0, len("hello"), False)

    # Low-quality lexing of import line should suffice
    formatRange = importLine.layout().formats()[0]
    assert digestFormatRange(formatRange) == (0, len("from"), True)

    # Let LexJob finish its high-quality highlighting
    while not rw.diffView.highlighter.newLexJob.lexingComplete:
        QTest.qWait(0)
    QTest.qWait(0)  # Let highlighter respond

    # Now the inside of the multiline comment should be properly formatted
    formatRange = commentLine.layout().formats()[0]
    assert digestFormatRange(formatRange) == (0, len("hello multiline comment"), True)


def testLexJobCaching(tempDir, mainWindow):
    GFApplication.applyPrefs(largeFileThresholdKB=0)

    wd = unpackRepo(tempDir)
    writeFile(f"{wd}/aaaa.empty", "")  # first file is empty to avoid starting a LexJob off the bat
    writeFile(f"{wd}/big.py", SAMPLE_CODE * 3000)  # enough tokens to require LexJob round-trip
    writeFile(f"{wd}/small.py", SAMPLE_CODE * 4)

    rw = mainWindow.openRepo(wd)

    def getNewLexJob() -> LexJob:
        return rw.diffView.highlighter.newLexJob

    rw.jump(NavLocator.inUnstaged("big.py"), check=True)
    assert rw.diffView.isVisible()

    # Remember which job handles big.py
    job = getNewLexJob()

    assert not getNewLexJob().lexingComplete
    waitUntilTrue(lambda: getNewLexJob().scheduler.isActive(), interval=0)
    assert not getNewLexJob().lexingComplete

    # Switch away from DiffView, put LexJob on ice
    rw.jump(NavLocator.inUnstaged("aaaa.empty"), check=True)
    assert not rw.diffView.isVisible()
    assert not getNewLexJob().scheduler.isActive()

    # Switch back to DiffView, restore LexJob
    rw.jump(NavLocator.inUnstaged("big.py"), check=True)
    assert rw.diffView.isVisible()
    assert job is getNewLexJob()
    assert getNewLexJob().scheduler.isActive()

    # Change document in DiffView
    rw.jump(NavLocator.inUnstaged("small.py"), check=True)
    assert job is not getNewLexJob()

    # Restore document
    rw.jump(NavLocator.inUnstaged("big.py"), check=True)
    assert rw.diffView.isVisible()
    assert job is getNewLexJob()


@pytest.mark.skipif(WINDOWS, reason="TODO: flaky on Windows")
def testEvictLexJobFromCache(tempDir, mainWindow):
    GFApplication.applyPrefs(largeFileThresholdKB=1_000_000)
    assert not LexJobCache.cache
    assert LexJobCache.totalFileSize == 0

    wd = unpackRepo(tempDir)

    bigChunk = SAMPLE_CODE * 100
    bigChunk += "\n# Differentiator: XXXX"

    # Make one too many copies of the file to fit in LexJob cache
    numCopies = 1 + LexJobCache.MaxBudget // len(bigChunk)
    for i in range(numCopies):
        blobContents = bigChunk.removesuffix("XXXX") + f"{i:04}"
        writeFile(f"{wd}/copy{i:04}.py", blobContents)

    # Create a giant file that doesn't fit in cache
    writeFile(f"{wd}/giantfile.py", SAMPLE_CODE * (1 + LexJobCache.MaxBudget // len(SAMPLE_CODE)))

    rw = mainWindow.openRepo(wd)

    def getNewLexJob() -> LexJob:
        return rw.diffView.highlighter.newLexJob

    # Remember which LexJob handles copy0000.py
    assert rw.navLocator.isSimilarEnoughTo(NavLocator.inUnstaged("copy0000.py"))
    job = getNewLexJob()

    # Check that jumping back and forth to copy0000.py reuses the cached LexJob
    rw.jump(NavLocator.inUnstaged("copy0001.py"), True)
    assert job is not getNewLexJob()
    # Giant file that exceeds cache size shouldn't evict our old job
    rw.jump(NavLocator.inUnstaged("giantfile.py"), True)
    assert rw.diffView.isVisible()  # make we're not showing the "diff too large" message
    assert job is not getNewLexJob()
    rw.jump(NavLocator.inUnstaged("copy0000.py"), True)
    assert job is getNewLexJob()

    # Start lexing every file.
    # Touching the last file should cause copy0000.py's LexJob to be evicted.
    for i in range(numCopies):
        rw.jump(NavLocator.inUnstaged(f"copy{i:04}.py"), check=True)

    # Jump back to copy0000.py
    # Should start a new LexJob because it's been evicted
    rw.jump(NavLocator.inUnstaged("copy0000.py"), check=True)
    assert job is not getNewLexJob()


# Simple coverage test
def testSyntaxHighlightingNullOid(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    shell(f"""
        echo {shlex.quote(SAMPLE_CODE)} > hello.py
        git add hello.py
        rm hello.py
    """, wd)

    mainWindow.openRepo(wd)


# Simple coverage test
def testSyntaxHighlightingEmptyOid(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    shell(f"""
        touch hello.py
        git add hello.py
        echo {shlex.quote(SAMPLE_CODE)} > hello.py
    """, wd)

    mainWindow.openRepo(wd)


def testSyntaxHighlightingFillInFallbackTokenTypes(tempDir, mainWindow):
    # YAML has bespoke token types that aren't part of the standard Pygments token set,
    # e.g. Token.Literal.Scalar.Plain, Token.Punctuation.Indicator.
    wd = unpackRepo(tempDir)
    writeFile(f"{wd}/hello.yml", "- name: Hello\n")

    from gitfourchette.settings import prefs
    scheme = prefs.syntaxHighlightingScheme()
    numKnownTokens1 = len(scheme.highContrastScheme)

    mainWindow.openRepo(wd)
    numKnownTokens2 = len(scheme.highContrastScheme)
    assert numKnownTokens2 > numKnownTokens1


def testWhitespaceHighlighting(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    GFApplication.applyPrefs(showWhitespace=True)

    for space in [" ", "\t", "\xA0"]:
        writeFile(f"{wd}/hello.txt", f"hello{space}space\n")
        rw.refreshRepo()
        QTest.qWait(0)  # wait for syntax highlighting to finish

        doc: QTextDocument = rw.diffView.document()
        block = doc.findBlockByNumber(1)
        formatRanges = block.layout().formats()

        # In plain text files, the highlighter only applies formatting to
        # whitespace. Non-space text is not formatted. Make sure we apply
        # formatting to all kinds of whitespace rendered by ShowTabsAndSpaces.
        assert formatRanges
        for span in formatRanges:
            token = block.text()[span.start: span.start + span.length]
            assert token == space


def testLexJobToleratesLinesBeyondLexedFile():
    """
    The patch on screen and the bytes handed to the lexer are two separate
    reads of the same workdir file. If the file is rewritten between those two
    reads, the diff document can reference lines that were never lexed. The
    lex job must degrade to no highlighting there instead of raising KeyError
    out of QSyntaxHighlighter.highlightBlock().
    """
    from gitfourchette.syntax import LexerCache

    lexer = LexerCache.getLexerFromPath("hello.py", False)
    job = LexJob(lexer, b"x = 1\n", "dummykey")
    while not job.lexingComplete:
        job.lexChunk()

    assert job.tokens(1, "x = 1")  # a line we did lex
    assert job.tokens(148, "y = 2") == []  # far beyond the lexed file


def testDiffViewSurvivesFileGrowingDuringLoad(tempDir, mainWindow):
    """
    Reproduces the crash: an untracked file is rewritten longer while its diff
    is being loaded, so the diff document outruns the lex job's token map.
    """
    wd = unpackRepo(tempDir)
    writeFile(f"{wd}/hello.py", SAMPLE_CODE * 20)
    rw = mainWindow.openRepo(wd)
    rw.jump(NavLocator.inUnstaged("hello.py"), check=True)
    QTest.qWait(0)

    highlighter = rw.diffView.highlighter
    assert highlighter.newLexJob is not None

    # Stand in for the shorter copy of the file that the lexer got to read
    staleJob = LexJob(highlighter.newLexJob.lexer, b"x = 1\n", "stalekey")
    while not staleJob.lexingComplete:
        staleJob.lexChunk()
    highlighter.newLexJob = staleJob

    errors = []
    oldHook = sys.excepthook
    sys.excepthook = lambda *args: errors.append(args)
    try:
        highlighter.rehighlight()
        QTest.qWait(0)
    finally:
        sys.excepthook = oldHook

    assert not errors, f"highlighter raised: {errors}"


def testLexJobCacheRejectsContentThatDoesNotMatchItsKey(tempDir, mainWindow):
    """
    LoadPatch keys the lex job on the blob hash that `git diff` wrote into the
    patch, but reads the bytes to lex from the workdir afterwards. If the file
    changed in between, that tokenization must not enter the cache under a hash
    it doesn't match -- it would be served again later, when the file really
    does have those contents.
    """
    from gitfourchette.gitdriver import GitDeltaFile

    wd = unpackRepo(tempDir)
    writeFile(f"{wd}/hello.py", SAMPLE_CODE * 20)
    rw = mainWindow.openRepo(wd)
    loc = NavLocator.inUnstaged("hello.py")

    # Stand in for the file being rewritten between `git diff` and read()
    realRead = GitDeltaFile.read

    def shortRead(self, repo, maxSize=-1):
        if self.path == "hello.py":
            return b"x = 1\n"
        return realRead(self, repo, maxSize)

    # Drop the valid job that opening the repo already lexed, so that the first
    # tokenization of this blob hash is the mismatched one
    LexJobCache.clear()

    GitDeltaFile.read = shortRead
    try:
        rw.jump(loc.withExtraFlags(NavFlags.ForceRecreateDocument), check=True)
        QTest.qWait(0)
        blobHash = rw.diffView.currentDelta.new.id
        assert blobHash
        assert blobHash not in LexJobCache.cache, "cached a tokenization that doesn't match its key"
    finally:
        GitDeltaFile.read = realRead

    # With the real contents back, the diff must get a token map that covers it
    rw.jump(loc.withExtraFlags(NavFlags.ForceRecreateDocument), check=True)
    QTest.qWait(0)
    job = rw.diffView.highlighter.newLexJob
    assert job is not None
    while not job.lexingComplete:
        QTest.qWait(0)
    maxDocLine = max(ld.newLineNo for ld in rw.diffView.currentDiffDocument.lineData)
    assert maxDocLine <= max(job.hqTokenMap)
