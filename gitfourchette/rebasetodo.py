# -----------------------------------------------------------------------------
# Copyright (C) 2026 GitFourchette contributors.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

"""Pure-Python model for an interactive-rebase todo list.

No Qt and no pygit2 in here: rows carry plain strings so the model can be
unit-tested without an app or a repository. Rows are always handled in git's
execution order (oldest first) at this layer; the dialog is responsible for
flipping its newest-first display order before calling in.
"""

from dataclasses import dataclass

from gitfourchette.localization import *

TODO_ACTIONS = ("pick", "reword", "squash", "fixup", "drop")

_FOLD_ACTIONS = ("squash", "fixup")


@dataclass
class RebaseTodoRow:
    oid: str
    """Full hex hash of the commit."""

    summary: str
    """First line of the original commit message."""

    author: str = ""

    fullMessage: str = ""
    """Complete original commit message (pre-fill for reword/squash editing)."""

    action: str = "pick"

    message: str = ""
    """User-provided replacement message (reword) or combined message for the
    squash chain this row belongs to. Empty = keep git's default."""


def validateTodo(rowsOldestFirst: list[RebaseTodoRow]) -> str:
    """Return an error message, or an empty string if the todo is executable."""
    anyKept = False
    for row in rowsOldestFirst:
        if row.action == "drop":
            continue
        if row.action in _FOLD_ACTIONS and not anyKept:
            return _("The first commit to be replayed can’t be squashed or fixed up — "
                     "there’s no earlier commit to fold it into.")
        if row.action == "reword" and not row.message.strip():
            return _("Enter a new message for the reworded commit.")
        anyKept = True
    if not anyKept:
        return _("Every commit is dropped — there’s nothing left to do.")
    return ""


def formatTodoFile(rowsOldestFirst: list[RebaseTodoRow]) -> str:
    """Serialize the rows to git's todo-file format (oldest first).
    Dropped commits get explicit 'drop' lines so git never warns about
    silently-missing commits regardless of rebase.missingCommitsCheck."""
    lines = [f"{row.action} {row.oid} {row.summary}".rstrip() for row in rowsOldestFirst]
    return "\n".join(lines) + "\n"


def planEditorMessages(rowsOldestFirst: list[RebaseTodoRow]) -> list[str]:
    """Predict the sequence of editor invocations `git rebase -i` will make
    for this todo, and the message to substitute at each one ('' = accept
    git's default). git opens the editor once per reword (when that commit is
    applied) and once per squash chain (after the chain's last fold);
    fixup-only chains open no editor."""
    invocations = []
    chainHasSquash = False
    chainMessage = ""
    for row in rowsOldestFirst:
        if row.action == "drop":
            continue
        if row.action in _FOLD_ACTIONS:
            if row.action == "squash":
                chainHasSquash = True
                if row.message:
                    chainMessage = row.message
            continue
        # pick or reword: closes any open fold chain
        if chainHasSquash:
            invocations.append(chainMessage)
        chainHasSquash = False
        chainMessage = ""
        if row.action == "reword":
            invocations.append(row.message)
    if chainHasSquash:
        invocations.append(chainMessage)
    return invocations


def combinedSquashMessage(rowsOldestFirst: list[RebaseTodoRow], index: int) -> str:
    """Concatenated messages of the squash chain containing rowsOldestFirst[index]:
    the anchor commit's message plus every squash member's (fixup messages are
    discarded by git). Used to pre-fill the message editor for a squash row."""
    kept = [row for row in rowsOldestFirst if row.action != "drop"]
    target = rowsOldestFirst[index]
    if target not in kept:
        return ""
    anchor = kept.index(target)
    while anchor > 0 and kept[anchor].action in _FOLD_ACTIONS:
        anchor -= 1
    parts = [kept[anchor].fullMessage]
    walk = anchor + 1
    while walk < len(kept) and kept[walk].action in _FOLD_ACTIONS:
        if kept[walk].action == "squash":
            parts.append(kept[walk].fullMessage)
        walk += 1
    return "\n\n".join(part.strip() for part in parts if part.strip()) + "\n"
