"""
纯 Python zstd 帧编解码（raw/RLE 块）

发布目标要求 `.snap.zst`（DOC-RELEASE-003 DES-RELEASE-006）但运行时不引入
zstandard 依赖：本模块产出符合 RFC 8878 的 zstd 帧——只使用 raw（存储）块，
任何标准 zstd 解码器（含 `zstd -d`）均可还原。解码侧支持 raw 与 RLE 块，
遇到压缩块时明确报错（本实现永不产生）。
"""

from __future__ import annotations

MAGIC = 0xFD2FB528
_MAX_BLOCK = 128 * 1024  # zstd Block_Maximum_Size 上限


def compress(data: bytes) -> bytes:
    """产出 single-segment、raw 块的合法 zstd 帧"""
    out = bytearray()
    out += MAGIC.to_bytes(4, "little")
    size = len(data)
    # Frame_Header_Descriptor：Single_Segment=1；FCS 字段按长度选 1/2/4/8 字节
    if size < 256:
        out.append(0x20)
        out.append(size)
    elif size < 65536 + 256:
        out.append(0x60)
        out += (size - 256).to_bytes(2, "little")
    elif size < 2**32:
        out.append(0xA0)
        out += size.to_bytes(4, "little")
    else:
        out.append(0xE0)
        out += size.to_bytes(8, "little")
    if size == 0:
        out += (1).to_bytes(3, "little")  # last=1, raw, size=0
        return bytes(out)
    offset = 0
    while offset < size:
        chunk = data[offset:offset + _MAX_BLOCK]
        offset += len(chunk)
        last = 1 if offset >= size else 0
        header = last | (0 << 1) | (len(chunk) << 3)  # raw 块
        out += header.to_bytes(3, "little")
        out += chunk
    return bytes(out)


def decompress(frame: bytes) -> bytes:
    """解码本模块产出的帧（raw/RLE 块）；压缩块明确拒绝"""
    if len(frame) < 5 or int.from_bytes(frame[:4], "little") != MAGIC:
        raise ValueError("不是合法 zstd 帧")
    descriptor = frame[4]
    fcs_flag = descriptor >> 6
    single_segment = bool(descriptor & 0x20)
    dict_id_flag = descriptor & 0x03
    if descriptor & 0x04:
        raise ValueError("不支持带校验和的帧")
    pos = 5
    if not single_segment:
        pos += 1  # Window_Descriptor
    pos += (0, 1, 2, 4)[dict_id_flag]
    fcs_sizes = (1 if single_segment else 0, 2, 4, 8)
    pos += fcs_sizes[fcs_flag]
    out = bytearray()
    while True:
        if pos + 3 > len(frame):
            raise ValueError("帧在块头处截断")
        header = int.from_bytes(frame[pos:pos + 3], "little")
        pos += 3
        last = header & 1
        block_type = (header >> 1) & 0x03
        block_size = header >> 3
        if block_type == 0:  # raw
            out += frame[pos:pos + block_size]
            pos += block_size
        elif block_type == 1:  # RLE
            out += frame[pos:pos + 1] * block_size
            pos += 1
        else:
            raise ValueError("不支持压缩块（本实现只产出 raw 块）")
        if last:
            break
    return bytes(out)


def is_zstd_frame(data: bytes) -> bool:
    return len(data) >= 4 and int.from_bytes(data[:4], "little") == MAGIC
