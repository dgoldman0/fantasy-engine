"""Stage 7: NIC, Storage, SysInfo, and MP64FS tests."""
from __future__ import annotations

import struct
import tempfile
import os
import pytest

from chimera.devices.nic import NIC, LoopbackBackend, NICBackend
from chimera.devices.storage import Storage, SECTOR_SIZE
from chimera.devices.sysinfo import SysInfo
from chimera.devices.mp64fs import MP64FS, FTYPE_RAW, FTYPE_TEXT, FLAG_READONLY
from chimera.devices.bus import DeviceBus


# ═════════════════════════════════════════════════════════════════════
#  NIC — Basic register access
# ═════════════════════════════════════════════════════════════════════

class TestNICRegisters:
    def test_present_and_link_up(self):
        nic = NIC(backend=LoopbackBackend())
        st = nic.read8(0x01)
        assert st & 0x80  # present
        assert st & 0x04  # link_up (loopback always up)

    def test_mac_readback(self):
        mac = b"\xAA\xBB\xCC\xDD\xEE\xFF"
        nic = NIC(backend=LoopbackBackend(), mac=mac)
        read_mac = bytes(nic.read8(0x0E + i) for i in range(6))
        assert read_mac == mac

    def test_dma_addr_readback(self):
        nic = NIC(backend=LoopbackBackend())
        addr = 0x1234_5678_9ABC_DEF0
        for i in range(8):
            nic.write8(0x02 + i, (addr >> (i * 8)) & 0xFF)
        assert nic.dma_addr == addr

    def test_frame_len_readback(self):
        nic = NIC(backend=LoopbackBackend())
        nic.write8(0x0A, 0x00)
        nic.write8(0x0B, 0x06)  # 0x0600 = 1536
        assert nic.frame_len == 0x0600

    def test_irq_ctrl_readback(self):
        nic = NIC(backend=LoopbackBackend())
        nic.write8(0x0C, 0x03)  # enable both RX and TX IRQs
        assert nic.read8(0x0C) == 0x03

    def test_irq_w1c(self):
        """IRQ status is Write-1-to-Clear."""
        nic = NIC(backend=LoopbackBackend())
        nic.irq_status = 0x03
        nic.write8(0x0D, 0x01)  # clear bit 0
        assert nic.irq_status == 0x02


# ═════════════════════════════════════════════════════════════════════
#  NIC — TX/RX with data port
# ═════════════════════════════════════════════════════════════════════

class TestNICDataPort:
    def test_send_via_data_port(self):
        nic = NIC(backend=LoopbackBackend())
        frame = b"\x01\x02\x03\x04\x05"
        for i, b in enumerate(frame):
            nic.write8(0x20 + i, b)
        nic.write8(0x0A, len(frame))  # frame_len
        nic.write8(0x00, 0x01)  # CMD_SEND
        assert len(nic.tx_queue) == 1
        assert nic.tx_queue[0] == frame
        assert nic.tx_count == 1

    def test_recv_fills_data_port(self):
        nic = NIC(backend=LoopbackBackend())
        frame = b"\xAA\xBB\xCC"
        nic.rx_queue.append(frame)
        nic.write8(0x00, 0x02)  # CMD_RECV
        assert nic.frame_len == 3
        for i in range(3):
            assert nic.read8(0x20 + i) == frame[i]

    def test_rx_avail_bit(self):
        nic = NIC(backend=LoopbackBackend())
        assert not (nic.read8(0x01) & 0x02)
        nic.rx_queue.append(b"\xFF")
        assert nic.read8(0x01) & 0x02

    def test_reset_clears_state(self):
        nic = NIC(backend=LoopbackBackend())
        nic.tx_count = 5
        nic.rx_queue.append(b"\xFF")
        nic.write8(0x00, 0x04)  # CMD_RESET
        assert nic.tx_count == 0
        assert len(nic.rx_queue) == 0


# ═════════════════════════════════════════════════════════════════════
#  NIC — DMA TX/RX
# ═════════════════════════════════════════════════════════════════════

