# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

"""Pure unit tests for the interactive-rebase todo model (no Qt, no repo)."""

from gitfourchette.rebasetodo import (
    RebaseTodoRow,
    TODO_ACTIONS,
    combinedSquashMessage,
    formatTodoFile,
    planEditorMessages,
    validateTodo,
)


def row(oid, summary, action="pick", message="", fullMessage=""):
    return RebaseTodoRow(oid=oid * 40, summary=summary, action=action,
                         message=message, fullMessage=fullMessage or summary + "\n")


def testActionsTuple():
    assert TODO_ACTIONS == ("pick", "reword", "squash", "fixup", "drop")


def testValidateHappyPath():
    rows = [row("a", "one"), row("b", "two", "squash", message="combined"),
            row("c", "three", "fixup"), row("d", "four", "drop")]
    assert validateTodo(rows) == ""


def testValidateFirstKeptCannotBeSquashOrFixup():
    for bad in ("squash", "fixup"):
        assert validateTodo([row("a", "one", bad), row("b", "two")]) != ""
        # Leading drops don't count as a fold target either
        assert validateTodo([row("a", "one", "drop"), row("b", "two", bad),
                             row("c", "three")]) != ""


def testValidateAllDropped():
    rows = [row("a", "one", "drop"), row("b", "two", "drop")]
    # Legitimate: git executes the drop lines and resets the branch to the base
    assert validateTodo(rows) == ""
    # No base to fall back on (rebase --root): git would leave an empty commit
    assert validateTodo(rows, hasBase=False) != ""
    assert validateTodo([row("a", "one", "drop"), row("b", "two")], hasBase=False) == ""


def testValidateRewordNeedsMessage():
    assert validateTodo([row("a", "one", "reword", message="  ")]) != ""
    assert validateTodo([row("a", "one", "reword", message="new msg")]) == ""


def testFormatTodoFile():
    rows = [row("a", "one"), row("b", "two", "drop"), row("c", "three", "reword", message="x")]
    assert formatTodoFile(rows) == (
        f"pick {'a' * 40} one\n"
        f"drop {'b' * 40} two\n"
        f"reword {'c' * 40} three\n")


def testPlanNoEditorForPicksAndFixups():
    rows = [row("a", "one"), row("b", "two", "fixup"), row("c", "three")]
    assert planEditorMessages(rows) == []


def testPlanRewordThenSquashChain():
    # Execution order: pick a; reword b (editor #1); squash c (editor #2)
    rows = [row("a", "one"),
            row("b", "two", "reword", message="two, reworded"),
            row("c", "three", "squash", message="two+three combined")]
    assert planEditorMessages(rows) == ["two, reworded", "two+three combined"]


def testPlanSquashChainLastEditedMessageWins():
    rows = [row("a", "one"),
            row("b", "two", "squash"),
            row("c", "three", "squash", message="final message")]
    assert planEditorMessages(rows) == ["final message"]


def testPlanUneditedSquashLeavesGitDefault():
    rows = [row("a", "one"), row("b", "two", "squash")]
    assert planEditorMessages(rows) == [""]


def testPlanTwoSeparateChains():
    rows = [row("a", "one"), row("b", "two", "squash", message="first chain"),
            row("c", "three"), row("d", "four", "squash", message="second chain")]
    assert planEditorMessages(rows) == ["first chain", "second chain"]


def testCombinedSquashMessage():
    rows = [row("a", "one", fullMessage="one\n\nbody one\n"),
            row("b", "two", "squash", fullMessage="two\n"),
            row("c", "three", "fixup", fullMessage="three\n"),
            row("d", "four", "squash", fullMessage="four\n")]
    combined = combinedSquashMessage(rows, 1)
    assert "one\n\nbody one" in combined
    assert "two" in combined
    assert "four" in combined
    assert "three" not in combined  # fixup messages are discarded by git
