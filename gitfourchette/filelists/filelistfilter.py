# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

"""
Fork: search provider that turns the file lists' Ctrl+F bar into a FILTER
(Fork.dev-style): typing narrows the list to matching paths instead of merely
jumping to matches. Consistent with the sidebar, whose Ctrl+F also filters.
"""

from __future__ import annotations

import typing

from gitfourchette.search.itemviewsearchprovider import ItemViewSearchProvider

if typing.TYPE_CHECKING:
    from gitfourchette.filelists.filelist import FileList


class FileListFilter(ItemViewSearchProvider):
    @property
    def fileList(self) -> FileList:
        from gitfourchette.filelists.filelist import FileList
        assert isinstance(self._buddy, FileList)
        return self._buddy

    def _termChanged(self):
        self.fileList.flModel.setFilterTerm(self.term())

    def freeze(self, frozen: bool):
        # SearchBar freezes the provider when the bar hides (Esc) and thaws it
        # on show. A hidden bar must always mean "no filter"; on re-show, the
        # bar's showEvent reevaluates the term and the filter reapplies.
        super().freeze(frozen)
        if frozen:
            self.fileList.flModel.setFilterTerm("")
