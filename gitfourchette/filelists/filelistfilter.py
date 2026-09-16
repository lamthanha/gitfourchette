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
        # SearchBar freezes the provider on every hideEvent. A bar the user
        # explicitly dismissed (Esc/close) must mean "no filter". But a bar
        # hidden along with its pane — the committed file list giving way to
        # the working directory, say — is still up as far as the user is
        # concerned, and dropping the filter there only means the bar's
        # showEvent reapplies it later, in the middle of an unrelated jump.
        super().freeze(frozen)
        searchBar = self.fileList.searchBar
        if frozen and (searchBar is None or searchBar.isHidden()):
            self.fileList.flModel.setFilterTerm("")
