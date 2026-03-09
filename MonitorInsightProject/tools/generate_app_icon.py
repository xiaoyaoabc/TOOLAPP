from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF

CANVAS_SIZE = 512


def draw_icon(size: int = CANVAS_SIZE) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    background_rect = QRectF(size * 0.06, size * 0.06, size * 0.88, size * 0.88)
    background_gradient = QLinearGradient(background_rect.topLeft(), background_rect.bottomRight())
    background_gradient.setColorAt(0.0, QColor('#17324d'))
    background_gradient.setColorAt(0.55, QColor('#1d4762'))
    background_gradient.setColorAt(1.0, QColor('#49b8a7'))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(background_gradient)
    painter.drawRoundedRect(background_rect, size * 0.11, size * 0.11)

    glow_path = QPainterPath()
    glow_path.addEllipse(QRectF(size * 0.50, size * 0.14, size * 0.24, size * 0.24))
    painter.fillPath(glow_path, QColor(255, 255, 255, 34))

    monitor_rect = QRectF(size * 0.15, size * 0.14, size * 0.56, size * 0.42)
    painter.setPen(QPen(QColor('#f8fbff'), size * 0.032, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(QColor('#f8fbff'))
    painter.drawRoundedRect(monitor_rect, size * 0.04, size * 0.04)

    screen_rect = QRectF(size * 0.18, size * 0.17, size * 0.50, size * 0.36)
    screen_gradient = QLinearGradient(screen_rect.topLeft(), screen_rect.bottomRight())
    screen_gradient.setColorAt(0.0, QColor('#dff6ff'))
    screen_gradient.setColorAt(0.58, QColor('#85d8cc'))
    screen_gradient.setColorAt(1.0, QColor('#4e98b7'))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(screen_gradient)
    painter.drawRoundedRect(screen_rect, size * 0.03, size * 0.03)

    painter.setBrush(QColor(255, 255, 255, 42))
    painter.drawRoundedRect(QRectF(size * 0.21, size * 0.20, size * 0.20, size * 0.05), size * 0.02, size * 0.02)

    signal_line = QPolygonF(
        [
            QPointF(size * 0.25, size * 0.39),
            QPointF(size * 0.34, size * 0.31),
            QPointF(size * 0.42, size * 0.36),
            QPointF(size * 0.50, size * 0.27),
            QPointF(size * 0.58, size * 0.33),
        ]
    )
    painter.setPen(QPen(QColor('#17324d'), size * 0.02, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPolyline(signal_line)

    arrow = QPolygonF(
        [
            QPointF(size * 0.565, size * 0.305),
            QPointF(size * 0.615, size * 0.325),
            QPointF(size * 0.575, size * 0.355),
        ]
    )
    painter.setBrush(QColor('#17324d'))
    painter.drawPolygon(arrow)

    painter.setPen(QPen(QColor('#f8fbff'), size * 0.026, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(size * 0.43, size * 0.57), QPointF(size * 0.43, size * 0.67))
    painter.drawLine(QPointF(size * 0.33, size * 0.70), QPointF(size * 0.53, size * 0.70))

    accent_ring_pen = QPen(QColor(255, 255, 255, 96), size * 0.018)
    painter.setPen(accent_ring_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(QRectF(size * 0.57, size * 0.54, size * 0.18, size * 0.18), 25 * 16, 250 * 16)

    painter.end()
    return image



def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    assets_dir = project_root / 'assets'
    assets_dir.mkdir(parents=True, exist_ok=True)

    icon = draw_icon()
    png_path = assets_dir / 'monitor_insight_icon.png'
    ico_path = assets_dir / 'monitor_insight.ico'

    if not icon.save(str(png_path)):
        raise SystemExit('Failed to save PNG icon.')
    if not icon.save(str(ico_path)):
        raise SystemExit('Failed to save ICO icon.')

    print(f'Saved {png_path}')
    print(f'Saved {ico_path}')


if __name__ == '__main__':
    main()