class TestNICDMA:
    def test_dma_send(self):
        """TX reads frame from DMA memory."""
        mem = bytearray(1024)
        frame = b"Hello, DMA!"
        mem[0x100:0x100 + len(frame)] = frame

        nic = NIC(backend=LoopbackBackend())
        nic._mem_read = lambda a: mem[a]
        nic._mem_write = lambda a, v: mem.__setitem__(a, v)

        # Set DMA addr
        for i in range(8):
            nic.write8(0x02 + i, (0x100 >> (i * 8)) & 0xFF)
        nic.write8(0x0A, len(frame))  # frame_len
        nic.write8(0x00, 0x01)  # CMD_SEND

        assert len(nic.tx_queue) == 1
        assert nic.tx_queue[0] == frame

    def test_dma_recv(self):
        """RX writes frame to DMA memory."""
        mem = bytearray(1024)
        frame = b"DMA receive!"

        nic = NIC(backend=LoopbackBackend())
        nic._mem_read = lambda a: mem[a]
        nic._mem_write = lambda a, v: mem.__setitem__(a, v)

        # Queue a frame
        nic.rx_queue.append(frame)

        # Set DMA addr
        for i in range(8):
            nic.write8(0x02 + i, (0x200 >> (i * 8)) & 0xFF)
        nic.write8(0x00, 0x02)  # CMD_RECV

        assert bytes(mem[0x200:0x200 + len(frame)]) == frame


# ═════════════════════════════════════════════════════════════════════
#  NIC — Echo loopback
# ═════════════════════════════════════════════════════════════════════

class TestNICEchoLoopback:
    def test_echo_mode(self):
        """LoopbackBackend(echo=True) sends TX frames back as RX."""
        nic = NIC(backend=LoopbackBackend(echo=True))
        frame = b"\xDE\xAD\xBE\xEF"
        for i, b in enumerate(frame):
            nic.write8(0x20 + i, b)
        nic.write8(0x0A, len(frame))
        nic.write8(0x00, 0x01)  # SEND

        # Frame should appear in rx_queue via echo
        assert len(nic.rx_queue) == 1
        assert nic.rx_queue[0] == frame


# ═════════════════════════════════════════════════════════════════════
#  Storage — Basic register access
# ═════════════════════════════════════════════════════════════════════

class TestStorageRegisters:
    def test_present_bit(self):
        st = Storage()
        assert st.read8(0x01) & 0x80

    def test_sector_readback(self):
        st = Storage()
        st.write8(0x02, 0x10)
        st.write8(0x03, 0x20)
        st.write8(0x04, 0x00)
        st.write8(0x05, 0x00)
        assert st.sector_num == 0x2010

    def test_dma_addr_readback(self):
        st = Storage()
        for i in range(8):
            st.write8(0x06 + i, i + 1)
        val = 0
        for i in range(8):
            val |= st.read8(0x06 + i) << (i * 8)
        assert val == st.dma_addr

    def test_sec_count(self):
        st = Storage()
        st.write8(0x0E, 4)
        assert st.sec_count == 4


# ═════════════════════════════════════════════════════════════════════
#  Storage — Direct sector I/O
# ═════════════════════════════════════════════════════════════════════

class TestStorageSectors:
    def test_read_write_sectors(self):
        st = Storage()
        data = bytes(range(256)) * 2  # 512 bytes
        st.write_sectors(10, 1, data)
        got = st.read_sectors(10, 1)
        assert got == data

    def test_multi_sector_write(self):
        st = Storage()
        data = b"\xAA" * 1024  # 2 sectors
        st.write_sectors(100, 2, data)
        got = st.read_sectors(100, 2)
        assert got == data


# ═════════════════════════════════════════════════════════════════════
#  Storage — DMA
# ═════════════════════════════════════════════════════════════════════

