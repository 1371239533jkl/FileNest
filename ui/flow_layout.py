"""
FlowLayout - 流式布局，自动换行
标准 Qt 流式布局实现，用于标签云等场景
"""
from PyQt6.QtWidgets import QLayout
from PyQt6.QtCore import QRect, QSize, Qt, QPoint


class FlowLayout(QLayout):
    """流式布局：子部件从左到右排列，超出宽度自动换行"""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 6):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), False)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect, True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margin = self.contentsMargins().left() + self.contentsMargins().right()
        spacing = self.spacing()
        return QSize(size.width() + margin, size.height() + spacing)

    def _do_layout(self, rect: QRect, move: bool) -> int:
        """执行布局，返回总高度。move=True时实际移动子部件"""
        margin_left = self.contentsMargins().left()
        margin_top = self.contentsMargins().top()
        margin_right = self.contentsMargins().right()
        margin_bottom = self.contentsMargins().bottom()

        effective_rect = rect.adjusted(
            margin_left, margin_top, -margin_right, -margin_bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            if widget and not widget.isVisible():
                continue

            space_x = self.spacing()
            space_y = self.spacing()

            hint = item.sizeHint()
            next_x = x + hint.width() + space_x

            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y += line_height + space_y
                next_x = x + hint.width() + space_x
                line_height = 0

            if move:
                item.setGeometry(QRect(QPoint(x, y), hint))

            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margin_bottom
