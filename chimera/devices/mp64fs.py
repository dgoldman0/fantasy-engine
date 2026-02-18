"""MP64FS — Simple flat filesystem for Chimera-1 storage.

Layout (1 MiB = 2048 × 512-byte sectors):
    Sector 0      : Superblock
    Sector 1      : Allocation bitmap (2048 bits = 256 bytes)
    Sectors 2–5   : Directory (64 entries × 32 bytes = 2048 bytes)
    Sectors 6+    : Data area

Superblock format (sector 0):
    +0   magic[4]       b"MP64"
    +4   version[2]     u16 LE (1)
    +6   total_sec[2]   u16 LE (2048)
    +8   bmap_start[2]  u16 LE (1)
    +10  bmap_secs[2]   u16 LE (1)
    +12  dir_start[2]   u16 LE (2)
    +14  dir_secs[2]    u16 LE (4)
    +16  data_start[2]  u16 LE (6)

Directory entry (32 bytes):
    +0   name[16]       null-terminated ASCII (max 15 chars)
    +16  start_sec[2]   u16 LE
    +18  sec_count[2]   u16 LE
    +20  used_bytes[4]  u32 LE
    +24  type[1]        0=free 1=raw 2=text 3=forth 4=doc 5=data 6=tutorial 7=bundle
    +25  flags[1]       bit0=readonly bit1=system
    +26  reserved[6]

Note: v1 is a flat single-directory filesystem with contiguous allocation.
Multi-folder support is planned for v2.
"""
from __future__ import annotations

import struct
from typing import Optional

SECTOR_SIZE = 512
TOTAL_SECTORS = 2048          # 1 MiB
BMAP_START = 1
BMAP_SECTORS = 1
DIR_START = 2
DIR_SECTORS = 4
DATA_START = 6
MAX_FILES = 64
MAX_NAME = 15
MAGIC = b"MP64"
VERSION = 1
DIR_ENTRY_SIZE = 32

# File types
FTYPE_FREE     = 0
FTYPE_RAW      = 1
FTYPE_TEXT     = 2
FTYPE_FORTH    = 3
FTYPE_DOC      = 4
FTYPE_DATA     = 5
FTYPE_TUTORIAL = 6
FTYPE_BUNDLE   = 7

# Flags
FLAG_READONLY = 0x01
FLAG_SYSTEM   = 0x02


# ═════════════════════════════════════════════════════════════════════
#  Bitmap helpers
# ═════════════════════════════════════════════════════════════════════

def _bitmap_get(bmap: bytearray, sector: int) -> bool:
    return bool(bmap[sector >> 3] & (1 << (sector & 7)))


def _bitmap_set(bmap: bytearray, sector: int):
    bmap[sector >> 3] |= (1 << (sector & 7))


def _bitmap_clear(bmap: bytearray, sector: int):
    bmap[sector >> 3] &= ~(1 << (sector & 7))


def _bitmap_find_free(bmap: bytearray, count: int,
                      total: int, start: int = DATA_START) -> int:
    """Find a contiguous run of `count` free sectors.  Returns -1 on failure."""
    run_start = start
    run_len = 0
    for s in range(start, total):
        if _bitmap_get(bmap, s):
            run_start = s + 1
            run_len = 0
        else:
            run_len += 1
            if run_len == count:
                return run_start
    return -1


# ═════════════════════════════════════════════════════════════════════
#  MP64FS
# ═════════════════════════════════════════════════════════════════════

