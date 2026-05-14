"""Command-line interface for mkpfs package.

This module provides a clean CLI entry point that calls into the
implementation in src/mkpfs/psf.py. It is kept minimal and focused on
argument parsing and user-facing printing.
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import sys
from pathlib import Path

from . import consts
from .pfs import (
    BuildError,
    BuildStats,
    ParsedDirent,
    build_expected_fpt,
    build_pfs,
    build_tree_from_uroot,
    compose_pfs_mode_with_sign,
    human_readable_size,
    parse_image_header,
    parse_image_inodes,
    parse_superroot_and_indexes,
    render_tree,
    validate_fpt_maps,
    validate_inode_layout,
    validate_input,
    validate_ps5_checklist,
    validate_source_match,
    verify_file_payload_hashes,
    verify_signed_image_signatures,
)
from .utils import (
    is_power_of_two,
    normalize_output_path,
)


def print_build_parameters(
    source_path: Path,
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
) -> None:
    """Print build configuration at the start."""
    print("\n" + "=" * 70)
    print("PFS Image Builder - Parameters")
    print("=" * 70)
    mode = compose_pfs_mode_with_sign(inode_bits, case_insensitive, signed)
    print(f"  Source path:       {source_path}")
    print(f"  Output path:       {output_path}")
    ver_label = "PS5" if pfs_version == consts.PFS_VERSION_PS5 else "PS4"
    print(f"  Version:           {pfs_version} ({ver_label})")
    fmt = globals().get("PFS_MAGIC", "")
    print(f"  Format:            {fmt}")
    print(f"  Block size:        {block_size:,} bytes ({block_size // 1024} KiB)")
    print(f"  Inode width:       {inode_bits}-bit")
    print(
        f"  PFS mode:          0x{mode:04X}  (Bit 0=signed, Bit 1=64-bit inodes, "
        "Bit 2=encrypted, Bit 3=case insensitive)"
    )
    print(f"    Signed:          {'yes' if mode & consts.PFS_MODE_SIGNED else 'no'}")
    print(f"    64-bit inodes:   {'yes' if mode & consts.PFS_MODE_64BIT_INODES else 'no'}")
    print(f"    Encrypted:       {'yes' if mode & consts.PFS_MODE_ENCRYPTED else 'no'}")
    print(f"    Case insensitive: {'yes' if mode & consts.PFS_MODE_CASE_INSENSITIVE else 'no'}")
    print(f"  Compression:       {'enabled' if compress else 'disabled'}")
    if compress:
        print(f"  Threshold gain:    {threshold_gain}%")
        print(f"  CPU cores:         {'all available' if cpu_count == 0 else cpu_count}")
        print(f"  Zlib level:        {zlib_level}")
    print(f"  Dry run:           {'yes' if dry_run else 'no'}")
    print("=" * 70)


def print_summary(stats: BuildStats) -> None:
    print("\n" + "=" * 70)
    print("Build Summary")
    print("=" * 70)
    print(f"  Input path:              {stats.input_path}")
    print(f"  Output path:             {stats.output_path}")
    print(f"  Total files:             {stats.total_files:,}")
    print(f"  Total uncompressed size: {human_readable_size(stats.uncompressed_total_size)}")
    print(f"  Total stored size:       {human_readable_size(stats.stored_total_size)}")

    if stats.compression_enabled:
        print("\n  Compression Statistics:")
        print(f"    Compressed files:       {stats.compressed_files:,}")
        print(f"    Uncompressed files:     {stats.uncompressed_files:,}")
        print(f"    Actual gain achieved:   {stats.actual_gain_pct:.2f}%")
        print(
            "    Max theoretical gain:   "
            f"{stats.max_possible_gain_pct:.2f}%  "
            f"({human_readable_size(stats.all_compressed_total_size)} if all files compressed)"
        )
    else:
        print("\n  Compression:             disabled")

    aligned_total = stats.stored_total_size + stats.block_alignment_waste
    waste_pct = (stats.block_alignment_waste / aligned_total * 100.0) if aligned_total > 0 else 0.0
    print("\n  Block Alignment Waste:")
    print(f"    Block size:             {stats.block_size // 1024} KiB ({stats.block_size:,} bytes)")
    print(
        "    Wasted space:           "
        f"{human_readable_size(stats.block_alignment_waste)} "
        f"({waste_pct:.2f}% of file data blocks)"
    )

    print(f"\n  Elapsed time:            {stats.elapsed_seconds:.2f}s")

    if stats.total_files > 0:
        throughput = stats.uncompressed_total_size / (stats.elapsed_seconds + 0.001)
        print(f"  Throughput:              {human_readable_size(int(throughput))}/s")

    print("=" * 70 + "\n")


def prompt_overwrite(output_path: Path) -> bool:
    """Prompt user if output file exists. Returns True if it should proceed."""
    if not output_path.exists():
        return True

    print(f"Output file already exists: {output_path}")
    while True:
        response = input("Overwrite? [Y/n] ").strip().lower()
        if response in ("y", "yes", ""):
            # Clean up any partial .tmp file if it exists
            tmp_path = Path(str(output_path) + ".tmp")
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            return True
        if response in ("n", "no"):
            return False
        print("Please enter 'y' or 'n'")


def parse_args(argv: list | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a .ffpfs image from an app or homebrew folder")
    parser.add_argument("--path", required=True, help="Source app or homebrew folder")
    parser.add_argument("--output", required=True, help="Output image path")

    comp_group = parser.add_mutually_exclusive_group()
    comp_group.add_argument(
        "--compress", action="store_true", default=True, help="Enable per-file compression (default)"
    )
    comp_group.add_argument("--no-compress", action="store_true", help="Disable per-file compression")

    parser.add_argument(
        "--threshold-gain", type=int, default=20, help="Minimum gain percent to keep a file compressed (default: 20)"
    )
    parser.add_argument(
        "--block-size", default="auto", help="PFS block size in bytes, or 'auto' (default: auto=65536)"
    )
    parser.add_argument("--version", choices=["PS4", "PS5"], default="PS4", help="PFS profile version (default: PS4)")
    parser.add_argument(
        "--inode-bits", type=int, choices=[32, 64], default=32, help="Inode width mode bit (32 or 64, default: 32)"
    )

    case_group = parser.add_mutually_exclusive_group()
    case_group.add_argument("--case-sensitive", action="store_true", help="Build a case-sensitive image")
    case_group.add_argument("--case-insensitive", action="store_true", help="Set case-insensitive mode bit (default)")

    parser.add_argument(
        "--cpu-count", type=int, default=0, help="Number of CPU cores to use for compression (0 = all available)"
    )
    parser.add_argument("--compression-level", type=int, default=9, help="Zlib compression level (0-9, default: 9)")
    parser.add_argument("--signed", action="store_true", help="Build a signed PFS image using zero EKPFS/seed")
    parser.add_argument("--verbose", action="store_true", help="Verbose per-file decisions")
    parser.add_argument("--dry-run", action="store_true", help="Scan/layout/report only; do not write image")

    return parser.parse_args(argv)


def main_analyzer(argv: list | None = None) -> int:
    # Support analyzer subcommand by delegating before parsing build args.
    # Keeps existing build CLI behavior unchanged when 'analyze' is not used.
    if argv and len(argv) > 0 and argv[0] == "analyze":
        from .analyze import main as analyze_main

        return analyze_main(argv[1:])
    args = parse_args(argv)

    source_path = Path(args.path).expanduser().resolve()
    output_path, output_warn = normalize_output_path(args.output)
    output_path = output_path.expanduser().resolve()

    if output_warn:
        print(f"warning: {output_warn}", file=sys.stderr)

    if args.threshold_gain < 0 or args.threshold_gain > 100:
        raise BuildError("--threshold-gain must be within 0..100")

    if isinstance(args.block_size, str) and args.block_size.strip().lower() == "auto":
        block_size = 65536
    else:
        try:
            block_size = int(args.block_size)
        except (TypeError, ValueError) as exc:
            raise BuildError("--block-size must be an integer value or 'auto'") from exc

    # PFS-compatible values: power-of-two block size in the supported range.
    if not (block_size > 0 and (block_size & (block_size - 1)) == 0):
        raise BuildError("--block-size must be a power of two")
    if block_size < 0x1000 or block_size > 0x200000:
        raise BuildError("--block-size must be between 4096 and 2097152")

    available_cpu_count = mp.cpu_count()
    if args.cpu_count < 0 or args.cpu_count > available_cpu_count:
        raise BuildError(f"--cpu-count must be within 0..{available_cpu_count}")

    if args.compression_level < 0 or args.compression_level > 9:
        raise BuildError("--compression-level must be within 0..9")

    _title_id, warnings = validate_input(source_path)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)

    compress = not args.no_compress
    case_insensitive = args.case_insensitive or not args.case_sensitive
    pfs_version = consts.PFS_VERSION_PS5 if args.version == "PS5" else consts.PFS_VERSION_PS4

    print_build_parameters(
        source_path,
        output_path,
        block_size,
        pfs_version,
        args.inode_bits,
        case_insensitive,
        args.signed,
        compress,
        args.threshold_gain,
        args.cpu_count,
        args.compression_level,
        args.dry_run,
    )

    if not args.dry_run and not prompt_overwrite(output_path):
        print("Operation cancelled.")
        return 0

    stats = build_pfs(
        source_root=source_path,
        output_path=output_path,
        block_size=block_size,
        pfs_version=pfs_version,
        inode_bits=args.inode_bits,
        case_insensitive=case_insensitive,
        signed=args.signed,
        compress=compress,
        threshold_gain=args.threshold_gain,
        cpu_count=args.cpu_count,
        zlib_level=args.compression_level,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    print_summary(stats)
    return 0


def run_image_check(
    image: Path,
    source: Path | None,
    print_tree: bool,
    expected_crc32: int | None = None,
    expected_manifest_sha256: str | None = None,
    emit_report: bool = True,
) -> tuple[list[str], list[str], dict[int, list[ParsedDirent]], int]:
    errors: list[str] = []
    warnings: list[str] = []
    tree: dict[int, list[ParsedDirent]] = {}
    uroot_inode = -1

    if not image.exists() or not image.is_file():
        return [f"image path does not exist or is not a file: {image}"], [], tree, uroot_inode

    with image.open("rb") as fh:
        header = parse_image_header(fh)
        inodes = parse_image_inodes(fh, header)

        validate_inode_layout(header, inodes, errors, warnings)
        verify_signed_image_signatures(fh, header, inodes, errors)
        uroot_inode, fpt_map, collision_map, special_inodes = parse_superroot_and_indexes(fh, header, inodes, errors)

        if uroot_inode >= 0:
            file_inodes, dir_inodes, tree = build_tree_from_uroot(fh, header, inodes, uroot_inode, errors)

            case_insensitive = bool(header.mode & consts.PFS_MODE_CASE_INSENSITIVE)
            expected_fpt = build_expected_fpt(file_inodes, dir_inodes, case_insensitive)
            validate_fpt_maps(fpt_map, collision_map, expected_fpt, errors)
            validate_ps5_checklist(fh, header, inodes, file_inodes, warnings, errors)

            checked_files, data_crc32, manifest_sha256 = verify_file_payload_hashes(
                fh,
                header,
                inodes,
                file_inodes,
                errors,
            )

            if expected_crc32 is not None and data_crc32 != expected_crc32:
                errors.append(f"CRC32 mismatch: actual 0x{data_crc32:08X}, expected 0x{expected_crc32:08X}")
            if expected_manifest_sha256 is not None and manifest_sha256.lower() != expected_manifest_sha256.lower():
                errors.append(
                    f"Manifest SHA256 mismatch: actual {manifest_sha256}, expected {expected_manifest_sha256.lower()}"
                )

            reachable = set(file_inodes.values()) | set(dir_inodes.values()) | set(special_inodes)
            orphan_inodes = sorted(i.number for i in inodes if i.number not in reachable)
            if orphan_inodes:
                errors.append(
                    "orphan inodes not reachable from filesystem tree: "
                    + ", ".join(str(v) for v in orphan_inodes[:20])
                    + (" ..." if len(orphan_inodes) > 20 else "")
                )

            if source is not None:
                validate_source_match(fh, header, inodes, file_inodes, source, errors)

            compressed_count = sum(1 for i in file_inodes.values() if inodes[i].is_compressed)
            total_logical = sum(max(0, inodes[i].size) for i in file_inodes.values())
            total_stored = sum(max(0, inodes[i].size_compressed) for i in file_inodes.values())

            if emit_report:
                print("=" * 70)
                print("PFS Check Report")
                print("=" * 70)
                print(f"Image:                 {image}")
                ver_label = "PS5" if header.version == consts.PFS_VERSION_PS5 else "PS4"
                print(f"Version:               {header.version} ({ver_label})")
                print(f"Format:                {header.magic}")
                print(f"Read-only:             {'yes' if header.readonly else 'no'}")
                print(
                    "Mode:                  "
                    f"0x{header.mode:04X}  (Bit 0=signed, Bit 1=64-bit inodes, "
                    "Bit 2=encrypted, Bit 3=case insensitive)"
                )
                print(f"  Signed:              {'yes' if header.mode & consts.PFS_MODE_SIGNED else 'no'}")
                print(f"  64-bit inodes:       {'yes' if header.mode & consts.PFS_MODE_64BIT_INODES else 'no'}")
                print(f"  Encrypted:           {'yes' if header.mode & consts.PFS_MODE_ENCRYPTED else 'no'}")
                print(f"  Case insensitive:    {'yes' if header.mode & consts.PFS_MODE_CASE_INSENSITIVE else 'no'}")
                print(f"Block size:            {header.block_size:,} bytes")
                print(f"Inodes:                {len(inodes):,}")
                print(f"Directories:           {len(dir_inodes):,}")
                print(f"Files:                 {len(file_inodes):,}")
                print(f"Compressed files:      {compressed_count:,}")
                print(f"Files hash-checked:    {checked_files:,}")
                print(f"Data CRC32:            0x{data_crc32:08X}")
                print(f"Manifest SHA256:       {manifest_sha256}")
                print(f"Logical file bytes:    {total_logical:,}")
                print(f"Stored file bytes:     {total_stored:,}")
                print(f"flat_path_table keys:  {len(fpt_map):,}")
                print(f"Warnings:              {len(warnings)}")
                print(f"Errors:                {len(errors)}")
                print("=" * 70)

            if print_tree:
                print("/")
                for line in render_tree(tree, uroot_inode):
                    print(line)

    return errors, warnings, tree, uroot_inode


def add_create_subcommand_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--path", required=True, help="Source app or homebrew folder")
    parser.add_argument("--output", required=True, help="Output image path")

    comp_group = parser.add_mutually_exclusive_group()
    comp_group.add_argument(
        "--compress", action="store_true", default=True, help="Enable per-file compression (default)"
    )
    comp_group.add_argument("--no-compress", action="store_true", help="Disable per-file compression")

    parser.add_argument(
        "--threshold-gain", type=int, default=20, help="Minimum gain percent to keep a file compressed (default: 20)"
    )
    parser.add_argument(
        "--block-size", default="auto", help="PFS block size in bytes, or 'auto' (default: auto=65536)"
    )
    parser.add_argument("--version", choices=["PS4", "PS5"], default="PS4", help="PFS profile version (default: PS4)")
    parser.add_argument(
        "--inode-bits", type=int, choices=[32, 64], default=32, help="Inode width mode bit (32 or 64, default: 32)"
    )

    case_group = parser.add_mutually_exclusive_group()
    case_group.add_argument("--case-sensitive", action="store_true", help="Build a case-sensitive image")
    case_group.add_argument("--case-insensitive", action="store_true", help="Set case-insensitive mode bit (default)")

    parser.add_argument(
        "--cpu-count", type=int, default=0, help="Number of CPU cores to use for compression (0 = all available)"
    )
    parser.add_argument("--compression-level", type=int, default=9, help="Zlib compression level (0-9, default: 9)")
    parser.add_argument("--signed", action="store_true", help="Build a signed PFS image using zero EKPFS/seed")
    parser.add_argument("--verbose", action="store_true", help="Verbose per-file decisions")
    parser.add_argument("--dry-run", action="store_true", help="Scan/layout/report only; do not write image")
    parser.add_argument("--verify", action="store_true", help="Run 'check' after a successful create")


def create_args_to_legacy_argv(args: argparse.Namespace) -> list[str]:
    argv = ["--path", args.path, "--output", args.output]
    if args.no_compress:
        argv.append("--no-compress")
    else:
        argv.append("--compress")
    argv.extend(["--threshold-gain", str(args.threshold_gain)])
    argv.extend(["--block-size", str(args.block_size)])
    argv.extend(["--version", args.version])
    argv.extend(["--inode-bits", str(args.inode_bits)])
    if args.case_sensitive:
        argv.append("--case-sensitive")
    if args.case_insensitive:
        argv.append("--case-insensitive")
    argv.extend(["--cpu-count", str(args.cpu_count)])
    argv.extend(["--compression-level", str(args.compression_level)])
    if args.signed:
        argv.append("--signed")
    if args.verbose:
        argv.append("--verbose")
    if args.dry_run:
        argv.append("--dry-run")
    return argv


def cmd_create(args: argparse.Namespace) -> int:
    source_path = Path(args.path).expanduser().resolve()
    output_path, output_warn = normalize_output_path(args.output)
    output_path = output_path.expanduser().resolve()

    if output_warn:
        print(f"warning: {output_warn}", file=sys.stderr)

    if args.threshold_gain < 0 or args.threshold_gain > 100:
        raise BuildError("--threshold-gain must be within 0..100")

    if isinstance(args.block_size, str) and args.block_size.strip().lower() == "auto":
        block_size = 65536
    else:
        try:
            block_size = int(args.block_size)
        except (TypeError, ValueError) as exc:
            raise BuildError("--block-size must be an integer value or 'auto'") from exc

    if not is_power_of_two(block_size):
        raise BuildError("--block-size must be a power of two")
    if block_size < 0x1000 or block_size > 0x200000:
        raise BuildError("--block-size must be between 4096 and 2097152")

    available_cpu_count = mp.cpu_count()
    if args.cpu_count < 0 or args.cpu_count > available_cpu_count:
        raise BuildError(f"--cpu-count must be within 0..{available_cpu_count}")

    if args.compression_level < 0 or args.compression_level > 9:
        raise BuildError("--compression-level must be within 0..9")

    _title_id, warnings = validate_input(source_path)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)

    compress = not args.no_compress
    case_insensitive = args.case_insensitive or not args.case_sensitive
    pfs_version = consts.PFS_VERSION_PS5 if args.version == "PS5" else consts.PFS_VERSION_PS4

    print_build_parameters(
        source_path,
        output_path,
        block_size,
        pfs_version,
        args.inode_bits,
        case_insensitive,
        args.signed,
        compress,
        args.threshold_gain,
        args.cpu_count,
        args.compression_level,
        args.dry_run,
    )

    if not args.dry_run and not prompt_overwrite(output_path):
        print("Operation cancelled.")
        return 0

    stats = build_pfs(
        source_root=source_path,
        output_path=output_path,
        block_size=block_size,
        pfs_version=pfs_version,
        inode_bits=args.inode_bits,
        case_insensitive=case_insensitive,
        signed=args.signed,
        compress=compress,
        threshold_gain=args.threshold_gain,
        cpu_count=args.cpu_count,
        zlib_level=args.compression_level,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    print_summary(stats)
    if args.dry_run or not args.verify:
        return 0

    print("Running post-create check...")
    errors, warnings, _tree, _uroot = run_image_check(
        output_path,
        source_path,
        print_tree=False,
    )

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    return 1 if errors else 0


def cmd_check(args: argparse.Namespace) -> int:
    image = Path(args.image).expanduser().resolve()
    source = Path(args.source).expanduser().resolve() if args.source else None
    expected_crc32: int | None = None
    if args.expected_crc32:
        crc_text = args.expected_crc32.strip().lower()
        if crc_text.startswith("0x"):
            crc_text = crc_text[2:]
        if len(crc_text) == 0 or len(crc_text) > 8:
            print("error: --expected-crc32 must be a 32-bit hex value", file=sys.stderr)
            return 2
        try:
            expected_crc32 = int(crc_text, 16)
        except ValueError:
            print("error: --expected-crc32 must be hex (example: 7F528D1F or 0x7F528D1F)", file=sys.stderr)
            return 2
        if expected_crc32 < 0 or expected_crc32 > 0xFFFFFFFF:
            print("error: --expected-crc32 out of range", file=sys.stderr)
            return 2

    expected_manifest_sha256: str | None = None
    if args.expected_manifest_sha256:
        digest = args.expected_manifest_sha256.strip().lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            print("error: --expected-manifest-sha256 must be a 64-hex SHA256 digest", file=sys.stderr)
            return 2
        expected_manifest_sha256 = digest

    errors, warnings, _tree, _uroot = run_image_check(
        image,
        source,
        print_tree=args.print_tree,
        expected_crc32=expected_crc32,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    return 1 if errors else 0


def cmd_ls(args: argparse.Namespace) -> int:
    image = Path(args.image).expanduser().resolve()
    errors, _warnings, tree, uroot = run_image_check(
        image,
        source=None,
        print_tree=False,
        emit_report=False,
    )
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        return 1
    print("/")
    for line in render_tree(tree, uroot):
        print(line)
    return 0


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ffpfs", description="PFS create/check/list CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    create_parser = sub.add_parser("create", help="Create .ffpfs image")
    add_create_subcommand_arguments(create_parser)
    create_parser.set_defaults(func=cmd_create)

    check_parser = sub.add_parser("check", aliases=["verify"], help="Validate image structure and contents")
    check_parser.add_argument("--image", required=True, help="Path to .ffpfs image")
    check_parser.add_argument("--source", help="Optional source folder to verify hierarchy and content hashes")
    check_parser.add_argument(
        "--expected-crc32",
        help="Expected cumulative data CRC32 (hex), fails if different",
    )
    check_parser.add_argument(
        "--expected-manifest-sha256",
        help="Expected manifest SHA256 (64 hex chars), fails if different",
    )
    check_parser.add_argument("--print-tree", action="store_true", help="Print file tree in check output")
    check_parser.set_defaults(func=cmd_check)

    ls_parser = sub.add_parser("ls", help="List files/directories as a tree")
    ls_parser.add_argument("--image", required=True, help="Path to .ffpfs image")
    ls_parser.set_defaults(func=cmd_ls)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_cli()
    args = parser.parse_args(argv)
    return int(args.func(args))
