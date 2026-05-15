"""Command-line interface for mkpfs package.

This module provides a clean CLI entry point that calls into the
implementation in src/mkpfs/psf.py. It is kept minimal and focused on
argument parsing and user-facing printing.
"""

import argparse
import multiprocessing as mp
from pathlib import Path

from . import consts
from .logging import error, info, warn
from .pfs import (
    BuildError,
    BuildStats,
    ParsedDirent,
    PFSExtractionResult,
    PFSImageInfo,
    PFSImageInspection,
    build_expected_fpt,
    build_pfs,
    build_tree_from_uroot,
    compose_pfs_mode_with_sign,
    extract_pfs_image,
    human_readable_size,
    inspect_pfs_image,
    parse_image_header,
    parse_image_inodes,
    parse_superroot_and_indexes,
    read_pfs_info,
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
    mode: int = compose_pfs_mode_with_sign(inode_bits, case_insensitive, signed)
    info("" + "=" * 70)
    info("PFS Image Builder - Parameters")
    info("" + "=" * 70)
    info(f"  Source path:       {source_path}")
    info(f"  Output path:       {output_path}")
    ver_label: str = "PS5" if pfs_version == consts.PFS_VERSION_PS5 else "PS4"
    info(f"  Version:           {pfs_version} ({ver_label})")
    fmt: str = globals().get("PFS_MAGIC", "")
    info(f"  Format:            {fmt}")
    info(f"  Block size:        {block_size:,} bytes ({block_size // 1024} KiB)")
    info(f"  Inode width:       {inode_bits}-bit")
    info(
        f"  PFS mode:          0x{mode:04X}  (Bit 0=signed, Bit 1=64-bit inodes, "
        "Bit 2=encrypted, Bit 3=case insensitive)"
    )
    info(f"    Signed:          {'yes' if mode & consts.PFS_MODE_SIGNED else 'no'}")
    info(f"    64-bit inodes:   {'yes' if mode & consts.PFS_MODE_64BIT_INODES else 'no'}")
    info(f"    Encrypted:       {'yes' if mode & consts.PFS_MODE_ENCRYPTED else 'no'}")
    info(f"    Case insensitive: {'yes' if mode & consts.PFS_MODE_CASE_INSENSITIVE else 'no'}")
    info(f"  Compression:       {'enabled' if compress else 'disabled'}")
    if compress:
        info(f"  Threshold gain:    {threshold_gain}%")
        info(f"  CPU cores:         {'all available' if cpu_count == 0 else cpu_count}")
        info(f"  Zlib level:        {zlib_level}")
    info(f"  Dry run:           {'yes' if dry_run else 'no'}")
    info("" + "=" * 70)


def print_summary(stats: BuildStats) -> None:
    info("" + "=" * 70)
    info("Build Summary")
    info("" + "=" * 70)
    info(f"  Input path:              {stats.input_path}")
    info(f"  Output path:             {stats.output_path}")
    info(f"  Total files:             {stats.total_files:,}")
    info(f"  Total uncompressed size: {human_readable_size(stats.uncompressed_total_size)}")
    info(f"  Total stored size:       {human_readable_size(stats.stored_total_size)}")

    if stats.compression_enabled:
        info("\n  Compression Statistics:")
        info(f"    Compressed files:       {stats.compressed_files:,}")
        info(f"    Uncompressed files:     {stats.uncompressed_files:,}")
        info(f"    Actual gain achieved:   {stats.actual_gain_pct:.2f}%")
        info(
            "    Max theoretical gain:   "
            f"{stats.max_possible_gain_pct:.2f}%  "
            f"({human_readable_size(stats.all_compressed_total_size)} if all files compressed)"
        )
    else:
        info("\n  Compression:             disabled")

    aligned_total: int = stats.stored_total_size + stats.block_alignment_waste
    waste_pct: float = (stats.block_alignment_waste / aligned_total * 100.0) if aligned_total > 0 else 0.0
    info("\n  Block Alignment Waste:")
    info(f"    Block size:             {stats.block_size // 1024} KiB ({stats.block_size:,} bytes)")
    info(
        "    Wasted space:           "
        f"{human_readable_size(stats.block_alignment_waste)} "
        f"({waste_pct:.2f}% of file data blocks)"
    )

    info(f"\n  Elapsed time:            {stats.elapsed_seconds:.2f}s")

    if stats.total_files > 0:
        throughput: float = stats.uncompressed_total_size / (stats.elapsed_seconds + 0.001)
        info(f"  Throughput:              {human_readable_size(int(throughput))}/s")

    info("" * 70 + "\n")


def prompt_overwrite(output_path: Path) -> bool:
    """Prompt user if output file exists. Returns True if it should proceed."""
    if not output_path.exists():
        return True

    info(f"Output file already exists: {output_path}")
    while True:
        response = input("Overwrite? [Y/n] ").strip().lower()
        if response in ("y", "yes", ""):
            # Clean up any partial .tmp file if it exists
            tmp_path = Path(str(output_path) + ".tmp")
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            return True
        if response in ("n", "no"):
            return False
        info("Please enter 'y' or 'n'")


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


# Legacy analyzer compatibility removed; use the `analyze` subcommand instead.


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
                info("" + "=" * 70)
                info("PFS Check Report")
                info("" + "=" * 70)
                info(f"Image:                 {image}")
                ver_label: str = "PS5" if header.version == consts.PFS_VERSION_PS5 else "PS4"
                info(f"Version:               {header.version} ({ver_label})")
                info(f"Format:                {header.magic}")
                info(f"Read-only:             {'yes' if header.readonly else 'no'}")
                info(
                    "Mode:                  "
                    f"0x{header.mode:04X}  (Bit 0=signed, Bit 1=64-bit inodes, "
                    "Bit 2=encrypted, Bit 3=case insensitive)"
                )
                info(f"  Signed:              {'yes' if header.mode & consts.PFS_MODE_SIGNED else 'no'}")
                info(f"  64-bit inodes:       {'yes' if header.mode & consts.PFS_MODE_64BIT_INODES else 'no'}")
                info(f"  Encrypted:           {'yes' if header.mode & consts.PFS_MODE_ENCRYPTED else 'no'}")
                info(f"  Case insensitive:    {'yes' if header.mode & consts.PFS_MODE_CASE_INSENSITIVE else 'no'}")
                info(f"Block size:            {header.block_size:,} bytes")
                info(f"Inodes:                {len(inodes):,}")
                info(f"Directories:           {len(dir_inodes):,}")
                info(f"Files:                 {len(file_inodes):,}")
                info(f"Compressed files:      {compressed_count:,}")
                info(f"Files hash-checked:    {checked_files:,}")
                info(f"Data CRC32:            0x{data_crc32:08X}")
                info(f"Manifest SHA256:       {manifest_sha256}")
                info(f"Logical file bytes:    {total_logical:,}")
                info(f"Stored file bytes:     {total_stored:,}")
                info(f"flat_path_table keys:  {len(fpt_map):,}")
                info(f"Warnings:              {len(warnings)}")
                info(f"Errors:                {len(errors)}")
                info("=" * 70)

            if print_tree:
                info("/")
                for line in render_tree(tree, uroot_inode):
                    info(line)

    return errors, warnings, tree, uroot_inode


def cli_mkpfs_add_create_args(parser: argparse.ArgumentParser) -> None:
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
    argv: list[str] = ["--path", args.path, "--output", args.output]
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


def cli_mkpfs_create_run(args: argparse.Namespace) -> int:
    source_path: Path = Path(args.path).expanduser().resolve()
    output_path: Path
    output_warn: str | None
    output_path, output_warn = normalize_output_path(args.output)
    output_path = output_path.expanduser().resolve()

    if output_warn:
        info(output_warn)

    if args.threshold_gain < 0 or args.threshold_gain > 100:
        raise BuildError("--threshold-gain must be within 0..100")

    if isinstance(args.block_size, str) and args.block_size.strip().lower() == "auto":
        block_size: int = 65536
    else:
        try:
            block_size = int(args.block_size)
        except (TypeError, ValueError) as exc:
            raise BuildError("--block-size must be an integer value or 'auto'") from exc

    if not is_power_of_two(block_size):
        raise BuildError("--block-size must be a power of two")
    if block_size < 0x1000 or block_size > 0x200000:
        raise BuildError("--block-size must be between 4096 and 2097152")

    available_cpu_count: int = mp.cpu_count()
    if args.cpu_count < 0 or args.cpu_count > available_cpu_count:
        raise BuildError(f"--cpu-count must be within 0..{available_cpu_count}")

    if args.compression_level < 0 or args.compression_level > 9:
        raise BuildError("--compression-level must be within 0..9")

    _title_id: str | None
    warnings: list[str]
    _title_id, warnings = validate_input(source_path)
    for w in warnings:
        warn(w)

    compress: bool = not args.no_compress
    case_insensitive: bool = args.case_insensitive or not args.case_sensitive
    pfs_version: int = consts.PFS_VERSION_PS5 if args.version == "PS5" else consts.PFS_VERSION_PS4

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
        info("Operation cancelled.")
        return 0

    stats: BuildStats = build_pfs(
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

    info("Running post-create check...")
    errors, warnings, _tree, _uroot = run_image_check(
        output_path,
        source_path,
        print_tree=False,
    )

    for w in warnings:
        warn(w)
    for e in errors:
        error(e)
    return 1 if errors else 0


def cli_mkpfs_check_run(args: argparse.Namespace) -> int:
    image = Path(args.image).expanduser().resolve()
    source = Path(args.source).expanduser().resolve() if args.source else None
    expected_crc32: int | None = None
    if args.expected_crc32:
        crc_text = args.expected_crc32.strip().lower()
        if crc_text.startswith("0x"):
            crc_text = crc_text[2:]
        if len(crc_text) == 0 or len(crc_text) > 8:
            info("--expected-crc32 must be a 32-bit hex value")
            return 2
        try:
            expected_crc32 = int(crc_text, 16)
        except ValueError:
            info("--expected-crc32 must be hex (example: 7F528D1F or 0x7F528D1F)")
            return 2
        if expected_crc32 < 0 or expected_crc32 > 0xFFFFFFFF:
            info("--expected-crc32 out of range")
            return 2

    expected_manifest_sha256: str | None = None
    if args.expected_manifest_sha256:
        digest = args.expected_manifest_sha256.strip().lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            info("--expected-manifest-sha256 must be a 64-hex SHA256 digest")
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
        warn(w)
    for e in errors:
        error(e)
    return 1 if errors else 0


def cli_mkpfs_ls_run(args: argparse.Namespace) -> int:
    image: Path = Path(args.image).expanduser().resolve()
    errors: list[str]
    _warnings: list[str]
    tree: dict[int, list[ParsedDirent]]
    uroot: int
    errors, _warnings, tree, uroot = run_image_check(
        image,
        source=None,
        print_tree=False,
        emit_report=False,
    )
    if errors:
        for e in errors:
            error(e)
        return 1
    info("/")
    for line in render_tree(tree, uroot):
        info(line)
    return 0


def cli_mkpfs_info_run(args: argparse.Namespace) -> int:
    """Show lightweight PFS image metadata.

    Args:
        args: Parsed CLI arguments with `image` attribute.
    """
    image: Path = Path(args.image).expanduser().resolve()
    info_result: PFSImageInfo = read_pfs_info(image)

    # Print header-level metadata and any warnings/errors
    info("=" * 70)
    info("PFS Image Info")
    info("=" * 70)
    info(f"Image:       {image}")
    info(f"Size (bytes):{info_result.size_bytes}")
    if info_result.header is not None:
        info(f"Version:     {info_result.version_label} ({info_result.header.version})")
        info(f"Block size:  {info_result.header.block_size}")
        info(f"Magic:       0x{info_result.header.magic:016X}")

    for w in info_result.warnings:
        warn(w)
    for e in info_result.errors:
        error(e)

    return 1 if info_result.errors else 0


def cli_mkpfs_analyze_run(args: argparse.Namespace) -> int:
    """Inspect a PFS image and emit a detailed report.

    Args:
        args: Parsed CLI arguments (image, source, expected hashes, print-tree).
    """
    image: Path = Path(args.image).expanduser().resolve()
    source: Path | None = Path(args.source).expanduser().resolve() if getattr(args, "source", None) else None

    # Parse optional expected CRC32
    expected_crc32: int | None = None
    if getattr(args, "expected_crc32", None):
        crc_text: str = args.expected_crc32.strip().lower()
        if crc_text.startswith("0x"):
            crc_text = crc_text[2:]
        try:
            expected_crc32 = int(crc_text, 16)
        except ValueError:
            info("--expected-crc32 must be hex (example: 7F528D1F or 0x7F528D1F)")
            return 2

    # Parse optional expected manifest digest
    expected_manifest_sha256: str | None = None
    if getattr(args, "expected_manifest_sha256", None):
        digest: str = args.expected_manifest_sha256.strip().lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            info("--expected-manifest-sha256 must be a 64-hex SHA256 digest")
            return 2
        expected_manifest_sha256 = digest

    # Run library inspection
    inspection: PFSImageInspection = inspect_pfs_image(
        image=image,
        source=source,
        expected_crc32=expected_crc32,
        expected_manifest_sha256=expected_manifest_sha256,
    )

    # Emit report
    info("=" * 70)
    info("PFS Image Inspection")
    info("=" * 70)
    info(f"Image:    {image}")
    if inspection.header is not None:
        ver_label: str = "PS5" if inspection.header.version == consts.PFS_VERSION_PS5 else "PS4"
        info(f"Version:  {inspection.header.version} ({ver_label})")
        info(f"Block:    {inspection.header.block_size}")

    info(f"Warnings: {len(inspection.warnings)}")
    info(f"Errors:   {len(inspection.errors)}")

    for w in inspection.warnings:
        info(w)
    for e in inspection.errors:
        info(e)

    if getattr(args, "print_tree", False) and inspection.has_tree:
        info("/")
        for line in render_tree(inspection.dirents_by_inode, inspection.uroot_inode):
            info(line)

    return 1 if inspection.errors else 0


def cli_mkpfs_extract_run(args: argparse.Namespace) -> int:
    """Extract all files from a PFS image into a directory.

    Args:
        args: Parsed CLI arguments with `image`, `output`, and optional `overwrite`.
    """
    image: Path = Path(args.image).expanduser().resolve()
    output_path: Path = Path(args.output).expanduser().resolve()

    if output_path.exists() and not args.overwrite:
        info(f"output path {output_path} exists (use --overwrite to force)")
        return 2

    # Perform extraction via library API
    result: PFSExtractionResult = extract_pfs_image(image=image, output_path=output_path, progress=None)

    for w in result.warnings:
        info(w)
    for e in result.errors:
        info(e)

    if result.errors:
        return 1

    info("Extraction complete:")
    info(f"  Output:       {result.output_path}")
    info(f"  Files written: {result.files_written}")
    info(f"  Dirs created:  {result.directories_created}")
    info(f"  Bytes written: {result.bytes_written}")
    return 0


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ffpfs", description="PFS create/check/list CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    create_parser = sub.add_parser("create", help="Create .ffpfs image")
    cli_mkpfs_add_create_args(create_parser)
    create_parser.set_defaults(func=cli_mkpfs_create_run)

    check_parser = sub.add_parser("check", help="Validate image structure and contents")
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
    check_parser.set_defaults(func=cli_mkpfs_check_run)

    ls_parser = sub.add_parser("ls", help="List files/directories as a tree")
    ls_parser.add_argument("--image", required=True, help="Path to .ffpfs image")
    ls_parser.set_defaults(func=cli_mkpfs_ls_run)

    info_parser = sub.add_parser("info", help="Show lightweight image metadata")
    info_parser.add_argument("--image", required=True, help="Path to .ffpfs image")
    info_parser.set_defaults(func=cli_mkpfs_info_run)

    analyze_parser = sub.add_parser("analyze", help="Inspect image structure and contents")
    analyze_parser.add_argument("--image", required=True, help="Path to .ffpfs image")
    analyze_parser.add_argument("--source", help="Optional source folder to verify hierarchy and content hashes")
    analyze_parser.add_argument(
        "--expected-crc32",
        help="Expected cumulative data CRC32 (hex), fails if different",
    )
    analyze_parser.add_argument(
        "--expected-manifest-sha256",
        help="Expected manifest SHA256 (64 hex chars), fails if different",
    )
    analyze_parser.add_argument("--print-tree", action="store_true", help="Print file tree in analysis output")
    analyze_parser.set_defaults(func=cli_mkpfs_analyze_run)

    extract_parser = sub.add_parser("extract", help="Extract files from image to directory")
    extract_parser.add_argument("--image", required=True, help="Path to .ffpfs image")
    extract_parser.add_argument("--output", required=True, help="Destination directory for extraction")
    extract_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output path")
    extract_parser.set_defaults(func=cli_mkpfs_extract_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_cli()
    args = parser.parse_args(argv)
    return int(args.func(args))


# Public canonical exports
cli_mkpfs_build_parser = build_cli
cli_mkpfs = main