class MP64FS:
    """In-memory MP64 filesystem operating on a raw disk image."""

    def __init__(self, image: bytearray | None = None):
        if image is None:
            self._img = bytearray(TOTAL_SECTORS * SECTOR_SIZE)
        else:
            self._img = image

    # -- raw sector helpers -----------------------------------------------
    def _read_sector(self, s: int) -> bytes:
        off = s * SECTOR_SIZE
        return bytes(self._img[off:off + SECTOR_SIZE])

    def _write_sector(self, s: int, data: bytes | bytearray):
        off = s * SECTOR_SIZE
        self._img[off:off + SECTOR_SIZE] = data[:SECTOR_SIZE]

    # -- format -----------------------------------------------------------
    def format(self):
        """Create a fresh MP64FS filesystem."""
        # Clear in-place to preserve shared references
        for i in range(len(self._img)):
            self._img[i] = 0

        # Superblock
        sb = bytearray(SECTOR_SIZE)
        sb[0:4] = MAGIC
        struct.pack_into("<H", sb, 4, VERSION)
        struct.pack_into("<H", sb, 6, TOTAL_SECTORS)
        struct.pack_into("<H", sb, 8, BMAP_START)
        struct.pack_into("<H", sb, 10, BMAP_SECTORS)
        struct.pack_into("<H", sb, 12, DIR_START)
        struct.pack_into("<H", sb, 14, DIR_SECTORS)
        struct.pack_into("<H", sb, 16, DATA_START)
        self._write_sector(0, sb)

        # Bitmap — mark metadata sectors as used
        bmap = bytearray(SECTOR_SIZE)
        for s in range(DATA_START):
            _bitmap_set(bmap, s)
        self._write_sector(BMAP_START, bmap)

        # Directory — all zero (free)
        for s in range(DIR_START, DIR_START + DIR_SECTORS):
            self._write_sector(s, bytearray(SECTOR_SIZE))

    # -- superblock -------------------------------------------------------
    def _read_superblock(self) -> dict:
        sb = self._read_sector(0)
        if sb[0:4] != MAGIC:
            raise ValueError("not an MP64FS image")
        return {
            "magic": sb[0:4],
            "version": struct.unpack_from("<H", sb, 4)[0],
            "total_sec": struct.unpack_from("<H", sb, 6)[0],
            "bmap_start": struct.unpack_from("<H", sb, 8)[0],
            "bmap_secs": struct.unpack_from("<H", sb, 10)[0],
            "dir_start": struct.unpack_from("<H", sb, 12)[0],
            "dir_secs": struct.unpack_from("<H", sb, 14)[0],
            "data_start": struct.unpack_from("<H", sb, 16)[0],
        }

    # -- bitmap -----------------------------------------------------------
    def _read_bitmap(self) -> bytearray:
        return bytearray(self._read_sector(BMAP_START))

    def _write_bitmap(self, bmap: bytearray):
        self._write_sector(BMAP_START, bmap)

    # -- directory --------------------------------------------------------
    def _read_dir_entry(self, idx: int) -> dict:
        sec = DIR_START + (idx * DIR_ENTRY_SIZE) // SECTOR_SIZE
        off_in_sec = (idx * DIR_ENTRY_SIZE) % SECTOR_SIZE
        raw = self._read_sector(sec)
        entry = raw[off_in_sec:off_in_sec + DIR_ENTRY_SIZE]
        name = entry[0:16].split(b"\x00")[0].decode("ascii", errors="replace")
        return {
            "name": name,
            "start_sec": struct.unpack_from("<H", entry, 16)[0],
            "sec_count": struct.unpack_from("<H", entry, 18)[0],
            "used_bytes": struct.unpack_from("<I", entry, 20)[0],
            "type": entry[24],
            "flags": entry[25],
            "index": idx,
        }

    def _write_dir_entry(self, idx: int, name: str, start_sec: int,
                         sec_count: int, used_bytes: int,
                         ftype: int = FTYPE_RAW, flags: int = 0):
        sec = DIR_START + (idx * DIR_ENTRY_SIZE) // SECTOR_SIZE
        off_in_sec = (idx * DIR_ENTRY_SIZE) % SECTOR_SIZE
        raw = bytearray(self._read_sector(sec))
        entry = bytearray(DIR_ENTRY_SIZE)
        entry[0:16] = name.encode("ascii")[:MAX_NAME].ljust(16, b"\x00")
        struct.pack_into("<H", entry, 16, start_sec)
        struct.pack_into("<H", entry, 18, sec_count)
        struct.pack_into("<I", entry, 20, used_bytes)
        entry[24] = ftype
        entry[25] = flags
        raw[off_in_sec:off_in_sec + DIR_ENTRY_SIZE] = entry
        self._write_sector(sec, raw)

    def _clear_dir_entry(self, idx: int):
        sec = DIR_START + (idx * DIR_ENTRY_SIZE) // SECTOR_SIZE
        off_in_sec = (idx * DIR_ENTRY_SIZE) % SECTOR_SIZE
        raw = bytearray(self._read_sector(sec))
        raw[off_in_sec:off_in_sec + DIR_ENTRY_SIZE] = b"\x00" * DIR_ENTRY_SIZE
        self._write_sector(sec, raw)

    # -- public API -------------------------------------------------------
    def list_files(self) -> list[dict]:
        """Return list of directory entries for non-free files."""
        files = []
        for i in range(MAX_FILES):
            entry = self._read_dir_entry(i)
            if entry["type"] != FTYPE_FREE and entry["name"]:
                files.append(entry)
        return files

    def find_file(self, name: str) -> Optional[dict]:
        """Find a file by name.  Returns None if not found."""
        for i in range(MAX_FILES):
            entry = self._read_dir_entry(i)
            if entry["type"] != FTYPE_FREE and entry["name"] == name:
                return entry
        return None

    def inject_file(self, name: str, data: bytes,
                    ftype: int = FTYPE_RAW, flags: int = 0) -> bool:
        """Add a file to the filesystem.  Returns True on success."""
        if len(name) > MAX_NAME:
            return False
        if self.find_file(name) is not None:
            return False  # duplicate

        # Find free directory slot
        slot = -1
        for i in range(MAX_FILES):
            entry = self._read_dir_entry(i)
            if entry["type"] == FTYPE_FREE:
                slot = i
                break
        if slot < 0:
            return False  # directory full

        # Calculate sectors needed
        secs_needed = (len(data) + SECTOR_SIZE - 1) // SECTOR_SIZE
        if secs_needed == 0:
            secs_needed = 1  # minimum 1 sector

        bmap = self._read_bitmap()
        start = _bitmap_find_free(bmap, secs_needed, TOTAL_SECTORS)
        if start < 0:
            return False  # disk full

        # Mark sectors used
        for s in range(start, start + secs_needed):
            _bitmap_set(bmap, s)
        self._write_bitmap(bmap)

        # Write data
        padded = bytearray(data) + bytearray(secs_needed * SECTOR_SIZE - len(data))
        for i in range(secs_needed):
            chunk = padded[i * SECTOR_SIZE:(i + 1) * SECTOR_SIZE]
            self._write_sector(start + i, chunk)

        # Write directory entry
        self._write_dir_entry(slot, name, start, secs_needed, len(data), ftype, flags)
        return True

    def read_file(self, name: str) -> Optional[bytes]:
        """Read a file's data.  Returns None if not found."""
        entry = self.find_file(name)
        if entry is None:
            return None
        raw = bytearray()
        for s in range(entry["start_sec"], entry["start_sec"] + entry["sec_count"]):
            raw.extend(self._read_sector(s))
        return bytes(raw[:entry["used_bytes"]])

    def delete_file(self, name: str) -> bool:
        """Delete a file.  Returns True on success."""
        entry = self.find_file(name)
        if entry is None:
            return False
        if entry["flags"] & FLAG_READONLY:
            return False

        bmap = self._read_bitmap()
        for s in range(entry["start_sec"], entry["start_sec"] + entry["sec_count"]):
            _bitmap_clear(bmap, s)
        self._write_bitmap(bmap)
        self._clear_dir_entry(entry["index"])
        return True

    def info(self) -> dict:
        """Return filesystem summary."""
        sb = self._read_superblock()
        bmap = self._read_bitmap()
        used = sum(1 for s in range(TOTAL_SECTORS) if _bitmap_get(bmap, s))
        files = self.list_files()
        return {
            "version": sb["version"],
            "total_sectors": sb["total_sec"],
            "used_sectors": used,
            "free_sectors": sb["total_sec"] - used,
            "num_files": len(files),
            "max_files": MAX_FILES,
        }

    # -- I/O helpers ------------------------------------------------------
    @classmethod
    def from_image(cls, image: bytearray) -> "MP64FS":
        """Wrap an existing image bytearray."""
        return cls(image)

    def save(self, path: str):
        """Save raw image to file."""
        with open(path, "wb") as f:
            f.write(self._img)

    @classmethod
    def load(cls, path: str) -> "MP64FS":
        """Load raw image from file."""
        with open(path, "rb") as f:
            data = f.read()
        return cls(bytearray(data))
