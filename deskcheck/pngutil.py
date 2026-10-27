"""Minimal stdlib PNG decoder/encoder (zlib + struct only, no Pillow).

Supports 8-bit colour types 0 (grey), 2 (RGB), 3 (palette), 4 (grey+alpha)
and 6 (RGBA), non-interlaced. This is all deskcheck needs: screenshots are
captured by the OS driver as PNG, and pixel-diff only needs RGB(A) pixels.
"""
import struct
import zlib


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png(data: bytes):
    """Return (width, height, pixels) where pixels is a list of rows of
    (r, g, b, a) tuples."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    pos, idat, plte, trns = 8, b"", None, None
    width = height = bit_depth = colour = None
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            width, height, bit_depth, colour, comp, filt, inter = struct.unpack(">IIBBBBB", chunk)
            if bit_depth != 8:
                raise ValueError(f"unsupported PNG bit depth {bit_depth} (only 8-bit)")
            if inter != 0:
                raise ValueError("interlaced PNG not supported")
        elif ctype == b"PLTE":
            plte = [tuple(chunk[i:i + 3]) for i in range(0, len(chunk), 3)]
        elif ctype == b"tRNS":
            trns = chunk
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if width is None:
        raise ValueError("PNG missing IHDR")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour]
    raw = zlib.decompress(idat)
    stride = width * channels
    rows, prev = [], bytearray(stride)
    offset = 0
    for _ in range(height):
        f = raw[offset]
        offset += 1
        line = bytearray(raw[offset:offset + stride])
        offset += stride
        if f == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((a + prev[i]) // 2)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                line[i] = (line[i] + _paeth(a, b, c)) & 0xFF
        elif f != 0:
            raise ValueError(f"unsupported PNG filter {f}")
        prev = line
        out = []
        for x in range(width):
            v = line[x * channels:(x + 1) * channels]
            if colour == 0:
                out.append((v[0], v[0], v[0], 255))
            elif colour == 2:
                out.append((v[0], v[1], v[2], 255))
            elif colour == 3:
                rgb = plte[v[0]]
                alpha = trns[v[0]] if trns else 255
                out.append((rgb[0], rgb[1], rgb[2], alpha))
            elif colour == 4:
                out.append((v[0], v[0], v[0], v[1]))
            else:
                out.append(tuple(v))
        rows.append(out)
    return width, height, rows


def encode_png(width, height, rows):
    """Encode rows of (r, g, b) or (r, g, b, a) tuples as an RGB PNG."""
    def chunk(ctype, payload):
        c = struct.pack(">I", len(payload)) + ctype + payload
        return c + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF)
    raw = b""
    for row in rows:
        raw += b"\x00" + b"".join(bytes((r, g, b)) for (r, g, b, *_a) in row)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def solid_png(width, height, rgb):
    return encode_png(width, height, [[rgb] * width for _ in range(height)])