class TestStorageDMA:
    def test_dma_read(self):
        """CMD=READ copies sectors to DMA memory."""
        mem = bytearray(2048)
        st = Storage()
        st._mem_read = lambda a: mem[a]
        st._mem_write = lambda a, v: mem.__setitem__(a, v)

        # Write known data to sector 0
        st.write_sectors(0, 1, b"\x42" * SECTOR_SIZE)

        # Set DMA address and read
        for i in range(8):
            st.write8(0x06 + i, (0x100 >> (i * 8)) & 0xFF)
        st.write8(0x02, 0)  # sector 0
        st.write8(0x0E, 1)  # 1 sector
        st.write8(0x00, 0x01)  # CMD_READ

        assert mem[0x100] == 0x42
        assert all(b == 0x42 for b in mem[0x100:0x100 + SECTOR_SIZE])

    def test_dma_write(self):
        """CMD=WRITE copies from DMA memory to sectors."""
        mem = bytearray(2048)
        mem[0x200:0x200 + SECTOR_SIZE] = b"\xBB" * SECTOR_SIZE

        st = Storage()
        st._mem_read = lambda a: mem[a]
        st._mem_write = lambda a, v: mem.__setitem__(a, v)

        for i in range(8):
            st.write8(0x06 + i, (0x200 >> (i * 8)) & 0xFF)
        st.write8(0x02, 5)  # sector 5
        st.write8(0x0E, 1)
        st.write8(0x00, 0x02)  # CMD_WRITE

        assert st.read_sectors(5, 1) == b"\xBB" * SECTOR_SIZE

    def test_out_of_range_error(self):
        """Read past end sets error bit."""
        st = Storage(total_sectors=10)
        st.write8(0x02, 9)  # sector 9
        st.write8(0x0E, 2)  # 2 sectors → overflow
        st.write8(0x00, 0x01)  # CMD_READ
        assert st.read8(0x01) & 0x02  # error bit


# ═════════════════════════════════════════════════════════════════════
#  Storage — Host file backing
# ═════════════════════════════════════════════════════════════════════

class TestStorageFileIO:
    def test_save_and_load(self, tmp_path):
        st = Storage(total_sectors=16)
        st.write_sectors(0, 1, b"\xAA" * SECTOR_SIZE)
        path = str(tmp_path / "test.img")
        st._image_path = path
        assert st.save_image()

        st2 = Storage(image_path=path, total_sectors=16)
        assert st2.read_sectors(0, 1) == b"\xAA" * SECTOR_SIZE

    def test_flush_cmd(self, tmp_path):
        path = str(tmp_path / "flush.img")
        st = Storage(total_sectors=16)
        st._image_path = path
        st.write_sectors(1, 1, b"\xFF" * SECTOR_SIZE)
        st.write8(0x00, 0xFF)  # CMD_FLUSH
        assert os.path.exists(path)


# ═════════════════════════════════════════════════════════════════════
#  SysInfo
# ═════════════════════════════════════════════════════════════════════

class TestSysInfo:
    def test_board_id(self):
        si = SysInfo()
        val = 0
        for i in range(8):
            val |= si.read8(i) << (i * 8)
        assert val == 0x0000_0001_314D_4843  # "CHM1" + v1 LE

    def test_ram_size(self):
        si = SysInfo(ram_size=0x200000)
        val = 0
        for i in range(8):
            val |= si.read8(0x08 + i) << (i * 8)
        assert val == 0x200000

    def test_num_cores(self):
        si = SysInfo(num_cores=8)
        val = 0
        for i in range(8):
            val |= si.read8(0x10 + i) << (i * 8)
        assert val == 8

    def test_cluster_en_rw(self):
        si = SysInfo()
        # Write lower byte = 0x0F (enable clusters 0-3)
        si.write8(0x18, 0x0F)
        assert si.read8(0x18) == 0x0F
        # Upper bytes unchanged
        assert si.read8(0x19) == 0xFF

    def test_lm1_tiles(self):
        si = SysInfo(lm1_tiles=16)
        val = 0
        for i in range(8):
            val |= si.read8(0x20 + i) << (i * 8)
        assert val == 16

    def test_readonly_regs(self):
        """Writes to non-CLUSTER_EN regs are ignored."""
        si = SysInfo()
        si.write8(0x00, 0xFF)
        assert si.read8(0x00) == 0x43  # 'C' from "CHM1" LE, unchanged


# ═════════════════════════════════════════════════════════════════════
#  MP64FS
# ═════════════════════════════════════════════════════════════════════

