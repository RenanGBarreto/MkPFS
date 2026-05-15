"""Create a PS-style unsigned PFS image for ShadowMountPlus workflows.

This script builds an unsigned PFS image inspired by LibOrbisPkg's
layout for inner PFS images (superroot + flat_path_table + uroot).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import multiprocessing as mp
import shutil
import struct
import time
import zlib
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from . import consts
from .logging import info
from .pbar import Progress, scan_source_tree
from .utils import _read_exact, ceil_div, human_readable_size, read_param_json


def validate_d32_ranges(inodes: list[Inode], final_ndblock: int) -> None:
    """Validate values that are serialized into 32-bit inode structures."""
    if final_ndblock > consts.INT32_MAX:
        raise BuildError(f"Image requires block index {final_ndblock}, exceeds D32 pointer limit {consts.INT32_MAX}")

    for ino in inodes:
        if not (0 <= ino.number <= consts.INT32_MAX):
            raise BuildError(f"Inode number {ino.number} out of uint32 range")
        if not (0 <= ino.mode <= 0xFFFF):
            raise BuildError(f"Inode mode {ino.mode} out of uint16 range")
        if not (0 <= ino.nlink <= 0xFFFF):
            raise BuildError(f"Inode nlink {ino.nlink} out of uint16 range")
        if not (0 <= ino.flags <= consts.INT32_MAX):
            raise BuildError(f"Inode flags {ino.flags} out of uint32 range")
        if not (0 <= ino.blocks <= consts.INT32_MAX):
            raise BuildError(f"Inode blocks {ino.blocks} out of uint32 range")

        for ptr in ino.db:
            if not (-1 <= ptr <= consts.INT32_MAX):
                raise BuildError(f"Direct block pointer {ptr} out of int32 range")
        for ptr in ino.ib:
            if not (-1 <= ptr <= consts.INT32_MAX):
                raise BuildError(f"Indirect block pointer {ptr} out of int32 range")


def pfs_gen_sign_key(ekpfs: bytes, seed: bytes) -> bytes:
    """Generate signing key (convenience wrapper)."""
    return pfs_gen_crypto_key(ekpfs, seed, 2)


def hmac_sha256(key: bytes, data: bytes) -> bytes:
    """HMAC-SHA256 convenience helper."""
    return hmac.new(key, data, hashlib.sha256).digest()


def pfs_gen_crypto_key(ekpfs: bytes, seed: bytes, index: int) -> bytes:
    return hmac.new(ekpfs, struct.pack("<I", index) + seed, hashlib.sha256).digest()


def signed_inode_capacity_bytes(block_size: int) -> int:
    sigs_per_block = block_size // consts.SIG_ENTRY_SIZE
    if sigs_per_block <= 0:
        return 0
    max_blocks = 12 + sigs_per_block + (sigs_per_block * sigs_per_block)
    return max_blocks * block_size


def compose_pfs_mode(inode_bits: int, case_insensitive: bool) -> int:
    # Bit 3 (0x8) controls case-sensitivity: when set, filesystem is case-insensitive.
    mode = 0
    if inode_bits == 64:
        mode |= consts.PFS_MODE_64BIT_INODES
    if case_insensitive:
        mode |= consts.PFS_MODE_CASE_INSENSITIVE
    return mode


def compose_pfs_mode_with_sign(inode_bits: int, case_insensitive: bool, signed: bool) -> int:
    mode = compose_pfs_mode(inode_bits, case_insensitive)
    if signed:
        mode |= consts.PFS_MODE_SIGNED
    return mode


def build_inode_block_sig_s64(inode_block_count: int, block_size: int, now: int, signed: bool = False) -> bytes:
    """Build the superblock InodeBlockSig using the signed-64 inode layout.

    Real working images encode this field as DinodeS64-sized data in the header
    even when filesystem inodes are unsigned D32.
    """
    sig = bytearray(0x310)

    struct.pack_into("<H", sig, 0x00, 0)  # mode
    struct.pack_into("<H", sig, 0x02, 1)  # nlink
    struct.pack_into("<I", sig, 0x04, 0 if signed else consts.INODE_FLAG_READONLY)  # flags
    size_bytes = inode_block_count * block_size
    struct.pack_into("<q", sig, 0x08, size_bytes)
    struct.pack_into("<q", sig, 0x10, size_bytes)

    struct.pack_into("<qqqq", sig, 0x18, now, now, now, now)
    struct.pack_into("<IIII", sig, 0x38, 0, 0, 0, 0)
    struct.pack_into("<I", sig, 0x48, 0)  # uid
    struct.pack_into("<I", sig, 0x4C, 0)  # gid
    struct.pack_into("<Q", sig, 0x50, 0)  # unk1
    struct.pack_into("<Q", sig, 0x58, 0)  # unk2
    struct.pack_into("<I", sig, 0x60, inode_block_count)  # blocks

    # Signed-64 layout: 12 direct and 5 indirect entries, each 32-byte sig + 8-byte block.
    # Reference images use zeroed signatures and only db[0] = 1 for inode-table start block.
    # Observed S64 header layout includes 4-byte padding after `blocks`.
    db_base = 0x68
    for i in range(12):
        if signed:
            block = 1 + i if i < inode_block_count else 0
        else:
            block = 1 if i == 0 else 0
        struct.pack_into("<q", sig, db_base + i * 40 + 32, block)

    ib_base = db_base + 12 * 40
    for i in range(5):
        struct.pack_into("<q", sig, ib_base + i * 40 + 32, 0)

    return bytes(sig)


@dataclass
class SignatureTarget:
    block: int
    sig_offset: int
    size: int
    level: int


class BuildError(RuntimeError):
    pass


@dataclass
class Dirent:
    inode_number: int
    type_code: int
    name: str

    @property
    def name_length(self) -> int:
        return len(self.name)

    @property
    def ent_size(self) -> int:
        size = self.name_length + 17
        rem = size % 8
        if rem:
            size += 8 - rem
        return size

    def to_bytes(self) -> bytes:
        name_bytes = self.name.encode("ascii", errors="strict")
        out = bytearray()
        out += struct.pack("<Iiii", self.inode_number, self.type_code, self.name_length, self.ent_size)
        out += name_bytes
        if len(out) < self.ent_size:
            out += b"\x00" * (self.ent_size - len(out))
        return bytes(out)


@dataclass
class Inode:
    number: int
    mode: int
    nlink: int
    flags: int
    size: int
    size_compressed: int
    blocks: int
    db: list[int] = field(default_factory=lambda: [0] * consts.MAX_DIRECT_BLOCKS)
    ib: list[int] = field(default_factory=lambda: [0] * consts.MAX_INDIRECT_BLOCKS)
    db_sig: list[bytes] = field(
        default_factory=lambda: [b"\x00" * consts.SIG_SIZE for _ in range(consts.MAX_DIRECT_BLOCKS)]
    )
    ib_sig: list[bytes] = field(
        default_factory=lambda: [b"\x00" * consts.SIG_SIZE for _ in range(consts.MAX_INDIRECT_BLOCKS)]
    )
    time_sec: int = 0

    def _base_bytes(self) -> bytearray:
        ts = self.time_sec
        time_nsec = 0
        uid = 0
        gid = 0
        unk1 = 0
        unk2 = 0
        out = bytearray()
        out += struct.pack("<HHI", self.mode, self.nlink, self.flags)
        out += struct.pack("<qq", self.size, self.size_compressed)
        out += struct.pack("<qqqq", ts, ts, ts, ts)
        out += struct.pack("<IIII", time_nsec, time_nsec, time_nsec, time_nsec)
        out += struct.pack("<IIQQI", uid, gid, unk1, unk2, self.blocks)
        return out

    def to_bytes(self) -> bytes:
        out = self._base_bytes()
        out += struct.pack("<" + "i" * consts.MAX_DIRECT_BLOCKS, *self.db)
        out += struct.pack("<" + "i" * consts.MAX_INDIRECT_BLOCKS, *self.ib)
        if len(out) != consts.INODE_D32_SIZE:
            raise BuildError(f"Unexpected inode size {len(out)}")
        return bytes(out)

    def to_bytes_signed32(self) -> bytes:
        out = self._base_bytes()
        for sig, block in zip(self.db_sig, self.db):
            if len(sig) != consts.SIG_SIZE:
                raise BuildError("Signed inode direct signature must be 32 bytes")
            out += sig
            out += struct.pack("<i", block)
        for sig, block in zip(self.ib_sig, self.ib):
            if len(sig) != consts.SIG_SIZE:
                raise BuildError("Signed inode indirect signature must be 32 bytes")
            out += sig
            out += struct.pack("<i", block)
        if len(out) != consts.INODE_S32_SIZE:
            raise BuildError(f"Unexpected signed inode size {len(out)}")
        return bytes(out)


@dataclass
class FileNode:
    rel_path: str
    abs_path: Path
    parent_rel_dir: str
    name: str
    raw_size: int
    stored_payload: bytes = b""
    stored_size: int = 0
    compressed: bool = False
    gain_pct: float = 0.0
    hypothetical_compressed_size: int = 0
    inode: Inode | None = None


@dataclass
class DirNode:
    rel_dir: str
    name: str
    parent_rel_dir: str | None
    children_dirs: list[str] = field(default_factory=list)
    children_files: list[str] = field(default_factory=list)
    dirents: list[Dirent] = field(default_factory=list)
    inode: Inode | None = None


@dataclass
class BuildStats:
    input_path: Path
    output_path: Path
    total_files: int = 0
    uncompressed_total_size: int = 0
    stored_total_size: int = 0
    all_compressed_total_size: int = 0
    compressed_files: int = 0
    uncompressed_files: int = 0
    elapsed_seconds: float = 0.0
    compression_enabled: bool = True
    block_size: int = 65536
    block_alignment_waste: int = 0

    @property
    def actual_gain_pct(self) -> float:
        if self.uncompressed_total_size == 0:
            return 0.0
        return ((self.uncompressed_total_size - self.stored_total_size) / self.uncompressed_total_size) * 100.0

    @property
    def max_possible_gain_pct(self) -> float:
        if self.uncompressed_total_size == 0:
            return 0.0
        return ((self.uncompressed_total_size - self.all_compressed_total_size) / self.uncompressed_total_size) * 100.0


def validate_input(path: Path) -> tuple[str, list[str]]:
    if not path.exists() or not path.is_dir():
        raise BuildError(f"--path must be an existing directory: {path}")
    param_json = path / "sce_sys" / "param.json"
    if not param_json.exists():
        raise BuildError(f"Missing required file: {param_json}")

    parsed = read_param_json(param_json)
    title_id = parsed.get("titleId") or parsed.get("title_id")
    if not isinstance(title_id, str) or not title_id.strip():
        raise BuildError("param.json is missing a valid titleId/title_id")

    warnings: list[str] = []
    if not (path / "eboot.bin").exists():
        warnings.append("Recommended file missing: eboot.bin")

    return title_id.strip(), warnings


def file_full_path_for_hash(file_node: FileNode) -> str:
    return "/" + file_node.rel_path.replace("\\", "/")


def dir_full_path_for_hash(dir_node: DirNode) -> str:
    if dir_node.rel_dir == "":
        return ""
    return "/" + dir_node.rel_dir.replace("\\", "/")


def fpt_hash(name: str, case_insensitive: bool = True) -> int:
    """Calculate flat_path_table hash.

    Args:
        name: Path to hash
        case_insensitive: If True, uppercase characters; if False, use as-is
    """
    h = 0
    for c in name:
        char = c.upper() if case_insensitive else c
        h = (ord(char) + (31 * h)) & 0xFFFFFFFF
    return h


def make_fpt_and_collision_blob(
    dirs_sorted: list[DirNode],
    files_sorted: list[FileNode],
    inode_by_path: dict[str, Inode],
    case_insensitive: bool = True,
) -> tuple[bytes, bytes | None, bool]:
    path_entries: list[tuple[str, int, bool]] = []
    for d in dirs_sorted:
        if d.rel_dir == "":
            continue
        path_entries.append((dir_full_path_for_hash(d), inode_by_path[f"dir:{d.rel_dir}"].number, True))
    for f in files_sorted:
        path_entries.append((file_full_path_for_hash(f), inode_by_path[f"file:{f.rel_path}"].number, False))

    by_hash: dict[int, list[tuple[str, int, bool]]] = {}
    for item in path_entries:
        h = fpt_hash(item[0], case_insensitive=case_insensitive)
        by_hash.setdefault(h, []).append(item)

    has_collision = any(len(v) > 1 for v in by_hash.values())

    hash_map: dict[int, int] = {}
    collision_blob = bytearray()
    collision_offsets: dict[int, int] = {}

    if has_collision:
        for h in sorted(by_hash.keys()):
            entries = by_hash[h]
            if len(entries) <= 1:
                continue
            offset = len(collision_blob)
            collision_offsets[h] = offset
            for full_path, ino_num, is_dir in entries:
                d = Dirent(
                    inode_number=ino_num,
                    type_code=consts.DIRENT_TYPE_DIRECTORY if is_dir else consts.DIRENT_TYPE_FILE,
                    name=full_path,
                )
                collision_blob += d.to_bytes()
            collision_blob += b"\x00" * 0x18

    for h in sorted(by_hash.keys()):
        entries = by_hash[h]
        if len(entries) == 1:
            _, ino_num, is_dir = entries[0]
            hash_map[h] = ino_num | (0x20000000 if is_dir else 0)
        else:
            hash_map[h] = 0x80000000 | collision_offsets[h]

    fpt = bytearray()
    for h in sorted(hash_map.keys()):
        fpt += struct.pack("<II", h, hash_map[h] & 0xFFFFFFFF)

    return bytes(fpt), (bytes(collision_blob) if has_collision else None), has_collision


def compute_file_storage(
    file_node: FileNode,
    compress: bool,
    threshold_gain: int,
    block_size: int = 65536,
    zlib_level: int = zlib.Z_BEST_COMPRESSION,
) -> None:
    """Decide how a file will be stored in the image.

    This function updates the provided FileNode in-place with the payload that will be
    written into the image (either raw or compressed), the stored size, whether it is
    compressed, and the observed gain percentage. It also computes a hypothetical
    compressed size used for statistics.

    Args:
        file_node: FileNode describing the file to process.
        compress: Whether compression is enabled.
        threshold_gain: Minimum percent gain required to keep compressed data.
        block_size: Files smaller than this are not compressed (alignment heuristic).
        zlib_level: Compression level passed to zlib.compress.

    Raises:
        OSError: If reading the file from disk fails.
    """
    raw: bytes = file_node.abs_path.read_bytes()
    too_small: bool = len(raw) < block_size
    # Hypothetical compressed size is useful for reporting even when not actually
    # compressing in this pass.
    file_node.hypothetical_compressed_size = len(raw) if too_small else len(zlib.compress(raw, level=zlib_level))

    if not compress or len(raw) == 0 or too_small:
        file_node.stored_payload = raw
        file_node.stored_size = len(raw)
        file_node.compressed = False
        file_node.gain_pct = 0.0
        return

    comp: bytes = zlib.compress(raw, level=zlib_level)
    gain_pct: float = ((len(raw) - len(comp)) / len(raw)) * 100.0
    if gain_pct >= threshold_gain:
        file_node.stored_payload = comp
        file_node.stored_size = len(comp)
        file_node.compressed = True
        file_node.gain_pct = gain_pct
    else:
        file_node.stored_payload = raw
        file_node.stored_size = len(raw)
        file_node.compressed = False
        file_node.gain_pct = gain_pct


def _compute_file_storage_worker(args: tuple[Path, int, bool, int, int]) -> tuple[Path, bytes, int, bool, float, int]:
    """Worker function for parallel compression.

    This function is executed in a worker process and performs the same storage
    decision logic as :func:`compute_file_storage` but returns the results instead
    of mutating a FileNode.

    Args:
        args: Tuple containing (abs_path, threshold_gain, compress, block_size, zlib_level).

    Returns:
        A tuple (file_path, stored_payload, stored_size, compressed, gain_pct, hypothetical_compressed_size).
    """
    abs_path: Path
    threshold_gain: int
    compress: bool
    block_size: int
    zlib_level: int
    (abs_path, threshold_gain, compress, block_size, zlib_level) = args

    raw: bytes = abs_path.read_bytes()
    too_small: bool = len(raw) < block_size
    hypothetical_compressed_size: int = (
        len(raw) if (not compress or too_small) else len(zlib.compress(raw, level=zlib_level))
    )

    if not compress or len(raw) == 0 or too_small:
        return abs_path, raw, len(raw), False, 0.0, hypothetical_compressed_size

    comp: bytes = zlib.compress(raw, level=zlib_level)
    gain_pct: float = ((len(raw) - len(comp)) / len(raw)) * 100.0
    if gain_pct >= threshold_gain:
        return abs_path, comp, len(comp), True, gain_pct, hypothetical_compressed_size
    return abs_path, raw, len(raw), False, gain_pct, hypothetical_compressed_size


def signed_inode_sig_offset(inode_number: int, ptr_index: int, block_size: int) -> int:
    inodes_per_block = block_size // consts.INODE_S32_SIZE
    if inodes_per_block <= 0:
        raise BuildError("block size too small for signed inode table")
    inode_table_block = inode_number // inodes_per_block
    inode_index_in_block = inode_number % inodes_per_block
    inode_offset = block_size + (inode_table_block * block_size) + (inode_index_in_block * consts.INODE_S32_SIZE)
    return inode_offset + 0x64 + (consts.SIG_ENTRY_SIZE * ptr_index)


def header_inode_block_sig_offset(ptr_index: int) -> int:
    return 0xB8 + (40 * ptr_index)


def make_sig_records_blob(blocks: list[int], block_size: int) -> bytes:
    blob = bytearray(block_size)
    offset = 0
    for block in blocks:
        struct.pack_into("<i", blob, offset + consts.SIG_SIZE, block)
        offset += consts.SIG_ENTRY_SIZE
    return bytes(blob)


def collect_signed_block_numbers(
    inode: Inode, block_size: int, indirect_block_records: dict[int, list[int]]
) -> list[int]:
    sigs_per_block = block_size // consts.SIG_ENTRY_SIZE
    blocks: list[int] = []
    direct_count = min(inode.blocks, consts.MAX_DIRECT_BLOCKS)
    blocks.extend(inode.db[:direct_count])
    remaining = inode.blocks - direct_count

    if remaining > 0:
        ib0_children = indirect_block_records.get(inode.ib[0], [])
        take = min(remaining, sigs_per_block)
        blocks.extend(ib0_children[:take])
        remaining -= take

    if remaining > 0:
        for child_indirect in indirect_block_records.get(inode.ib[1], []):
            child_children = indirect_block_records.get(child_indirect, [])
            take = min(remaining, sigs_per_block)
            blocks.extend(child_children[:take])
            remaining -= take
            if remaining <= 0:
                break

    return blocks


def write_payload_to_blocks(out: BinaryIO, payload: bytes, blocks: list[int], block_size: int) -> None:
    for index, block in enumerate(blocks):
        chunk = payload[index * block_size : (index + 1) * block_size]
        if not chunk:
            break
        out.seek(block * block_size)
        out.write(chunk)


def assign_signed_inode_layout(
    inode: Inode,
    block_count: int,
    block_size: int,
    next_block: int,
    sig_targets: list[SignatureTarget],
    indirect_block_records: dict[int, list[int]],
) -> int:
    sigs_per_block = block_size // consts.SIG_ENTRY_SIZE
    if sigs_per_block <= 0:
        raise BuildError("Block size too small for signed pointer records")

    if block_count > 12 + sigs_per_block + (sigs_per_block * sigs_per_block):
        raise BuildError(
            f"Signed inode {inode.number} requires {block_count} blocks, exceeds current signed layout capacity"
        )

    for i in range(consts.MAX_DIRECT_BLOCKS):
        inode.db[i] = 0
    for i in range(consts.MAX_INDIRECT_BLOCKS):
        inode.ib[i] = 0

    direct_count = min(block_count, consts.MAX_DIRECT_BLOCKS)
    for i in range(direct_count):
        inode.db[i] = next_block
        sig_targets.append(
            SignatureTarget(next_block, signed_inode_sig_offset(inode.number, i, block_size), block_size, 0)
        )
        next_block += 1

    remaining = block_count - direct_count
    if remaining <= 0:
        return next_block

    inode.ib[0] = next_block
    ib0_block = next_block
    next_block += 1
    sig_targets.append(
        SignatureTarget(ib0_block, signed_inode_sig_offset(inode.number, 12, block_size), block_size, 1)
    )

    ib0_children: list[int] = []
    simple_count = min(remaining, sigs_per_block)
    for _ in range(simple_count):
        child_block = next_block
        next_block += 1
        ib0_children.append(child_block)
        sig_targets.append(
            SignatureTarget(
                child_block, ib0_block * block_size + len(ib0_children[:-1]) * consts.SIG_ENTRY_SIZE, block_size, 0
            )
        )
    indirect_block_records[ib0_block] = ib0_children
    remaining -= simple_count
    if remaining <= 0:
        return next_block

    inode.ib[1] = next_block
    ib1_parent = next_block
    next_block += 1
    sig_targets.append(
        SignatureTarget(ib1_parent, signed_inode_sig_offset(inode.number, 13, block_size), block_size, 2)
    )

    ib1_children: list[int] = []
    for idx in range(sigs_per_block):
        if remaining <= 0:
            break
        child_indirect_block = next_block
        next_block += 1
        ib1_children.append(child_indirect_block)
        sig_targets.append(
            SignatureTarget(child_indirect_block, ib1_parent * block_size + idx * consts.SIG_ENTRY_SIZE, block_size, 1)
        )

        child_records: list[int] = []
        child_count = min(remaining, sigs_per_block)
        for rec_idx in range(child_count):
            data_block = next_block
            next_block += 1
            child_records.append(data_block)
            sig_targets.append(
                SignatureTarget(
                    data_block, child_indirect_block * block_size + rec_idx * consts.SIG_ENTRY_SIZE, block_size, 0
                )
            )
        indirect_block_records[child_indirect_block] = child_records
        remaining -= child_count

    indirect_block_records[ib1_parent] = ib1_children
    if remaining > 0:
        raise BuildError(f"Signed inode {inode.number} still has {remaining} blocks unallocated")

    return next_block


def build_pfs(
    source_root: Path,
    output_path: Path,
    block_size: int,
    pfs_version: int,
    inode_bits: int,
    case_insensitive: bool,
    signed: bool,
    compress: bool,
    threshold_gain: int,
    cpu_count: int,
    zlib_level: int,
    dry_run: bool,
    verbose: bool,
) -> BuildStats:
    start: float = time.time()
    progress: Progress = Progress(enabled=True)

    if signed and inode_bits != 32:
        raise BuildError("--signed currently supports only 32-bit inodes")

    dirs: dict[str, DirNode]
    files: dict[str, FileNode]
    dirs, files, _ = scan_source_tree(source_root, progress)

    dir_nodes_sorted: list[DirNode] = sorted(dirs.values(), key=lambda d: d.rel_dir.lower())
    file_nodes_sorted: list[FileNode] = sorted(files.values(), key=lambda f: f.rel_path.lower())

    if compress and len(file_nodes_sorted) > 0:
        # Calculate total bytes for compression progress
        total_bytes_to_process: int = sum(f.raw_size for f in file_nodes_sorted)
        worker_count: int = mp.cpu_count() if cpu_count == 0 else cpu_count
        progress.status(
            f"\nCompressing {len(file_nodes_sorted)} files ({human_readable_size(total_bytes_to_process)}) "
            f"using {worker_count} CPU core{'s' if worker_count != 1 else ''}..."
        )
        # Use multiprocessing for parallel compression
        worker_args: list[tuple] = [
            (f.abs_path, threshold_gain, True, block_size, zlib_level) for f in file_nodes_sorted
        ]
        total_bytes_processed: int = 0
        with mp.Pool(processes=worker_count) as pool:
            results = pool.imap_unordered(_compute_file_storage_worker, worker_args)
            for idx, result in enumerate(results, start=1):
                abs_path, payload, stored_size, is_compressed, gain_pct, hyp_comp_size = result
                # Find the corresponding file node
                file_node: FileNode = next(f for f in file_nodes_sorted if f.abs_path == abs_path)
                file_node.stored_payload = payload
                file_node.stored_size = stored_size
                file_node.compressed = is_compressed
                file_node.gain_pct = gain_pct
                file_node.hypothetical_compressed_size = hyp_comp_size
                total_bytes_processed += file_node.raw_size
                progress.step(
                    "compress", total_bytes_processed, total_bytes_to_process, bytes_processed=total_bytes_processed
                )
    else:
        # No compression: just read files without any compression logic
        if len(file_nodes_sorted) > 0:
            total_bytes_to_process = sum(f.raw_size for f in file_nodes_sorted)
            progress.status(
                f"\nReading {len(file_nodes_sorted)} files ({human_readable_size(total_bytes_to_process)})..."
            )
            total_bytes_processed = 0
            for idx, f in enumerate(file_nodes_sorted, start=1):
                raw = f.abs_path.read_bytes()
                f.stored_payload = raw
                f.stored_size = len(raw)
                f.compressed = False
                f.gain_pct = 0.0
                f.hypothetical_compressed_size = 0
                total_bytes_processed += f.raw_size
                progress.step(
                    "read", total_bytes_processed, total_bytes_to_process, bytes_processed=total_bytes_processed
                )

    now: int = int(time.time())
    inodes: list[Inode] = []

    super_root_inode = Inode(
        number=0,
        mode=consts.INODE_MODE_DIR | consts.INODE_RX_ONLY,
        nlink=1,
        flags=consts.INODE_FLAG_INTERNAL
        | (0 if signed else consts.INODE_FLAG_READONLY)
        | (consts.INODE_FLAG_SIGNED_EXTRA if signed else 0),
        size=block_size,
        size_compressed=block_size,
        blocks=1,
        time_sec=now,
    )
    fpt_inode = Inode(
        number=1,
        mode=consts.INODE_MODE_FILE | consts.INODE_RX_ONLY,
        nlink=1,
        flags=consts.INODE_FLAG_INTERNAL
        | (0 if signed else consts.INODE_FLAG_READONLY)
        | (consts.INODE_FLAG_SIGNED_EXTRA if signed else 0),
        size=0,
        size_compressed=0,
        blocks=1,
        time_sec=now,
    )

    collision_inode: Inode | None = None

    uroot_inode_num = 2
    uroot_inode = Inode(
        number=uroot_inode_num,
        mode=consts.INODE_MODE_DIR | consts.INODE_RX_ONLY,
        nlink=3,
        flags=(0 if signed else consts.INODE_FLAG_READONLY) | (consts.INODE_FLAG_SIGNED_EXTRA if signed else 0),
        size=block_size,
        size_compressed=block_size,
        blocks=1,
        time_sec=now,
    )

    inodes.extend([super_root_inode, fpt_inode, uroot_inode])
    dirs[""].inode = uroot_inode

    inode_by_path: dict[str, Inode] = {"dir:": uroot_inode}

    next_inode_number = 3

    non_root_dirs = [d for d in dir_nodes_sorted if d.rel_dir != ""]
    for d in non_root_dirs:
        ino = Inode(
            number=next_inode_number,
            mode=consts.INODE_MODE_DIR | consts.INODE_RX_ONLY,
            nlink=2,
            flags=consts.INODE_FLAG_READONLY | (consts.INODE_FLAG_SIGNED_EXTRA if signed else 0),
            size=block_size,
            size_compressed=block_size,
            blocks=1,
            time_sec=now,
        )
        d.inode = ino
        inode_by_path[f"dir:{d.rel_dir}"] = ino
        inodes.append(ino)
        next_inode_number += 1

    for f in file_nodes_sorted:
        flags = (
            consts.INODE_FLAG_READONLY
            | (consts.INODE_FLAG_COMPRESSED if f.compressed else 0)
            | (consts.INODE_FLAG_SIGNED_EXTRA if signed else 0)
        )
        blocks = max(1, ceil_div(f.stored_size, block_size)) if f.stored_size > 0 else 1
        file_size = f.raw_size if f.compressed else f.stored_size
        file_size_compressed = f.stored_size
        ino = Inode(
            number=next_inode_number,
            mode=consts.INODE_MODE_FILE | consts.INODE_RX_ONLY,
            nlink=1,
            flags=flags,
            size=file_size,
            size_compressed=file_size_compressed,
            blocks=blocks,
            time_sec=now,
        )
        f.inode = ino
        inode_by_path[f"file:{f.rel_path}"] = ino
        inodes.append(ino)
        next_inode_number += 1

    for d in dir_nodes_sorted:
        parent_ino = inode_by_path["dir:" + (d.parent_rel_dir if d.parent_rel_dir is not None else "")]
        this_ino = inode_by_path["dir:" + d.rel_dir]

        d.dirents = [
            Dirent(this_ino.number, consts.DIRENT_TYPE_DOT, "."),
            Dirent(parent_ino.number if d.rel_dir != "" else this_ino.number, consts.DIRENT_TYPE_DOTDOT, ".."),
        ]

        for child_rel_dir in d.children_dirs:
            child_dir = dirs[child_rel_dir]
            d.dirents.append(Dirent(child_dir.inode.number, consts.DIRENT_TYPE_DIRECTORY, child_dir.name))
            this_ino.nlink += 1

        for child_rel_file in d.children_files:
            child_file = files[child_rel_file]
            d.dirents.append(Dirent(child_file.inode.number, consts.DIRENT_TYPE_FILE, child_file.name))

    fpt_blob, collision_blob, has_collision = make_fpt_and_collision_blob(
        dir_nodes_sorted,
        file_nodes_sorted,
        inode_by_path,
        case_insensitive=case_insensitive,
    )

    if has_collision:
        collision_inode = Inode(
            number=2,
            mode=consts.INODE_MODE_FILE | consts.INODE_RX_ONLY,
            nlink=1,
            flags=consts.INODE_FLAG_INTERNAL
            | consts.INODE_FLAG_READONLY
            | (consts.INODE_FLAG_SIGNED_EXTRA if signed else 0),
            size=len(collision_blob or b""),
            size_compressed=len(collision_blob or b""),
            blocks=max(1, ceil_div(len(collision_blob or b""), block_size)),
            time_sec=now,
        )
        inodes = [super_root_inode, fpt_inode, collision_inode, uroot_inode] + [
            ino for ino in inodes if ino.number >= 3
        ]

        # Renumber all non-special inodes after inserting collision_resolver.
        remap: dict[int, int] = {}
        for idx, ino in enumerate(inodes):
            old = ino.number
            ino.number = idx
            remap[old] = idx

        for d in dir_nodes_sorted:
            d.inode.number = remap[d.inode.number]
            for ent in d.dirents:
                ent.inode_number = remap[ent.inode_number]
        for f in file_nodes_sorted:
            f.inode.number = remap[f.inode.number]

        inode_by_path = {}
        for d in dir_nodes_sorted:
            inode_by_path[f"dir:{d.rel_dir}"] = d.inode
        for f in file_nodes_sorted:
            inode_by_path[f"file:{f.rel_path}"] = f.inode

    super_root_dirents: list[Dirent] = [Dirent(fpt_inode.number, consts.DIRENT_TYPE_FILE, "flat_path_table")]
    if has_collision and collision_inode is not None:
        super_root_dirents.append(Dirent(collision_inode.number, consts.DIRENT_TYPE_FILE, "collision_resolver"))
    super_root_dirents.append(Dirent(uroot_inode.number, consts.DIRENT_TYPE_DIRECTORY, "uroot"))

    inode_count = len(inodes)
    inode_size = consts.INODE_S32_SIZE if signed else consts.INODE_D32_SIZE
    inodes_per_block = block_size // inode_size
    inode_block_count = ceil_div(inode_count, inodes_per_block)

    all_nodes_data: list[tuple[Inode, bytes, bool]] = []

    # Root directory first, then nested dirs, then files.
    root_blob = b"".join(d.to_bytes() for d in dirs[""].dirents)
    all_nodes_data.append((dirs[""].inode, root_blob, True))
    for d in non_root_dirs:
        blob = b"".join(ent.to_bytes() for ent in d.dirents)
        all_nodes_data.append((d.inode, blob, True))
    for f in file_nodes_sorted:
        all_nodes_data.append((f.inode, f.stored_payload, False))

    signature_targets: list[SignatureTarget] = []
    indirect_block_records: dict[int, list[int]] = {}

    if signed:
        max_signed_size = signed_inode_capacity_bytes(block_size)
        if max_signed_size <= 0:
            raise BuildError("Block size too small for signed PFS layout")
        for f in file_nodes_sorted:
            if f.stored_size > max_signed_size:
                raise BuildError(
                    f"Signed mode cannot represent file '{f.rel_path}' with block size {block_size}; "
                    f"max supported stored payload is {max_signed_size} bytes"
                )

        ndblock = 1
        for i in range(inode_block_count):
            signature_targets.append(SignatureTarget(1 + i, header_inode_block_sig_offset(i), block_size, 3))
        ndblock += inode_block_count

        super_root_inode.blocks = 1
        ndblock = assign_signed_inode_layout(
            super_root_inode,
            super_root_inode.blocks,
            block_size,
            ndblock,
            signature_targets,
            indirect_block_records,
        )

        fpt_inode.size = len(fpt_blob)
        fpt_inode.size_compressed = len(fpt_blob)
        fpt_inode.blocks = max(1, ceil_div(len(fpt_blob), block_size))
        ndblock = assign_signed_inode_layout(
            fpt_inode,
            fpt_inode.blocks,
            block_size,
            ndblock,
            signature_targets,
            indirect_block_records,
        )

        if has_collision and collision_inode is not None:
            collision_inode.blocks = max(1, ceil_div(len(collision_blob or b""), block_size))
            ndblock = assign_signed_inode_layout(
                collision_inode,
                collision_inode.blocks,
                block_size,
                ndblock,
                signature_targets,
                indirect_block_records,
            )

        ndblock += 2

        for inode, payload, is_dir in all_nodes_data:
            blocks = max(1, ceil_div(len(payload), block_size)) if len(payload) > 0 else 1
            inode.blocks = blocks
            if is_dir:
                inode.size = blocks * block_size
                inode.size_compressed = inode.size
            else:
                if inode.flags & consts.INODE_FLAG_COMPRESSED:
                    inode.size_compressed = len(payload)
                else:
                    inode.size = len(payload)
                    inode.size_compressed = inode.size
            ndblock = assign_signed_inode_layout(
                inode,
                blocks,
                block_size,
                ndblock,
                signature_targets,
                indirect_block_records,
            )

        signature_targets.append(SignatureTarget(0, consts.HEADER_DIGEST_OFFSET, consts.HEADER_DIGEST_SIZE, 4))
    else:
        ndblock = 1
        ndblock += inode_block_count

        super_root_inode.db[0] = ndblock
        ndblock += super_root_inode.blocks

        fpt_inode.size = len(fpt_blob)
        fpt_inode.size_compressed = len(fpt_blob)
        fpt_inode.blocks = max(1, ceil_div(len(fpt_blob), block_size))
        fpt_inode.db[0] = ndblock
        for i in range(1, consts.MAX_DIRECT_BLOCKS):
            fpt_inode.db[i] = -1
        ndblock += fpt_inode.blocks

        if has_collision and collision_inode is not None:
            collision_inode.db[0] = ndblock
            for i in range(1, consts.MAX_DIRECT_BLOCKS):
                collision_inode.db[i] = -1
            ndblock += collision_inode.blocks
        else:
            ndblock += 1

        for inode, payload, is_dir in all_nodes_data:
            blocks = max(1, ceil_div(len(payload), block_size)) if len(payload) > 0 else 1
            inode.db[0] = ndblock
            inode.blocks = blocks
            for i in range(1, consts.MAX_DIRECT_BLOCKS):
                inode.db[i] = -1
            if is_dir:
                inode.size = blocks * block_size
                inode.size_compressed = inode.size
            else:
                if inode.flags & consts.INODE_FLAG_COMPRESSED:
                    inode.size_compressed = len(payload)
                else:
                    inode.size = len(payload)
                    inode.size_compressed = inode.size
            ndblock += blocks

    nblock = 1
    final_ndblock = ndblock

    validate_d32_ranges(inodes, final_ndblock)

    stats = BuildStats(input_path=source_root, output_path=output_path)
    stats.total_files = len(file_nodes_sorted)
    stats.uncompressed_total_size = sum(f.raw_size for f in file_nodes_sorted)
    stats.stored_total_size = sum(f.stored_size for f in file_nodes_sorted)
    stats.all_compressed_total_size = sum(f.hypothetical_compressed_size for f in file_nodes_sorted)
    stats.compressed_files = sum(1 for f in file_nodes_sorted if f.compressed)
    stats.uncompressed_files = stats.total_files - stats.compressed_files
    stats.block_size = block_size
    stats.block_alignment_waste = sum(
        (ceil_div(f.stored_size, block_size) * block_size - f.stored_size) if f.stored_size > 0 else block_size
        for f in file_nodes_sorted
    )

    if verbose:
        for f in file_nodes_sorted:
            state: str = "compressed" if f.compressed else "raw"
            info(
                f"[file] {f.rel_path}: raw={f.raw_size} stored={f.stored_size} gain={f.gain_pct:.2f}% mode={state}",
                icon_name="file",
            )

    if dry_run:
        stats.elapsed_seconds = time.time() - start
        return stats

    mode = compose_pfs_mode_with_sign(inode_bits, case_insensitive, signed)

    progress.status(f"\nWriting PFS image to {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temporary file first
    tmp_path = Path(str(output_path) + ".tmp")
    try:
        image_size = final_ndblock * block_size
        with tmp_path.open("w+b") as out:
            out.truncate(image_size)

            hdr = bytearray(block_size)
            struct.pack_into("<q", hdr, 0x00, pfs_version)
            struct.pack_into("<q", hdr, 0x08, consts.PFS_MAGIC)
            struct.pack_into("<q", hdr, 0x10, 0)
            struct.pack_into("<BBBB", hdr, 0x18, 0, 0, 1, 0)
            struct.pack_into("<H", hdr, 0x1C, mode)
            struct.pack_into("<H", hdr, 0x1E, 0)
            struct.pack_into("<I", hdr, 0x20, block_size)
            struct.pack_into("<I", hdr, 0x24, 0)
            struct.pack_into("<q", hdr, 0x28, nblock)
            struct.pack_into("<q", hdr, 0x30, inode_count)
            struct.pack_into("<q", hdr, 0x38, final_ndblock)
            struct.pack_into("<q", hdr, 0x40, inode_block_count)
            ib_sig_bytes = build_inode_block_sig_s64(inode_block_count, block_size, now, signed=signed)
            hdr[0x50 : 0x50 + len(ib_sig_bytes)] = ib_sig_bytes
            if signed:
                struct.pack_into("<I", hdr, 0x36C, 1)
                hdr[0x370 : 0x370 + len(consts.ZERO_PFS_SEED)] = consts.ZERO_PFS_SEED
            else:
                struct.pack_into("<I", hdr, 0x368, 1)

            out.seek(0)
            out.write(hdr)

            out.seek(block_size)
            for ino in inodes:
                out.write(ino.to_bytes_signed32() if signed else ino.to_bytes())
                if (out.tell() % block_size) > (block_size - inode_size):
                    out.seek(out.tell() + (block_size - (out.tell() % block_size)))

            out.seek(block_size * (inode_block_count + 1))
            for d in super_root_dirents:
                out.write(d.to_bytes())

            if signed:
                write_payload_to_blocks(
                    out,
                    fpt_blob,
                    collect_signed_block_numbers(fpt_inode, block_size, indirect_block_records),
                    block_size,
                )
                if has_collision and collision_inode is not None and collision_blob is not None:
                    write_payload_to_blocks(
                        out,
                        collision_blob,
                        collect_signed_block_numbers(collision_inode, block_size, indirect_block_records),
                        block_size,
                    )
                for block, records in indirect_block_records.items():
                    out.seek(block * block_size)
                    out.write(make_sig_records_blob(records, block_size))
            else:
                out.seek(fpt_inode.db[0] * block_size)
                out.write(fpt_blob)

                if has_collision and collision_inode is not None and collision_blob is not None:
                    out.seek(collision_inode.db[0] * block_size)
                    out.write(collision_blob)

            # Calculate total bytes for progress tracking
            total_write_bytes = sum(len(payload) for _, payload, _ in all_nodes_data)
            written_bytes = 0
            for idx, (inode, payload, _is_dir) in enumerate(all_nodes_data, start=1):
                if signed:
                    write_payload_to_blocks(
                        out,
                        payload,
                        collect_signed_block_numbers(inode, block_size, indirect_block_records),
                        block_size,
                    )
                else:
                    out.seek(inode.db[0] * block_size)
                    out.write(payload)
                written_bytes += len(payload)
                progress.step("write", written_bytes, total_write_bytes, bytes_processed=written_bytes)

            if signed:
                sign_key = pfs_gen_sign_key(consts.ZERO_EKPFS, consts.ZERO_PFS_SEED)
                for level in range(5):
                    for target in (t for t in signature_targets if t.level == level):
                        block_data = bytearray(_read_exact(out, target.block * block_size, target.size))
                        sig_pos_in_block = target.sig_offset - (target.block * block_size)
                        if 0 <= sig_pos_in_block <= len(block_data) - consts.SIG_SIZE:
                            block_data[sig_pos_in_block : sig_pos_in_block + consts.SIG_SIZE] = (
                                b"\x00" * consts.SIG_SIZE
                            )
                        out.seek(target.sig_offset)
                        out.write(hmac_sha256(sign_key, bytes(block_data)))

        # Validate the temporary file
        validate_image_quick(tmp_path, block_size, mode, pfs_version)

        # Rename temp file to final output path
        shutil.move(str(tmp_path), str(output_path))
        progress.status(f"Successfully wrote {human_readable_size(image_size)} image")

    except Exception:
        # Broad exception handler is used here to ensure temporary file cleanup
        # for any failure that occurs during writing. We re-raise after cleanup
        # so callers still see the original error.
        if tmp_path.exists():
            with suppress(FileNotFoundError):
                tmp_path.unlink()
        raise

    stats.elapsed_seconds = time.time() - start
    return stats


def validate_image_quick(
    image_path: Path,
    expected_block_size: int,
    expected_mode: int,
    expected_version: int,
) -> None:
    with image_path.open("rb") as f:
        hdr = f.read(0x400)
    if len(hdr) < 0x400:
        raise BuildError("Output image header is too small")
    version, magic = struct.unpack_from("<qq", hdr, 0x00)
    readonly = struct.unpack_from("<B", hdr, 0x1A)[0]
    mode = struct.unpack_from("<H", hdr, 0x1C)[0]
    block_size = struct.unpack_from("<I", hdr, 0x20)[0]
    dinode_count = struct.unpack_from("<q", hdr, 0x30)[0]
    dinode_blocks = struct.unpack_from("<q", hdr, 0x40)[0]

    if version != expected_version or magic != consts.PFS_MAGIC:
        raise BuildError("Post-write validation failed: invalid header magic/version")
    if block_size != expected_block_size:
        raise BuildError("Post-write validation failed: unexpected block size")
    if readonly != 1:
        raise BuildError("Post-write validation failed: header readonly byte is not set")
    if mode != expected_mode:
        raise BuildError("Post-write validation failed: unexpected mode flags")
    if dinode_count < 3 or dinode_blocks < 1:
        raise BuildError("Post-write validation failed: inode table looks invalid")

    signed = (expected_mode & consts.PFS_MODE_SIGNED) != 0
    inode_size = consts.INODE_S32_SIZE if signed else consts.INODE_D32_SIZE
    inodes_per_block = expected_block_size // inode_size
    with image_path.open("rb") as f:
        f.seek(expected_block_size)  # inode table starts at block 1
        parsed = 0
        for _ in range(dinode_blocks):
            block = f.read(expected_block_size)
            if len(block) != expected_block_size:
                raise BuildError("Post-write validation failed: truncated inode block")
            for idx in range(inodes_per_block):
                if parsed >= dinode_count:
                    break
                off = idx * inode_size
                mode_bits = struct.unpack_from("<H", block, off)[0]
                flags_bits = struct.unpack_from("<I", block, off + 4)[0]
                if mode_bits & consts.INODE_MODE_ANY_WRITE:
                    raise BuildError(
                        f"Post-write validation failed: inode {parsed} has write bits set (mode=0x{mode_bits:04X})"
                    )
                if not signed and (flags_bits & consts.INODE_FLAG_READONLY) == 0:
                    raise BuildError(
                        "Post-write validation failed: "
                        f"inode {parsed} missing readonly flag (flags=0x{flags_bits:08X})"
                    )
                parsed += 1


def prompt_overwrite(output_path: Path) -> bool:
    """Prompt user if output file exists. Returns True if it should proceed."""
    if not output_path.exists():
        return True

    info(f"Output file already exists: {output_path}", icon_name="file")
    while True:
        response = input("Overwrite? [Y/n] ").strip().lower()
        if response in ["y", "yes", ""]:
            # Clean up any partial .tmp file if it exists
            tmp_path = Path(str(output_path) + ".tmp")
            if tmp_path.exists():
                with suppress(OSError):
                    tmp_path.unlink()
            return True
        elif response in ["n", "no"]:
            return False
        else:
            info("Please enter 'y' or 'n'")


@dataclass
class ParsedHeader:
    version: int
    magic: int
    mode: int
    block_size: int
    nblock: int
    dinode_count: int
    ndblock: int
    dinode_block_count: int
    readonly: int
    seed: bytes


@dataclass
class ParsedInode:
    number: int
    mode: int
    nlink: int
    flags: int
    size: int
    size_compressed: int
    blocks: int
    db: list[int]
    ib: list[int]
    db_sig: list[bytes] = field(default_factory=list)
    ib_sig: list[bytes] = field(default_factory=list)

    @property
    def is_dir(self) -> bool:
        return (self.mode & consts.INODE_MODE_DIR) != 0

    @property
    def is_file(self) -> bool:
        return (self.mode & consts.INODE_MODE_FILE) != 0

    @property
    def is_compressed(self) -> bool:
        return (self.flags & consts.INODE_FLAG_COMPRESSED) != 0


@dataclass
class ParsedDirent:
    inode_number: int
    type_code: int
    name: str


def parse_image_header(fh: BinaryIO) -> ParsedHeader:
    hdr = _read_exact(fh, 0, 0x400)
    version, magic = struct.unpack_from("<qq", hdr, 0x00)
    readonly = struct.unpack_from("<B", hdr, 0x1A)[0]
    mode = struct.unpack_from("<H", hdr, 0x1C)[0]
    block_size = struct.unpack_from("<I", hdr, 0x20)[0]
    nblock = struct.unpack_from("<q", hdr, 0x28)[0]
    dinode_count = struct.unpack_from("<q", hdr, 0x30)[0]
    ndblock = struct.unpack_from("<q", hdr, 0x38)[0]
    dinode_block_count = struct.unpack_from("<q", hdr, 0x40)[0]
    seed = hdr[0x370:0x380]
    return ParsedHeader(
        version=version,
        magic=magic,
        mode=mode,
        block_size=block_size,
        nblock=nblock,
        dinode_count=dinode_count,
        ndblock=ndblock,
        dinode_block_count=dinode_block_count,
        readonly=readonly,
        seed=seed,
    )


def parse_image_inode(blob: bytes, number: int, signed: bool) -> ParsedInode:
    expected_size = consts.INODE_S32_SIZE if signed else consts.INODE_D32_SIZE
    if len(blob) != expected_size:
        raise ValueError(f"inode blob has invalid size {len(blob)}")

    mode, nlink, flags = struct.unpack_from("<HHI", blob, 0x00)
    size, size_compressed = struct.unpack_from("<qq", blob, 0x08)
    blocks = struct.unpack_from("<I", blob, 0x60)[0]

    if signed:
        db_sig: list[bytes] = []
        db: list[int] = []
        ib_sig: list[bytes] = []
        ib: list[int] = []
        offset = 0x64
        for _ in range(consts.MAX_DIRECT_BLOCKS):
            db_sig.append(blob[offset : offset + consts.SIG_SIZE])
            db.append(struct.unpack_from("<i", blob, offset + consts.SIG_SIZE)[0])
            offset += consts.SIG_ENTRY_SIZE
        for _ in range(consts.MAX_INDIRECT_BLOCKS):
            ib_sig.append(blob[offset : offset + consts.SIG_SIZE])
            ib.append(struct.unpack_from("<i", blob, offset + consts.SIG_SIZE)[0])
            offset += consts.SIG_ENTRY_SIZE
        return ParsedInode(
            number=number,
            mode=mode,
            nlink=nlink,
            flags=flags,
            size=size,
            size_compressed=size_compressed,
            blocks=blocks,
            db=db,
            ib=ib,
            db_sig=db_sig,
            ib_sig=ib_sig,
        )

    db = list(struct.unpack_from("<12i", blob, 0x64))
    ib = list(struct.unpack_from("<5i", blob, 0x94))
    return ParsedInode(
        number=number,
        mode=mode,
        nlink=nlink,
        flags=flags,
        size=size,
        size_compressed=size_compressed,
        blocks=blocks,
        db=db,
        ib=ib,
    )


def parse_image_inodes(fh: BinaryIO, header: ParsedHeader) -> list[ParsedInode]:
    inodes: list[ParsedInode] = []
    signed = (header.mode & consts.PFS_MODE_SIGNED) != 0
    inode_size = consts.INODE_S32_SIZE if signed else consts.INODE_D32_SIZE
    inodes_per_block = header.block_size // inode_size
    if inodes_per_block <= 0:
        raise ValueError("block size too small for inode table")

    inode_idx = 0
    table_offset = header.block_size
    for block_idx in range(header.dinode_block_count):
        block = _read_exact(fh, table_offset + block_idx * header.block_size, header.block_size)
        for i in range(inodes_per_block):
            if inode_idx >= header.dinode_count:
                return inodes
            off = i * inode_size
            inode_blob = block[off : off + inode_size]
            inodes.append(parse_image_inode(inode_blob, inode_idx, signed=signed))
            inode_idx += 1
    return inodes


def parse_sig_record_block(fh: BinaryIO, block_num: int, block_size: int) -> list[tuple[bytes, int]]:
    blob = _read_exact(fh, block_num * block_size, block_size)
    records: list[tuple[bytes, int]] = []
    for offset in range(0, block_size, consts.SIG_ENTRY_SIZE):
        if offset + consts.SIG_ENTRY_SIZE > block_size:
            break
        sig = blob[offset : offset + consts.SIG_SIZE]
        block = struct.unpack_from("<i", blob, offset + consts.SIG_SIZE)[0]
        records.append((sig, block))
    return records


def block_hmac_without_slot(block_data: bytes, sig_offset_in_block: int, size: int, signed: bool = True) -> bytes:
    chunk = bytearray(block_data[:size])
    if signed and 0 <= sig_offset_in_block <= len(chunk) - consts.SIG_SIZE:
        chunk[sig_offset_in_block : sig_offset_in_block + consts.SIG_SIZE] = b"\x00" * consts.SIG_SIZE
    return bytes(chunk)


def verify_signed_image_signatures(
    fh: BinaryIO,
    header: ParsedHeader,
    inodes: list[ParsedInode],
    errors: list[str],
) -> None:
    if (header.mode & consts.PFS_MODE_SIGNED) == 0:
        return

    sign_key = pfs_gen_sign_key(consts.ZERO_EKPFS, header.seed)

    for i in range(header.dinode_block_count):
        block_num = 1 + i
        block_data = _read_exact(fh, block_num * header.block_size, header.block_size)
        sig_offset = header_inode_block_sig_offset(i)
        expected = hmac_sha256(sign_key, block_hmac_without_slot(block_data, 0, header.block_size, signed=False))
        actual = _read_exact(fh, sig_offset, consts.SIG_SIZE)
        if actual != expected:
            errors.append(f"inode block signature mismatch for block {block_num}")

    header_region = bytearray(_read_exact(fh, 0, consts.HEADER_DIGEST_SIZE))
    header_region[consts.HEADER_DIGEST_OFFSET : consts.HEADER_DIGEST_OFFSET + consts.SIG_SIZE] = (
        b"\x00" * consts.SIG_SIZE
    )
    expected_header_sig = hmac_sha256(sign_key, bytes(header_region))
    actual_header_sig = _read_exact(fh, consts.HEADER_DIGEST_OFFSET, consts.SIG_SIZE)
    if actual_header_sig != expected_header_sig:
        errors.append("header signature region digest mismatch")

    for inode in inodes:
        remaining = inode.blocks
        direct_count = min(remaining, consts.MAX_DIRECT_BLOCKS)
        for idx in range(direct_count):
            block = inode.db[idx]
            if block <= 0:
                errors.append(f"inode {inode.number} has invalid direct block db[{idx}]={block}")
                continue
            block_data = _read_exact(fh, block * header.block_size, header.block_size)
            expected = hmac_sha256(sign_key, block_data)
            actual = inode.db_sig[idx]
            if actual != expected:
                errors.append(f"inode {inode.number} direct signature mismatch at db[{idx}] -> block {block}")
        remaining -= direct_count

        sigs_per_block = header.block_size // consts.SIG_ENTRY_SIZE
        if remaining > 0:
            ib0 = inode.ib[0]
            if ib0 <= 0:
                errors.append(f"inode {inode.number} missing ib[0] for signed block chain")
            else:
                ib0_data = _read_exact(fh, ib0 * header.block_size, header.block_size)
                if inode.ib_sig[0] != hmac_sha256(sign_key, ib0_data):
                    errors.append(f"inode {inode.number} indirect signature mismatch at ib[0] -> block {ib0}")
                records = parse_sig_record_block(fh, ib0, header.block_size)
                take = min(remaining, sigs_per_block)
                for rec_idx, (sig, block) in enumerate(records[:take]):
                    if block <= 0:
                        errors.append(f"inode {inode.number} ib[0] record {rec_idx} has invalid block {block}")
                        continue
                    expected = hmac_sha256(sign_key, _read_exact(fh, block * header.block_size, header.block_size))
                    if sig != expected:
                        errors.append(
                            f"inode {inode.number} ib[0] record {rec_idx} signature mismatch for block {block}"
                        )
                remaining -= take

        if remaining > 0:
            ib1 = inode.ib[1]
            if ib1 <= 0:
                errors.append(f"inode {inode.number} missing ib[1] for signed block chain")
            else:
                ib1_data = _read_exact(fh, ib1 * header.block_size, header.block_size)
                if inode.ib_sig[1] != hmac_sha256(sign_key, ib1_data):
                    errors.append(f"inode {inode.number} indirect signature mismatch at ib[1] -> block {ib1}")
                parent_records = parse_sig_record_block(fh, ib1, header.block_size)
                for parent_idx, (parent_sig, child_indirect) in enumerate(parent_records):
                    if remaining <= 0:
                        break
                    if child_indirect <= 0:
                        errors.append(
                            f"inode {inode.number} ib[1] record {parent_idx} has invalid block {child_indirect}"
                        )
                        continue
                    child_data = _read_exact(fh, child_indirect * header.block_size, header.block_size)
                    if parent_sig != hmac_sha256(sign_key, child_data):
                        errors.append(
                            f"inode {inode.number} ib[1] record {parent_idx} "
                            f"signature mismatch for block {child_indirect}"
                        )
                    child_records = parse_sig_record_block(fh, child_indirect, header.block_size)
                    take = min(remaining, sigs_per_block)
                    for rec_idx, (sig, block) in enumerate(child_records[:take]):
                        if block <= 0:
                            errors.append(
                                f"inode {inode.number} ib[1][{parent_idx}] record {rec_idx} has invalid block {block}"
                            )
                            continue
                        expected = hmac_sha256(sign_key, _read_exact(fh, block * header.block_size, header.block_size))
                        if sig != expected:
                            errors.append(
                                f"inode {inode.number} ib[1][{parent_idx}] record {rec_idx} "
                                f"signature mismatch for block {block}"
                            )
                    remaining -= take

        if remaining > 0:
            errors.append(f"inode {inode.number} exceeds supported signed verification depth")


def resolve_signed_inode_blocks(
    fh: BinaryIO, header: ParsedHeader, inode: ParsedInode, errors: list[str] | None = None
) -> list[int]:
    blocks: list[int] = []
    direct_count = min(inode.blocks, consts.MAX_DIRECT_BLOCKS)
    blocks.extend(inode.db[:direct_count])
    remaining = inode.blocks - direct_count
    sigs_per_block = header.block_size // consts.SIG_ENTRY_SIZE

    if remaining > 0:
        if inode.ib[0] <= 0:
            if errors is not None:
                errors.append(f"inode {inode.number} missing ib[0] for signed block chain")
            return blocks
        records = parse_sig_record_block(fh, inode.ib[0], header.block_size)
        take = min(remaining, sigs_per_block)
        blocks.extend(block for _sig, block in records[:take])
        remaining -= take

    if remaining > 0:
        if inode.ib[1] <= 0:
            if errors is not None:
                errors.append(f"inode {inode.number} missing ib[1] for signed block chain")
            return blocks
        parent_records = parse_sig_record_block(fh, inode.ib[1], header.block_size)
        for _sig, child_block in parent_records:
            if remaining <= 0:
                break
            child_records = parse_sig_record_block(fh, child_block, header.block_size)
            take = min(remaining, sigs_per_block)
            blocks.extend(block for _sig2, block in child_records[:take])
            remaining -= take

    if remaining > 0 and errors is not None:
        errors.append(f"inode {inode.number} uses unsupported signed indirection depth")
    return blocks


def parse_image_dirents(blob: bytes, strict: bool = False) -> tuple[list[ParsedDirent], list[str]]:
    dirents: list[ParsedDirent] = []
    errors: list[str] = []
    offset = 0
    while offset + 16 <= len(blob):
        inode_number, type_code, name_len, ent_size = struct.unpack_from("<Iiii", blob, offset)
        if inode_number == 0 and type_code == 0 and name_len == 0 and ent_size == 0:
            break

        if ent_size < 17 or (ent_size % 8) != 0:
            msg = f"invalid dirent size {ent_size} at offset {offset}"
            if strict:
                errors.append(msg)
            break
        if name_len < 0 or name_len > ent_size - 16:
            msg = f"invalid dirent name length {name_len} at offset {offset}"
            if strict:
                errors.append(msg)
            break
        if offset + ent_size > len(blob):
            msg = f"dirent at offset {offset} exceeds payload boundary"
            if strict:
                errors.append(msg)
            break

        name_bytes = blob[offset + 16 : offset + 16 + name_len]
        try:
            name = name_bytes.decode("ascii", errors="strict")
        except UnicodeDecodeError:
            name = name_bytes.decode("ascii", errors="replace")
            if strict:
                errors.append(f"non-ascii dirent name at offset {offset}")

        dirents.append(ParsedDirent(inode_number=inode_number, type_code=type_code, name=name))
        offset += ent_size

    return dirents, errors


def read_image_inode_payload(fh: BinaryIO, inode: ParsedInode, block_size: int) -> bytes:
    if inode.blocks <= 0:
        return b""
    if inode.size_compressed < 0:
        raise ValueError(f"inode {inode.number} has negative size_compressed")
    if inode.db_sig or inode.ib_sig:
        block_numbers = resolve_signed_inode_blocks(
            fh,
            ParsedHeader(0, 0, 0, block_size, 0, 0, 0, 0, 0, b""),
            inode,
        )
        data = bytearray()
        for block in block_numbers:
            data += _read_exact(fh, block * block_size, block_size)
        data = bytes(data[: inode.size_compressed])
    else:
        fh.seek(inode.db[0] * block_size)
        data = fh.read(inode.size_compressed)
    if len(data) != inode.size_compressed:
        raise ValueError(f"inode {inode.number} payload truncated")
    return data


def parse_superroot_and_indexes(
    fh: BinaryIO,
    header: ParsedHeader,
    inodes: list[ParsedInode],
    errors: list[str],
) -> tuple[int, dict[int, int], dict[int, list[ParsedDirent]], set[int]]:
    super_root_offset = (1 + header.dinode_block_count) * header.block_size
    blob = _read_exact(fh, super_root_offset, header.block_size)
    super_entries, parse_errors = parse_image_dirents(blob, strict=True)
    for e in parse_errors:
        errors.append(f"superroot: {e}")

    fpt_inode = None
    collision_inode = None
    uroot_inode = None
    special_inodes: set[int] = {0}
    for ent in super_entries:
        if ent.name == "flat_path_table":
            fpt_inode = ent.inode_number
        elif ent.name == "collision_resolver":
            collision_inode = ent.inode_number
        elif ent.name == "uroot":
            uroot_inode = ent.inode_number

    if fpt_inode is None:
        errors.append("superroot missing 'flat_path_table' entry")
    if uroot_inode is None:
        errors.append("superroot missing 'uroot' entry")

    if fpt_inode is not None:
        special_inodes.add(fpt_inode)
    if collision_inode is not None:
        special_inodes.add(collision_inode)
    if uroot_inode is not None:
        special_inodes.add(uroot_inode)

    fpt_map: dict[int, int] = {}
    collision_map: dict[int, list[ParsedDirent]] = {}

    if fpt_inode is not None and 0 <= fpt_inode < len(inodes):
        fpt_blob = read_image_inode_payload(fh, inodes[fpt_inode], header.block_size)
        if (len(fpt_blob) % 8) != 0:
            errors.append("flat_path_table size is not divisible by 8")

        for i in range(0, len(fpt_blob) - (len(fpt_blob) % 8), 8):
            h, v = struct.unpack_from("<II", fpt_blob, i)
            if h in fpt_map:
                errors.append(f"flat_path_table has duplicate hash 0x{h:08X}")
            fpt_map[h] = v

        if any((v & 0x80000000) for v in fpt_map.values()):
            if collision_inode is None:
                errors.append("flat_path_table has collision entries but no collision_resolver inode")
            elif 0 <= collision_inode < len(inodes):
                c_blob = read_image_inode_payload(fh, inodes[collision_inode], header.block_size)
                for h, v in fpt_map.items():
                    if (v & 0x80000000) == 0:
                        continue
                    offset = v & 0x7FFFFFFF
                    if offset >= len(c_blob):
                        errors.append(f"collision_resolver offset {offset} out of range for hash 0x{h:08X}")
                        continue
                    entries, parse_err = parse_image_dirents(c_blob[offset:], strict=True)
                    if parse_err:
                        errors.extend([f"collision_resolver hash 0x{h:08X}: {e}" for e in parse_err])
                    collision_map[h] = entries

    return (uroot_inode if uroot_inode is not None else -1), fpt_map, collision_map, special_inodes


def build_tree_from_uroot(
    fh: BinaryIO,
    header: ParsedHeader,
    inodes: list[ParsedInode],
    uroot_inode: int,
    errors: list[str],
) -> tuple[dict[str, int], dict[str, int], dict[int, list[ParsedDirent]]]:
    files: dict[str, int] = {}
    dirs: dict[str, int] = {"": uroot_inode}
    dirents_by_inode: dict[int, list[ParsedDirent]] = {}
    visited: set[int] = set()
    dir_path_by_inode: dict[int, str] = {uroot_inode: ""}

    def walk(dir_inode_num: int, rel_path: str, parent_inode_num: int, ancestors: set[int]) -> None:
        if dir_inode_num in visited:
            return
        visited.add(dir_inode_num)

        if not (0 <= dir_inode_num < len(inodes)):
            errors.append(f"directory inode {dir_inode_num} is out of range")
            return

        inode = inodes[dir_inode_num]
        if not inode.is_dir:
            errors.append(f"inode {dir_inode_num} referenced as directory but mode is 0x{inode.mode:04X}")
            return

        payload = read_image_inode_payload(fh, inode, header.block_size)
        entries, parse_errors = parse_image_dirents(payload, strict=True)
        dirents_by_inode[dir_inode_num] = entries
        for e in parse_errors:
            errors.append(f"inode {dir_inode_num}: {e}")

        dot_entries = [e for e in entries if e.name == "."]
        dotdot_entries = [e for e in entries if e.name == ".."]
        dot = dot_entries[0] if dot_entries else None
        dotdot = dotdot_entries[0] if dotdot_entries else None

        if len(dot_entries) != 1:
            errors.append(f"directory '{rel_path or '/'}' must contain exactly one '.' entry")
        if dot is None:
            errors.append(f"directory '{rel_path or '/'}' missing '.' entry")
        elif dot.inode_number != dir_inode_num:
            errors.append(f"directory '{rel_path or '/'}' has '.' -> {dot.inode_number}, expected {dir_inode_num}")
        elif dot.type_code != consts.DIRENT_TYPE_DOT:
            errors.append(f"directory '{rel_path or '/'}' has '.' with invalid type {dot.type_code}")

        if len(dotdot_entries) != 1:
            errors.append(f"directory '{rel_path or '/'}' must contain exactly one '..' entry")
        if dotdot is None:
            errors.append(f"directory '{rel_path or '/'}' missing '..' entry")
        else:
            expected_parent = dir_inode_num if rel_path == "" else parent_inode_num
            if dotdot.inode_number != expected_parent:
                errors.append(
                    f"directory '{rel_path or '/'}' has '..' -> {dotdot.inode_number}, expected {expected_parent}"
                )
            if dotdot.type_code != consts.DIRENT_TYPE_DOTDOT:
                errors.append(f"directory '{rel_path or '/'}' has '..' with invalid type {dotdot.type_code}")

        names_seen: set[str] = set()
        next_ancestors = set(ancestors)
        next_ancestors.add(dir_inode_num)
        for ent in entries:
            if ent.name in (".", ".."):
                continue
            if ent.name in names_seen:
                errors.append(f"directory '{rel_path or '/'}' has duplicate entry '{ent.name}'")
                continue
            names_seen.add(ent.name)
            if "/" in ent.name:
                errors.append(f"directory '{rel_path or '/'}' has invalid entry name containing '/': {ent.name}")
                continue

            child_path = ent.name if rel_path == "" else f"{rel_path}/{ent.name}"
            if not (0 <= ent.inode_number < len(inodes)):
                errors.append(f"entry '{child_path}' references out-of-range inode {ent.inode_number}")
                continue

            child_inode = inodes[ent.inode_number]
            if ent.type_code == consts.DIRENT_TYPE_DIRECTORY:
                if not child_inode.is_dir:
                    errors.append(f"entry '{child_path}' typed directory but inode mode is 0x{child_inode.mode:04X}")
                    continue
                if ent.inode_number in next_ancestors:
                    errors.append(f"directory cycle detected at '{child_path}' (inode {ent.inode_number})")
                    continue
                prev_path = dir_path_by_inode.get(ent.inode_number)
                if prev_path is not None and prev_path != child_path:
                    errors.append(
                        f"directory inode {ent.inode_number} is reachable from multiple paths: "
                        f"'{prev_path}' and '{child_path}'"
                    )
                    continue
                dir_path_by_inode[ent.inode_number] = child_path
                dirs[child_path] = ent.inode_number
                walk(ent.inode_number, child_path, dir_inode_num, next_ancestors)
            elif ent.type_code == consts.DIRENT_TYPE_FILE:
                if not child_inode.is_file:
                    errors.append(f"entry '{child_path}' typed file but inode mode is 0x{child_inode.mode:04X}")
                    continue
                files[child_path] = ent.inode_number
            else:
                errors.append(f"directory '{rel_path or '/'}' has unsupported dirent type {ent.type_code}")

    walk(uroot_inode, "", uroot_inode, set())
    return files, dirs, dirents_by_inode


def verify_file_payload_hashes(
    fh: BinaryIO,
    header: ParsedHeader,
    inodes: list[ParsedInode],
    file_inodes: dict[str, int],
    errors: list[str],
) -> tuple[int, int, str]:
    manifest = hashlib.sha256()
    cumulative_crc = 0
    checked = 0

    for rel in sorted(file_inodes.keys()):
        inode_num = file_inodes[rel]
        inode = inodes[inode_num]
        try:
            payload = read_image_inode_payload(fh, inode, header.block_size)
        except Exception as exc:
            errors.append(f"failed to read file payload '{rel}' (inode {inode_num}): {exc}")
            continue

        logical_data = payload
        if inode.is_compressed:
            try:
                logical_data = zlib.decompress(payload)
            except zlib.error as exc:
                errors.append(f"file '{rel}' marked compressed but cannot decompress: {exc}")
                continue
            if inode.size >= 0 and len(logical_data) != inode.size:
                errors.append(
                    f"file '{rel}' decompressed size {len(logical_data)} does not match inode size {inode.size}"
                )
        else:
            if inode.size >= 0 and len(logical_data) != inode.size:
                errors.append(f"file '{rel}' size {len(logical_data)} does not match inode size {inode.size}")

        file_hash = hashlib.sha256(logical_data).digest()
        manifest.update(rel.encode("utf-8", errors="replace"))
        manifest.update(b"\0")
        manifest.update(file_hash)
        cumulative_crc = zlib.crc32(logical_data, cumulative_crc) & 0xFFFFFFFF
        checked += 1

    return checked, cumulative_crc, manifest.hexdigest()


def render_tree(dirents_by_inode: dict[int, list[ParsedDirent]], inode_num: int, prefix: str = "") -> list[str]:
    lines: list[str] = []
    entries = [e for e in dirents_by_inode.get(inode_num, []) if e.name not in (".", "..")]
    entries.sort(key=lambda e: (e.type_code != consts.DIRENT_TYPE_DIRECTORY, e.name.lower(), e.name))

    for idx, ent in enumerate(entries):
        last = idx == (len(entries) - 1)
        branch = "`-- " if last else "|-- "
        lines.append(prefix + branch + ent.name)
        if ent.type_code == consts.DIRENT_TYPE_DIRECTORY:
            child_prefix = prefix + ("    " if last else "|   ")
            lines.extend(render_tree(dirents_by_inode, ent.inode_number, child_prefix))
    return lines


def validate_inode_layout(
    header: ParsedHeader, inodes: list[ParsedInode], errors: list[str], warnings: list[str]
) -> None:
    if header.magic != consts.PFS_MAGIC:
        errors.append(f"header magic mismatch: 0x{header.magic:016X} != 0x{consts.PFS_MAGIC:016X}")
    if header.block_size <= 0 or (header.block_size & (header.block_size - 1)) != 0:
        errors.append(f"invalid block size {header.block_size}")
    if header.readonly != 1:
        warnings.append(f"header readonly byte is {header.readonly}, expected 1")
    if header.dinode_count != len(inodes):
        errors.append(f"inode count mismatch: header={header.dinode_count} parsed={len(inodes)}")

    used_ranges: list[tuple[int, int, int]] = []
    for inode in inodes:
        if inode.blocks <= 0:
            continue
        start = inode.db[0]
        end = start + inode.blocks - 1
        if start < 0:
            errors.append(f"inode {inode.number} has negative db[0]={start}")
            continue
        if end >= header.ndblock:
            errors.append(f"inode {inode.number} range [{start},{end}] exceeds ndblock {header.ndblock}")
        used_ranges.append((start, end, inode.number))

    used_ranges.sort()
    for i in range(1, len(used_ranges)):
        prev_start, prev_end, prev_ino = used_ranges[i - 1]
        curr_start, curr_end, curr_ino = used_ranges[i]
        if curr_start <= prev_end:
            errors.append(
                f"block overlap between inode {prev_ino} "
                f"[{prev_start},{prev_end}] and inode {curr_ino} [{curr_start},{curr_end}]"
            )


def build_expected_fpt(
    file_inodes: dict[str, int], dir_inodes: dict[str, int], case_insensitive: bool
) -> dict[int, list[tuple[str, bool, int]]]:
    out: dict[int, list[tuple[str, bool, int]]] = {}
    for rel_dir, inode_num in dir_inodes.items():
        if rel_dir == "":
            continue
        full = "/" + rel_dir
        h = fpt_hash(full, case_insensitive=case_insensitive)
        out.setdefault(h, []).append((full, True, inode_num))
    for rel_file, inode_num in file_inodes.items():
        full = "/" + rel_file
        h = fpt_hash(full, case_insensitive=case_insensitive)
        out.setdefault(h, []).append((full, False, inode_num))
    return out


def validate_fpt_maps(
    fpt_map: dict[int, int],
    collision_map: dict[int, list[ParsedDirent]],
    expected: dict[int, list[tuple[str, bool, int]]],
    errors: list[str],
) -> None:
    expected_hashes = set(expected.keys())
    table_hashes = set(fpt_map.keys())

    for h in sorted(expected_hashes - table_hashes):
        errors.append(f"flat_path_table missing hash 0x{h:08X}")
    for h in sorted(table_hashes - expected_hashes):
        errors.append(f"flat_path_table has unexpected hash 0x{h:08X}")

    for h in sorted(expected_hashes & table_hashes):
        exp_entries = expected[h]
        val = fpt_map[h]
        if len(exp_entries) == 1:
            exp_path, exp_is_dir, exp_inode = exp_entries[0]
            if val & 0x80000000:
                errors.append(f"hash 0x{h:08X} for {exp_path} unexpectedly points to collision resolver")
                continue
            act_is_dir = bool(val & 0x20000000)
            act_inode = val & 0x1FFFFFFF
            if act_is_dir != exp_is_dir or act_inode != exp_inode:
                errors.append(
                    f"hash 0x{h:08X} mismatch: actual inode={act_inode} dir={act_is_dir}, "
                    f"expected inode={exp_inode} dir={exp_is_dir} ({exp_path})"
                )
        else:
            if (val & 0x80000000) == 0:
                errors.append(f"hash 0x{h:08X} has collisions but does not point to collision resolver")
                continue
            actual_set = {
                (e.name, e.type_code == consts.DIRENT_TYPE_DIRECTORY, e.inode_number) for e in collision_map.get(h, [])
            }
            expected_set = set(exp_entries)
            if not expected_set.issubset(actual_set):
                errors.append(f"collision resolver for hash 0x{h:08X} is missing expected entries")


def validate_ps5_checklist(
    fh: BinaryIO,
    header: ParsedHeader,
    inodes: list[ParsedInode],
    file_inodes: dict[str, int],
    warnings: list[str],
    errors: list[str],
) -> None:
    if "sce_sys/param.json" in file_inodes:
        inode = inodes[file_inodes["sce_sys/param.json"]]
        payload = read_image_inode_payload(fh, inode, header.block_size)
        if inode.is_compressed:
            try:
                payload = zlib.decompress(payload)
            except zlib.error as exc:
                errors.append(f"sce_sys/param.json cannot be decompressed: {exc}")
                payload = b""
        if payload:
            try:
                parsed = json.loads(payload.decode("utf-8"))
                if not parsed.get("titleId") and not parsed.get("title_id"):
                    warnings.append("sce_sys/param.json missing titleId/title_id")
            except Exception as exc:
                errors.append(f"sce_sys/param.json invalid JSON: {exc}")
    else:
        warnings.append("sce_sys/param.json not found")

    if "eboot.bin" not in file_inodes:
        warnings.append("eboot.bin not found")
    if "sce_sys/pfs-version.dat" not in file_inodes:
        warnings.append("sce_sys/pfs-version.dat not found")


def validate_source_match(
    fh: BinaryIO,
    header: ParsedHeader,
    inodes: list[ParsedInode],
    file_inodes: dict[str, int],
    source: Path,
    errors: list[str],
) -> None:
    if not source.exists() or not source.is_dir():
        errors.append(f"source path does not exist or is not a directory: {source}")
        return

    source_files = sorted(p for p in source.rglob("*") if p.is_file())
    source_rel = {p.relative_to(source).as_posix() for p in source_files}
    image_rel = set(file_inodes.keys())

    for rel in sorted(source_rel - image_rel):
        errors.append(f"missing in image: {rel}")
    for rel in sorted(image_rel - source_rel):
        errors.append(f"extra in image: {rel}")

    for rel in sorted(source_rel & image_rel):
        inode = inodes[file_inodes[rel]]
        payload = read_image_inode_payload(fh, inode, header.block_size)
        if inode.is_compressed:
            try:
                payload = zlib.decompress(payload)
            except zlib.error as exc:
                errors.append(f"file '{rel}' marked compressed but failed to decompress: {exc}")
                continue

        src_data = (source / rel).read_bytes()
        if hashlib.sha256(src_data).digest() != hashlib.sha256(payload).digest():
            errors.append(f"content mismatch for file: {rel}")


@dataclass
class PFSOperationResult:
    """Base result object for high-level PFS operations.

    Args:
        image: Input image path.
        errors: Collected fatal or validation errors.
        warnings: Collected non-fatal warnings.
    """

    image: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PFSImageInfo(PFSOperationResult):
    """Lightweight PFS image metadata summary.

    Args:
        image: Input image path.
        errors: Collected fatal or validation errors.
        warnings: Collected non-fatal warnings.
        size_bytes: Image size on disk.
        header: Parsed image header, when available.
    """

    size_bytes: int = 0
    header: ParsedHeader | None = None

    @property
    def version_label(self) -> str:
        """Return the human-friendly version label."""
        if self.header is None:
            return ""
        return "PS5" if self.header.version == consts.PFS_VERSION_PS5 else "PS4"


@dataclass
class PFSImageInspection(PFSImageInfo):
    """Detailed PFS image inspection result.

    Args:
        image: Input image path.
        errors: Collected fatal or validation errors.
        warnings: Collected non-fatal warnings.
        size_bytes: Image size on disk.
        header: Parsed image header, when available.
        inodes: Parsed inode table.
        uroot_inode: Inode number of the filesystem root.
        file_inodes: Mapping of relative file paths to inode numbers.
        dir_inodes: Mapping of relative directory paths to inode numbers.
        dirents_by_inode: Parsed directory entries for each inode.
        fpt_map: Parsed flat_path_table entries.
        collision_map: Parsed collision resolver entries.
        special_inodes: Inodes reserved by the filesystem layout.
        checked_files: Number of payload hashes checked.
        data_crc32: Cumulative CRC32 of logical file payloads.
        manifest_sha256: SHA256 digest of the logical file manifest.
        compressed_files: Number of files stored compressed.
        logical_file_bytes: Total logical file payload bytes.
        stored_file_bytes: Total stored file payload bytes.
    """

    inodes: list[ParsedInode] = field(default_factory=list)
    uroot_inode: int = -1
    file_inodes: dict[str, int] = field(default_factory=dict)
    dir_inodes: dict[str, int] = field(default_factory=dict)
    dirents_by_inode: dict[int, list[ParsedDirent]] = field(default_factory=dict)
    fpt_map: dict[int, int] = field(default_factory=dict)
    collision_map: dict[int, list[ParsedDirent]] = field(default_factory=dict)
    special_inodes: set[int] = field(default_factory=set)
    checked_files: int = 0
    data_crc32: int = 0
    manifest_sha256: str = ""
    compressed_files: int = 0
    logical_file_bytes: int = 0
    stored_file_bytes: int = 0

    @property
    def has_tree(self) -> bool:
        """Return whether the inspection contains a parsed filesystem tree."""
        return self.uroot_inode >= 0 and len(self.dirents_by_inode) > 0


@dataclass
class PFSExtractionResult(PFSOperationResult):
    """Result of extracting a PFS image to a directory.

    Args:
        image: Input image path.
        errors: Collected fatal or validation errors.
        warnings: Collected non-fatal warnings.
        output_path: Destination directory path.
        files_written: Number of files written to disk.
        directories_created: Number of directories created or ensured.
        bytes_written: Total logical file bytes written to disk.
    """

    output_path: Path | None = None
    files_written: int = 0
    directories_created: int = 0
    bytes_written: int = 0


def _image_size_bytes(image: Path) -> int:
    """Return the size of a path on disk, or zero when unavailable."""
    try:
        return image.stat().st_size
    except OSError:
        return 0


def read_pfs_info(image: Path) -> PFSImageInfo:
    """Read lightweight metadata from a PFS image.

    Args:
        image: Input PFS image path.

    Returns:
        A structured summary containing the parsed header and any warnings or errors.
    """
    info = PFSImageInfo(image=image, size_bytes=_image_size_bytes(image))

    if not image.exists() or not image.is_file():
        info.errors.append(f"image path does not exist or is not a file: {image}")
        return info

    try:
        with image.open("rb") as fh:
            info.header = parse_image_header(fh)
    except (OSError, ValueError) as exc:
        info.errors.append(f"failed to read image header: {exc}")
        return info

    if info.header.magic != consts.PFS_MAGIC:
        info.errors.append(f"header magic mismatch: 0x{info.header.magic:016X} != 0x{consts.PFS_MAGIC:016X}")
    if info.header.block_size <= 0 or (info.header.block_size & (info.header.block_size - 1)) != 0:
        info.errors.append(f"invalid block size {info.header.block_size}")
    if info.header.readonly != 1:
        info.warnings.append(f"header readonly byte is {info.header.readonly}, expected 1")

    return info


def inspect_pfs_image(
    image: Path,
    source: Path | None = None,
    expected_crc32: int | None = None,
    expected_manifest_sha256: str | None = None,
) -> PFSImageInspection:
    """Inspect a PFS image and collect structural validation details.

    Args:
        image: Input PFS image path.
        source: Optional source tree to compare against.
        expected_crc32: Optional expected cumulative payload CRC32.
        expected_manifest_sha256: Optional expected manifest SHA256 digest.

    Returns:
        A detailed inspection report with parsed tree data, warnings, and errors.
    """
    inspection: PFSImageInspection = PFSImageInspection(image=image, size_bytes=_image_size_bytes(image))

    if not image.exists() or not image.is_file():
        inspection.errors.append(f"image path does not exist or is not a file: {image}")
        return inspection

    try:
        with image.open("rb") as fh:
            header: ParsedHeader = parse_image_header(fh)
            inspection.header = header

            try:
                inodes: list[ParsedInode] = parse_image_inodes(fh, header)
            except (OSError, ValueError) as exc:
                inspection.errors.append(f"failed to parse inode table: {exc}")
                return inspection

            inspection.inodes = inodes
            validate_inode_layout(header, inodes, inspection.errors, inspection.warnings)

            try:
                verify_signed_image_signatures(fh, header, inodes, inspection.errors)
            except (OSError, ValueError) as exc:
                inspection.errors.append(f"failed to verify image signatures: {exc}")

            try:
                (
                    inspection.uroot_inode,
                    inspection.fpt_map,
                    inspection.collision_map,
                    inspection.special_inodes,
                ) = parse_superroot_and_indexes(fh, header, inodes, inspection.errors)
            except (OSError, ValueError) as exc:
                inspection.errors.append(f"failed to parse superroot and indexes: {exc}")
                return inspection

            if inspection.uroot_inode >= 0:
                try:
                    inspection.file_inodes, inspection.dir_inodes, inspection.dirents_by_inode = build_tree_from_uroot(
                        fh,
                        header,
                        inodes,
                        inspection.uroot_inode,
                        inspection.errors,
                    )
                except (OSError, ValueError) as exc:
                    inspection.errors.append(f"failed to build filesystem tree: {exc}")
                    return inspection

                case_insensitive: bool = bool(header.mode & consts.PFS_MODE_CASE_INSENSITIVE)
                expected_fpt: dict = build_expected_fpt(
                    inspection.file_inodes, inspection.dir_inodes, case_insensitive
                )

                validate_fpt_maps(inspection.fpt_map, inspection.collision_map, expected_fpt, inspection.errors)
                validate_ps5_checklist(
                    fh, header, inodes, inspection.file_inodes, inspection.warnings, inspection.errors
                )

                try:
                    (
                        inspection.checked_files,
                        inspection.data_crc32,
                        inspection.manifest_sha256,
                    ) = verify_file_payload_hashes(
                        fh,
                        header,
                        inodes,
                        inspection.file_inodes,
                        inspection.errors,
                    )
                except (OSError, ValueError) as exc:
                    inspection.errors.append(f"failed to verify file payload hashes: {exc}")

                if expected_crc32 is not None and inspection.data_crc32 != expected_crc32:
                    inspection.errors.append(
                        f"CRC32 mismatch: actual 0x{inspection.data_crc32:08X}, expected 0x{expected_crc32:08X}"
                    )
                if (
                    expected_manifest_sha256 is not None
                    and inspection.manifest_sha256.lower() != expected_manifest_sha256.lower()
                ):
                    inspection.errors.append(
                        "Manifest SHA256 mismatch: actual "
                        f"{inspection.manifest_sha256}, expected {expected_manifest_sha256.lower()}"
                    )

                reachable = (
                    set(inspection.file_inodes.values())
                    | set(inspection.dir_inodes.values())
                    | set(inspection.special_inodes)
                )
                orphan_inodes = sorted(inode.number for inode in inodes if inode.number not in reachable)
                if orphan_inodes:
                    inspection.errors.append(
                        "orphan inodes not reachable from filesystem tree: "
                        + ", ".join(str(value) for value in orphan_inodes[:20])
                        + (" ..." if len(orphan_inodes) > 20 else "")
                    )

                if source is not None:
                    validate_source_match(fh, header, inodes, inspection.file_inodes, source, inspection.errors)

                inspection.compressed_files = sum(
                    1 for inode_num in inspection.file_inodes.values() if inodes[inode_num].is_compressed
                )
                inspection.logical_file_bytes = sum(
                    max(0, inodes[inode_num].size) for inode_num in inspection.file_inodes.values()
                )
                inspection.stored_file_bytes = sum(
                    max(0, inodes[inode_num].size_compressed) for inode_num in inspection.file_inodes.values()
                )
    except (OSError, ValueError) as exc:
        inspection.errors.append(f"failed to inspect image: {exc}")

    return inspection


def analyze_pfs_image(image: Path) -> PFSImageInspection:
    """Analyze a PFS image without comparing it to a source tree.

    Args:
        image: Input PFS image path.

    Returns:
        A detailed inspection report.
    """
    return inspect_pfs_image(image=image)


def verify_pfs_image(
    image: Path,
    source: Path | None = None,
    expected_crc32: int | None = None,
    expected_manifest_sha256: str | None = None,
) -> PFSImageInspection:
    """Verify a PFS image against optional source and hash expectations.

    Args:
        image: Input PFS image path.
        source: Optional source tree to compare against.
        expected_crc32: Optional expected cumulative payload CRC32.
        expected_manifest_sha256: Optional expected manifest SHA256 digest.

    Returns:
        A detailed inspection report.
    """
    return inspect_pfs_image(
        image=image,
        source=source,
        expected_crc32=expected_crc32,
        expected_manifest_sha256=expected_manifest_sha256,
    )


def extract_pfs_image(
    image: Path,
    output_path: Path,
    progress: Progress | None = None,
) -> PFSExtractionResult:
    """Extract all logical files from a PFS image.

    Args:
        image: Input PFS image path.
        output_path: Destination directory for extracted files.
        progress: Optional progress reporter.

    Returns:
        A structured extraction result.
    """
    result: PFSExtractionResult = PFSExtractionResult(image=image, output_path=output_path, bytes_written=0)
    inspection: PFSImageInspection = inspect_pfs_image(image=image)
    result.warnings.extend(inspection.warnings)
    result.errors.extend(inspection.errors)

    if result.errors:
        return result
    if inspection.header is None:
        result.errors.append("image header is not available")
        return result
    if output_path.exists() and not output_path.is_dir():
        result.errors.append(f"output path exists and is not a directory: {output_path}")
        return result

    directory_targets: list[Path] = [
        output_path / Path(rel_dir)
        for rel_dir in sorted(inspection.dir_inodes.keys(), key=lambda value: (value.count("/"), value.lower(), value))
        if rel_dir != ""
    ]
    file_targets: list[tuple[str, Path, int]] = [
        (rel_path, output_path / Path(rel_path), inode_num)
        for rel_path, inode_num in sorted(inspection.file_inodes.items())
    ]

    for directory_target in directory_targets:
        if directory_target.exists() and not directory_target.is_dir():
            result.errors.append(f"output path conflicts with a file: {directory_target}")
    for _rel_path, file_target, _inode_num in file_targets:
        if file_target.exists():
            result.errors.append(f"output file already exists: {file_target}")

    if result.errors:
        return result

    output_path.mkdir(parents=True, exist_ok=True)

    if progress is not None:
        progress.status(f"\nExtracting {len(file_targets)} files to {output_path}...")

    try:
        with image.open("rb") as fh:
            for directory_target in directory_targets:
                if not directory_target.exists():
                    directory_target.mkdir(parents=True, exist_ok=False)
                    result.directories_created += 1

            total_files: int = len(file_targets)
            for index, (rel_path, file_target, inode_num) in enumerate(file_targets, start=1):
                inode: ParsedInode = inspection.inodes[inode_num]
                payload = read_image_inode_payload(fh, inode, inspection.header.block_size)
                if inode.is_compressed:
                    try:
                        payload = zlib.decompress(payload)
                    except zlib.error as exc:
                        result.errors.append(f"failed to decompress file '{rel_path}': {exc}")
                        return result

                file_target.parent.mkdir(parents=True, exist_ok=True)
                file_target.write_bytes(payload)
                result.files_written += 1
                result.bytes_written += len(payload)

                if progress is not None:
                    progress.step("extract", index, total_files, bytes_processed=result.bytes_written)
    except (OSError, ValueError) as exc:
        result.errors.append(f"failed to extract image: {exc}")

    return result


# Thin, stable wrapper APIs --------------------------------------------------
def pfs_build(
    source_root: Path,
    output_path: Path,
    block_size: int,
    pfs_version: int,
    inode_bits: int,
    case_insensitive: bool,
    signed: bool,
    compress: bool,
    threshold_gain: int,
    cpu_count: int,
    zlib_level: int,
    dry_run: bool,
    verbose: bool,
) -> BuildStats:
    """Stable thin wrapper around :func:`build_pfs`.

    This wrapper exists to provide a stable, short and predictable symbol for
    external callers that prefer the `pfs_` prefix.
    """
    return build_pfs(
        source_root=source_root,
        output_path=output_path,
        block_size=block_size,
        pfs_version=pfs_version,
        inode_bits=inode_bits,
        case_insensitive=case_insensitive,
        signed=signed,
        compress=compress,
        threshold_gain=threshold_gain,
        cpu_count=cpu_count,
        zlib_level=zlib_level,
        dry_run=dry_run,
        verbose=verbose,
    )


def pfs_inspect(
    image: Path,
    source: Path | None = None,
    expected_crc32: int | None = None,
    expected_manifest_sha256: str | None = None,
) -> PFSImageInspection:
    """Thin wrapper around :func:`inspect_pfs_image` named with `pfs_` prefix."""
    return inspect_pfs_image(
        image=image,
        source=source,
        expected_crc32=expected_crc32,
        expected_manifest_sha256=expected_manifest_sha256,
    )


def pfs_read_info(image: Path) -> PFSImageInfo:
    """Thin wrapper around :func:`read_pfs_info` named with `pfs_` prefix."""
    return read_pfs_info(image)


def pfs_extract(image: Path, output_path: Path, progress: Progress | None = None) -> PFSExtractionResult:
    """Thin wrapper around :func:`extract_pfs_image` named with `pfs_` prefix."""
    return extract_pfs_image(image=image, output_path=output_path, progress=progress)


def pfs_verify(
    image: Path,
    source: Path | None = None,
    expected_crc32: int | None = None,
    expected_manifest_sha256: str | None = None,
) -> PFSImageInspection:
    """Thin wrapper around :func:`verify_pfs_image` named with `pfs_` prefix."""
    return verify_pfs_image(
        image=image,
        source=source,
        expected_crc32=expected_crc32,
        expected_manifest_sha256=expected_manifest_sha256,
    )
