# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from __future__ import annotations  # TODO: Remove once we can drop support for Python <= 3.13

import enum
import typing

from gitfourchette.qt import *
from gitfourchette.sidebar.sidebarmodel import SidebarNode, SidebarModel, SidebarItem, SidebarLayout, SYMBOL_AHEAD, SYMBOL_BEHIND
from gitfourchette.toolbox import stockIcon, FittedText
from gitfourchette.toolbox.recolorsvgiconengine import RecolorSvgIconEngine

if typing.TYPE_CHECKING:
    from gitfourchette.sidebar.sidebar import Sidebar

PE_EXPANDED = QStyle.PrimitiveElement.PE_IndicatorArrowDown
PE_COLLAPSED = QStyle.PrimitiveElement.PE_IndicatorArrowRight

# These metrics are a good compromise for Breeze, macOS, and Fusion.
EXPAND_TRIANGLE_WIDTH = 6
PADDING = 4
EYE_WIDTH = 16
STAR_WIDTH = 16


class SidebarClickZone(enum.IntEnum):
    Invalid = 0
    Select = 1
    Expand = 2
    Hide = 3
    Star = 4


class SidebarDelegate(QStyledItemDelegate):
    """
    Draws custom tree expand/collapse indicator arrows,
    and hide/show icons.
    """

    sidebar: Sidebar

    def __init__(self, parent: QTreeView):
        super().__init__(parent)
        self.sidebar = parent

    @staticmethod
    def unindentRect(item: SidebarItem, rect: QRect, indentation: int):
        if item not in SidebarLayout.UnindentItems:
            return
        unindentLevels = SidebarLayout.UnindentItems[item]
        unindentPixels = unindentLevels * indentation
        return rect.adjust(unindentPixels, 0, 0, 0)

    @staticmethod
    def getClickZone(node: SidebarNode, rect: QRect, x: int):
        if node.kind == SidebarItem.Spacer:
            return SidebarClickZone.Invalid
        elif node.mayHaveChildren() and node.children and x < rect.left():
            return SidebarClickZone.Expand
        elif node.canBeHidden() and x > rect.right() - EYE_WIDTH - PADDING:
            return SidebarClickZone.Hide
        elif node.canBeStarred() and x > rect.right() - EYE_WIDTH - STAR_WIDTH - PADDING:
            return SidebarClickZone.Star
        else:
            return SidebarClickZone.Select

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        node = self.sidebar.filterIndexToNode(index)
        assert node.parent is not None, "can't paint root node"

        sidebarModel = self.sidebar.sidebarModel
        view = self.sidebar
        assert view is option.widget

        style: QStyle = view.style()
        isActive = bool(option.state & QStyle.StateFlag.State_Active)
        isSelected = bool(option.state & QStyle.StateFlag.State_Selected)
        mouseOver = bool(option.state & QStyle.StateFlag.State_Enabled) and bool(option.state & QStyle.StateFlag.State_MouseOver)
        colorGroup = QPalette.ColorGroup.Active if isActive else QPalette.ColorGroup.Inactive

        isExplicitlyShown = False
        isExplicitlyHidden = False
        isImplicitlyHidden = False
        isHideAllButThisMode = sidebarModel.isHideAllButThisMode()
        makeRoomForEye = False
        if node.canBeHidden():
            isExplicitlyShown = sidebarModel.isExplicitlyShown(node)
            isExplicitlyHidden = sidebarModel.isExplicitlyHidden(node)
            isImplicitlyHidden = isExplicitlyHidden or sidebarModel.isImplicitlyHidden(node)
            makeRoomForEye = mouseOver or isExplicitlyShown or isExplicitlyHidden or isImplicitlyHidden

        isStarred = False
        makeRoomForStar = False
        if node.canBeStarred():
            isStarred = node.data in sidebarModel.repoModel.prefs.starredRefs
            makeRoomForStar = isStarred or mouseOver

        painter.save()

        if node.kind == SidebarItem.Spacer:
            mouseOver = False
            option.state &= ~QStyle.StateFlag.State_MouseOver

            r = QRect(option.rect)
            r.setLeft(0)
            middle = r.top() + int(r.height() / 2)

            tc1 = option.palette.color(colorGroup, QPalette.ColorRole.WindowText)
            tc2 = QColor(tc1)
            tc1.setAlpha(0)
            tc2.setAlpha(33)
            lineGradient = QLinearGradient(r.left() + PADDING, middle, r.right() - PADDING, middle)
            lineGradient.setColorAt(0, tc1)
            lineGradient.setColorAt(.2, tc2)
            lineGradient.setColorAt(1-.2, tc2)
            lineGradient.setColorAt(1, tc1)

            painter.save()
            painter.setPen(QPen(lineGradient, 1))
            painter.drawLine(r.left() + PADDING, middle, r.right() - PADDING, middle)
            painter.restore()

        # Unindent rect
        SidebarDelegate.unindentRect(node.kind, option.rect, view.indentation())

        # Draw expand/collapse triangle.
        if node.mayHaveChildren() and node.children and not node.wantForceExpand():
            opt2 = QStyleOptionViewItem(option)
            opt2.rect.adjust(-(EXPAND_TRIANGLE_WIDTH + PADDING), 0, 0, 0)  # args must be integers for pyqt5!
            opt2.rect.setWidth(EXPAND_TRIANGLE_WIDTH)

            # See QTreeView::drawBranches() in qtreeview.cpp for other interesting states
            opt2.state &= ~QStyle.StateFlag.State_MouseOver
            arrowPrimitive = PE_EXPANDED if view.isExpanded(index) else PE_COLLAPSED
            style.drawPrimitive(arrowPrimitive, opt2, painter, view)

        # Draw control background
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)

        # Adjust contents
        option.rect.adjust(PADDING, 0, -PADDING, 0)

        # Set highlighted text color if this item is selected
        iconMode = QIcon.Mode.Normal
        if isSelected:
            penColor = option.palette.color(colorGroup, QPalette.ColorRole.HighlightedText)
            iconMode = QIcon.Mode.Selected if isActive else QIcon.Mode.SelectedInactive
        elif not node.parent.parent and node.kind != SidebarItem.UncommittedChanges:
            penColor = option.palette.color(colorGroup, QPalette.ColorRole.WindowText)
            penColor.setAlphaF(.66)
        else:
            penColor = option.palette.color(colorGroup, QPalette.ColorRole.WindowText)
        painter.setPen(penColor)

        # Draw decoration icon
        iconWidth = option.decorationSize.width()
        iconKey = index.data(SidebarModel.Role.IconKey)
        if iconKey:
            r = QRect(option.rect)
            r.setWidth(iconWidth)
            icon = stockIcon(iconKey)
            icon.paint(painter, r, option.decorationAlignment, mode=iconMode)
            option.rect.adjust(r.width() + PADDING*150//100, 0, 0, 0)

        # Prepare text
        textRect = QRect(option.rect)
        if makeRoomForEye:
            textRect.adjust(0, 0, -EYE_WIDTH, 0)
        if makeRoomForStar:
            textRect.adjust(0, 0, -STAR_WIDTH, 0)

        # Anchor the star/eye button bands to the row's right edge NOW, before
        # the indicator blocks below clip textRect leftward. The bands must
        # stay pinned to the right regardless of any indicator; only the text
        # (and the indicator itself) yield space to each other.
        bandAnchor = textRect.right()

        font: QFont = index.data(Qt.ItemDataRole.FontRole) or option.font
        baseFontSize = font.pointSizeF()

        # Draw ahead/behind/missing upstream indicators
        missingUpstream = index.data(SidebarModel.Role.MissingUpstream)
        aheadBehind = index.data(SidebarModel.Role.AheadBehind)
        if makeRoomForEye:
            # No upstream indicators
            pass

        elif missingUpstream:
            r = QRect(option.rect)
            r.setLeft(textRect.right() - EYE_WIDTH)
            # Cap the width so the centered icon stays left of the star band
            # (r otherwise spans to the contents edge, i.e. under the band).
            r.setWidth(EYE_WIDTH)
            unpluggedIcon = stockIcon("git-upstream-missing")
            unpluggedIcon.paint(painter, r, mode=iconMode)
            # Clip rect
            textRect.setRight(r.left())

        elif aheadBehind:
            a, b = aheadBehind

            # Set a smaller font
            font.setPointSizeF(baseFontSize * (.67 if a and b else .75))
            painter.setFont(font)
            metrics = painter.fontMetrics()

            textA = f" {a} {SYMBOL_AHEAD}" if a else ""
            textB = f" {b} {SYMBOL_BEHIND}" if b else ""
            advanceA = metrics.horizontalAdvance(textA) if a else 0
            advanceB = metrics.horizontalAdvance(textB) if b else 0

            AF = Qt.AlignmentFlag
            if not isSelected:
                painter.setPen(RecolorSvgIconEngine.IconColors.mainColor)
            painter.drawText(textRect, AF.AlignRight | (AF.AlignTop if b else AF.AlignVCenter) , textA)
            painter.drawText(textRect, AF.AlignRight | (AF.AlignBottom if a else AF.AlignVCenter), textB)

            # Restore font size
            font.setPointSizeF(baseFontSize)
            painter.setPen(penColor)

            # Clip rect
            textRect.setRight(textRect.right() - max(advanceA, advanceB))

        # Draw text
        painter.setFont(font)
        fullText = index.data(Qt.ItemDataRole.DisplayRole)
        # Header kinds are numbered first in SidebarItem (Spacer..SubmodulesHeader).
        # StarredHeader (fork) is a header too, but it was appended at the end
        # of the enum instead, so as not to shift the ordinals of upstream's
        # existing members (keeps merges from upstream conflict-free, and
        # keeps ordinal comparisons like this one -- <= SubmodulesHeader --
        # stable across merges). That's why it falls outside the
        # <= SubmodulesHeader range and needs to be called out explicitly here.
        isCannedString = node.kind <= SidebarItem.SubmodulesHeader or node.kind == SidebarItem.StarredHeader
        if not isCannedString:
            FittedText.draw(painter, textRect, option.displayAlignment, fullText, option.textElideMode)
        else:
            text = painter.fontMetrics().elidedText(fullText, Qt.TextElideMode.ElideMiddle, textRect.width())
            painter.drawText(textRect, option.displayAlignment, text)

        # Draw star/eye buttons: flush bands filling right-to-left from the
        # row's right edge (bandAnchor, captured before indicator clipping),
        # star left of eye; each collapses when unused. This flush layout is
        # what aligns the painted icons with the raw-frame click zones.
        bandLeft = bandAnchor
        if makeRoomForStar:
            r = QRect(option.rect)
            r.setLeft(bandLeft)
            r.setWidth(STAR_WIDTH)
            starIcon = stockIcon("star-filled" if isStarred else "star-outline")
            starIcon.paint(painter, r, mode=iconMode)
            bandLeft += STAR_WIDTH
        if makeRoomForEye:
            r = QRect(option.rect)
            r.setLeft(bandLeft)
            r.setWidth(EYE_WIDTH)
            if isExplicitlyShown or mouseOver and isHideAllButThisMode:
                eyeIconName = "view-exclusive"
            elif isExplicitlyHidden or (isImplicitlyHidden and isHideAllButThisMode):
                eyeIconName = "view-hidden"
            elif isImplicitlyHidden:
                eyeIconName = "view-hidden-indirect"
            else:
                eyeIconName = "view-visible"
            unpluggedIcon = stockIcon(eyeIconName)
            unpluggedIcon.paint(painter, r, mode=iconMode)

        painter.restore()