class TestMP64FS:
    def _fresh(self) -> MP64FS:
        fs = MP64FS()
        fs.format()
        return fs

    def test_format_superblock(self):
        fs = self._fresh()
        info = fs.info()
        assert info["version"] == 1
        assert info["total_sectors"] == 2048
        assert info["num_files"] == 0

    def test_inject_and_read(self):
        fs = self._fresh()
        data = b"Hello, MP64FS!"
        assert fs.inject_file("hello.txt", data, FTYPE_TEXT)
        got = fs.read_file("hello.txt")
        assert got == data

    def test_list_files(self):
        fs = self._fresh()
        fs.inject_file("a.bin", b"\x00" * 100)
        fs.inject_file("b.txt", b"text", FTYPE_TEXT)
        files = fs.list_files()
        assert len(files) == 2
        names = {f["name"] for f in files}
        assert names == {"a.bin", "b.txt"}

    def test_find_file(self):
        fs = self._fresh()
        fs.inject_file("target", b"data")
        entry = fs.find_file("target")
        assert entry is not None
        assert entry["used_bytes"] == 4

    def test_delete_file(self):
        fs = self._fresh()
        fs.inject_file("del_me", b"x" * 1000)
        assert fs.delete_file("del_me")
        assert fs.find_file("del_me") is None
        # Sectors should be freed
        info = fs.info()
        assert info["free_sectors"] == 2048 - 6  # only metadata used

    def test_delete_readonly_fails(self):
        fs = self._fresh()
        fs.inject_file("locked", b"data", flags=FLAG_READONLY)
        assert not fs.delete_file("locked")
        assert fs.find_file("locked") is not None

    def test_duplicate_name_rejected(self):
        fs = self._fresh()
        assert fs.inject_file("dup", b"1")
        assert not fs.inject_file("dup", b"2")

    def test_large_file(self):
        fs = self._fresh()
        data = os.urandom(4096)  # 8 sectors
        assert fs.inject_file("big", data)
        got = fs.read_file("big")
        assert got == data

    def test_max_files(self):
        fs = self._fresh()
        for i in range(64):
            assert fs.inject_file(f"f{i:02d}", b"\x00")
        assert not fs.inject_file("overflow", b"\x00")

    def test_disk_full(self):
        fs = self._fresh()
        # Fill most of the disk (2048 - 6 data sectors)
        big = b"\xFF" * ((2048 - 6) * SECTOR_SIZE)
        assert fs.inject_file("huge", big)
        assert not fs.inject_file("more", b"\x00")

    def test_file_types(self):
        fs = self._fresh()
        fs.inject_file("code.f", b"forth code", FTYPE_TEXT)
        entry = fs.find_file("code.f")
        assert entry["type"] == FTYPE_TEXT

    def test_info_accounting(self):
        fs = self._fresh()
        fs.inject_file("test", b"x" * 1024)  # 2 sectors
        info = fs.info()
        assert info["used_sectors"] == 6 + 2  # metadata + data
        assert info["num_files"] == 1


# ═════════════════════════════════════════════════════════════════════
#  MP64FS — File I/O
# ═════════════════════════════════════════════════════════════════════

class TestMP64FSIO:
    def test_save_load(self, tmp_path):
        fs = MP64FS()
        fs.format()
        fs.inject_file("persist", b"saved data")
        path = str(tmp_path / "test.mp64")
        fs.save(path)

        fs2 = MP64FS.load(path)
        got = fs2.read_file("persist")
        assert got == b"saved data"


# ═════════════════════════════════════════════════════════════════════
#  Storage + MP64FS integration
# ═════════════════════════════════════════════════════════════════════

class TestStorageWithFS:
    def test_fs_on_storage(self):
        """MP64FS operates on Storage's image."""
        st = Storage()
        fs = MP64FS.from_image(st._image)
        fs.format()
        fs.inject_file("hello", b"world")

        # Read back through Storage's sector API
        data = st.read_sectors(0, 1)
        assert data[:4] == b"MP64"  # superblock magic

        # FS reads work
        got = fs.read_file("hello")
        assert got == b"world"


# ═════════════════════════════════════════════════════════════════════
#  Bus integration
# ═════════════════════════════════════════════════════════════════════

class TestStage7Bus:
    def test_all_devices_on_bus(self):
        bus = DeviceBus()
        nic = NIC(backend=LoopbackBackend())
        st = Storage()
        si = SysInfo()

        bus.register(0x0200, 0x10, st)
        bus.register(0x0300, 0x50, si)
        bus.register(0x0400, 0x80, nic)

        base = bus.base
        # Storage present
        assert bus.read(base + 0x0201) & 0x80
        # SysInfo board ID first byte = 'C' (0x43) from "CHM1" LE
        assert bus.read(base + 0x0300) == 0x43
        # NIC present + link up
        st_nic = bus.read(base + 0x0401)
        assert st_nic & 0x80
        assert st_nic & 0x04
