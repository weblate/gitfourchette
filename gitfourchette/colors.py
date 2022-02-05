# Color scheme based on https://clrs.cc/

from .qt import QColor

navy    = QColor(0x001F3F)
blue    = QColor(0x0074D9)
aqua    = QColor(0x7FDBFF)
teal    = QColor(0x39CCCC)
olive   = QColor(0x3D9970)
green   = QColor(0x2ECC40)
lime    = QColor(0x00EE66)
yellow  = QColor(0xFFBB00)
orange  = QColor(0xFF851B)
red     = QColor(0xFF4136)
fuchsia = QColor(0xF012BE)
purple  = QColor(0xB10DC9)
maroon  = QColor(0x85144B)
white   = QColor(0xFFFFFF)
silver  = QColor(0xDDDDDD)
gray    = QColor(0xAAAAAA)
black   = QColor(0x111111)

rainbow = [
    navy, blue, aqua, teal, olive, green, lime, yellow, orange, red, maroon, fuchsia, purple
]

rainbowBright = [
    orange, yellow, lime, teal, blue, purple, fuchsia, red
]

grayscale = [
    black, gray, silver, white
]
