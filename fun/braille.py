"""Sub-cell drawing with braille characters: each terminal cell is a 2x4 dot grid.

    b = braille.Braille(canvas.w, canvas.h)   # pixel size is (w*2, h*4)
    b.line(x0, y0, x1, y1, color=34)
    b.blit(canvas)

A cell takes the colour of the last dot drawn into it (one colour per cell).
"""
from fun import term

# Dot bit for (dx, dy) inside a cell; Unicode braille starts at U+2800.
_BITS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))
_CHARS = [chr(0x2800 + i) for i in range(256)]


class Braille:
    def __init__(self, cols, rows):
        self.cols, self.rows = cols, rows
        self.w, self.h = cols * 2, rows * 4
        self.clear()

    def clear(self):
        self.bits = [[0] * self.cols for _ in range(self.rows)]
        self.colors = [[None] * self.cols for _ in range(self.rows)]

    def dot(self, x, y, color=None):
        x, y = int(x), int(y)
        if 0 <= x < self.w and 0 <= y < self.h:
            cx, cy = x >> 1, y >> 2
            self.bits[cy][cx] |= _BITS[y & 3][x & 1]
            if color is not None:
                self.colors[cy][cx] = color

    def line(self, x0, y0, x1, y1, color=None):
        # Same points as calling dot() per step; inlined because this is the hot path.
        steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        ddx, ddy = x1 - x0, y1 - y0
        w, h, bits, colors = self.w, self.h, self.bits, self.colors
        for i in range(steps + 1):
            t = i / steps
            x, y = int(x0 + ddx * t), int(y0 + ddy * t)
            if 0 <= x < w and 0 <= y < h:
                cy, cx = y >> 2, x >> 1
                bits[cy][cx] |= _BITS[y & 3][x & 1]
                if color is not None:
                    colors[cy][cx] = color

    def disc(self, cx, cy, r, color=None):
        r2 = r * r
        for y in range(int(cy - r), int(cy + r) + 1):
            for x in range(int(cx - r), int(cx + r) + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r2:
                    self.dot(x, y, color)

    def blit(self, canvas, ox=0, oy=0, bg=None):
        """Draw non-empty cells onto a term.Canvas at cell offset (ox, oy)."""
        cells, cw, ch = canvas.cells, canvas.w, canvas.h
        for cy, row in enumerate(self.bits):
            y = oy + cy
            if not 0 <= y < ch or not any(row):
                continue
            colors, crow = self.colors[cy], cells[y]
            for cx in [i for i, b in enumerate(row) if b]:
                x = ox + cx
                if 0 <= x < cw:
                    crow[x] = (_CHARS[row[cx]], colors[cx], crow[x][2] if bg is None else bg)
