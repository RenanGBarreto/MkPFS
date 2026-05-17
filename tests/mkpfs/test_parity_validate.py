"""Verify validate_d32_ranges matches legacy/ffpfs.py behaviour.

Legacy/ffpfs.py validates inode values against:
- inode.number, .flags, .blocks: [0, UINT32_MAX]
- inode.mode, .nlink: [0, 0xFFFF]
- final_ndblock, db/ib pointers: [0, INT32_MAX] or [-1, INT32_MAX]
"""

import pytest

import mkpfs.consts as c
from mkpfs.pfs import BuildError, Inode, validate_d32_ranges


def _make_inode(
    number: int = 0,
    mode: int = 0,
    nlink: int = 1,
    flags: int = 0,
    blocks: int = 1,
) -> Inode:
    """Helper to create a minimal Inode for testing."""
    return Inode(
        number=number,
        mode=mode,
        nlink=nlink,
        flags=flags,
        size=0,
        size_compressed=0,
        blocks=blocks,
    )


def test_inode_number_at_uint32_max_passes() -> None:
    """Legacy: 0 <= ino.number <= UINT32_MAX."""
    ino: Inode = _make_inode(number=c.UINT32_MAX)
    validate_d32_ranges([ino], final_ndblock=0)  # must not raise


def test_inode_number_above_uint32_max_raises() -> None:
    """Inode number exceeding UINT32_MAX must raise."""
    ino: Inode = _make_inode(number=c.UINT32_MAX + 1)
    with pytest.raises(BuildError):
        validate_d32_ranges([ino], final_ndblock=0)


def test_inode_mode_at_uint16_max_passes() -> None:
    """Mode must fit in uint16."""
    ino: Inode = _make_inode(mode=0xFFFF)
    validate_d32_ranges([ino], final_ndblock=0)  # must not raise


def test_inode_mode_above_uint16_max_raises() -> None:
    """Mode exceeding uint16 must raise."""
    ino: Inode = _make_inode(mode=0x10000)
    with pytest.raises(BuildError):
        validate_d32_ranges([ino], final_ndblock=0)


def test_inode_nlink_at_uint16_max_passes() -> None:
    """Nlink must fit in uint16."""
    ino: Inode = _make_inode(nlink=0xFFFF)
    validate_d32_ranges([ino], final_ndblock=0)  # must not raise


def test_inode_nlink_above_uint16_max_raises() -> None:
    """Nlink exceeding uint16 must raise."""
    ino: Inode = _make_inode(nlink=0x10000)
    with pytest.raises(BuildError):
        validate_d32_ranges([ino], final_ndblock=0)


def test_inode_flags_at_uint32_max_passes() -> None:
    """Legacy: 0 <= ino.flags <= UINT32_MAX."""
    ino: Inode = _make_inode(flags=c.UINT32_MAX)
    validate_d32_ranges([ino], final_ndblock=0)  # must not raise


def test_inode_flags_above_uint32_max_raises() -> None:
    """Flags exceeding UINT32_MAX must raise."""
    ino: Inode = _make_inode(flags=c.UINT32_MAX + 1)
    with pytest.raises(BuildError):
        validate_d32_ranges([ino], final_ndblock=0)


def test_inode_blocks_at_uint32_max_passes() -> None:
    """Legacy: 0 <= ino.blocks <= UINT32_MAX."""
    ino: Inode = _make_inode(blocks=c.UINT32_MAX)
    validate_d32_ranges([ino], final_ndblock=0)  # must not raise


def test_inode_blocks_above_uint32_max_raises() -> None:
    """Blocks exceeding UINT32_MAX must raise."""
    ino: Inode = _make_inode(blocks=c.UINT32_MAX + 1)
    with pytest.raises(BuildError):
        validate_d32_ranges([ino], final_ndblock=0)


def test_final_ndblock_at_int32_max_passes() -> None:
    """Final ndblock must fit in int32."""
    ino: Inode = _make_inode()
    validate_d32_ranges([ino], final_ndblock=c.INT32_MAX)  # must not raise


def test_final_ndblock_above_int32_max_raises() -> None:
    """Final ndblock exceeding INT32_MAX must raise."""
    ino: Inode = _make_inode()
    with pytest.raises(BuildError):
        validate_d32_ranges([ino], final_ndblock=c.INT32_MAX + 1)


def test_direct_block_pointer_at_int32_max_passes() -> None:
    """Direct block pointer must fit in signed int32."""
    ino: Inode = _make_inode()
    ino.db[0] = c.INT32_MAX
    validate_d32_ranges([ino], final_ndblock=0)  # must not raise


def test_direct_block_pointer_at_minus_one_passes() -> None:
    """Direct block pointer -1 is the sentinel and must pass."""
    ino: Inode = _make_inode()
    ino.db[0] = -1
    validate_d32_ranges([ino], final_ndblock=0)  # must not raise


def test_direct_block_pointer_above_int32_max_raises() -> None:
    """Direct block pointer exceeding INT32_MAX must raise."""
    ino: Inode = _make_inode()
    ino.db[0] = c.INT32_MAX + 1
    with pytest.raises(BuildError):
        validate_d32_ranges([ino], final_ndblock=0)


def test_direct_block_pointer_below_minus_one_raises() -> None:
    """Direct block pointer < -1 is invalid."""
    ino: Inode = _make_inode()
    ino.db[0] = -2
    with pytest.raises(BuildError):
        validate_d32_ranges([ino], final_ndblock=0)


def test_indirect_block_pointer_at_int32_max_passes() -> None:
    """Indirect block pointer must fit in signed int32."""
    ino: Inode = _make_inode()
    ino.ib[0] = c.INT32_MAX
    validate_d32_ranges([ino], final_ndblock=0)  # must not raise


def test_indirect_block_pointer_at_minus_one_passes() -> None:
    """Indirect block pointer -1 is the sentinel and must pass."""
    ino: Inode = _make_inode()
    ino.ib[0] = -1
    validate_d32_ranges([ino], final_ndblock=0)  # must not raise


def test_indirect_block_pointer_above_int32_max_raises() -> None:
    """Indirect block pointer exceeding INT32_MAX must raise."""
    ino: Inode = _make_inode()
    ino.ib[0] = c.INT32_MAX + 1
    with pytest.raises(BuildError):
        validate_d32_ranges([ino], final_ndblock=0)


def test_indirect_block_pointer_below_minus_one_raises() -> None:
    """Indirect block pointer < -1 is invalid."""
    ino: Inode = _make_inode()
    ino.ib[0] = -2
    with pytest.raises(BuildError):
        validate_d32_ranges([ino], final_ndblock=0)


def test_multiple_inodes_all_valid() -> None:
    """Multiple valid inodes must all pass."""
    inodes: list[Inode] = [
        _make_inode(number=1),
        _make_inode(number=2),
        _make_inode(number=3),
    ]
    validate_d32_ranges(inodes, final_ndblock=100)  # must not raise


def test_multiple_inodes_one_invalid_raises() -> None:
    """If any inode is invalid, validation must raise."""
    inodes: list[Inode] = [
        _make_inode(number=1),
        _make_inode(number=c.UINT32_MAX + 1),
        _make_inode(number=3),
    ]
    with pytest.raises(BuildError):
        validate_d32_ranges(inodes, final_ndblock=100)
