# MkPFS Legacy Parity & Pre-Release Hardening Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. Update `current-plan/progress.html` after each task.

**Goal:** Prove and enforce byte-perfect 1-to-1 behavioral parity between `mkpfs` and the authoritative legacy implementation in `legacy/ffpfs.py` across every current CLI command (create, check, verify, ls, info, analyze, extract), including the full signed-image path, while fixing all code quality issues discovered along the way.

**Architecture:** The new code is already structured correctly — `mkpfs/cli.py` owns CLI wiring, `mkpfs/pfs.py` owns all PFS format logic, `mkpfs/consts.py`/`utils.py`/`pbar.py` own shared helpers. No module reorganisation is needed. The work is an audit-and-fix pass that proceeds function-by-function from constants through builder through reader/verifier, with side-by-side runtime comparison used to confirm every critical path.

**Tech Stack:** Python 3.11, uv, pytest, ruff, zlib, hmac/hashlib (sha256), struct, multiprocessing, legacy/ffpfs.py as oracle

---

## Key: legacy/ffpfs.py vs mkpfs mapping

| Legacy symbol | New location | Notes |
|---|---|---|
| `PFS_MAGIC`, `PFS_VERSION_*`, `PFS_MODE_*` | `mkpfs/consts.py` | Must be identical values |
| `INODE_MODE_*`, `INODE_FLAG_*`, `DIRENT_TYPE_*` | `mkpfs/consts.py` | Must be identical values |
| `INODE_D32_SIZE=0xA8`, `INODE_S32_SIZE=0x2C8`, `INODE_S64_SIZE=0x310` | `mkpfs/consts.py` | `INODE_S64_SIZE` may be missing |
| `SIG_ENTRY_SIZE=36`, `SIG_SIZE=32` | `mkpfs/consts.py` | Must match |
| `ZERO_EKPFS`, `ZERO_PFS_SEED` | `mkpfs/consts.py` or `pfs.py` | Must be present |
| `HEADER_DIGEST_OFFSET=0x380`, `HEADER_DIGEST_SIZE=0x5A0` | `mkpfs/consts.py` or `pfs.py` | Critical for signed header verification |
| `INODE_FLAG_SIGNED_EXTRA=0x4 \| 0x8` | `mkpfs/consts.py` | Must be present |
| `INT32_MAX`, `UINT32_MAX` | `mkpfs/consts.py` | `validate_d32_ranges` uses both |
| `validate_d32_ranges` | `mkpfs/pfs.py` | Legacy uses `UINT32_MAX` for inode number & flags — new uses `INT32_MAX`. **Bug: off-by-one in allowed range** |
| `pfs_gen_crypto_key`, `pfs_gen_sign_key`, `hmac_sha256` | `mkpfs/pfs.py` | Identical |
| `build_inode_block_sig_s64` | `mkpfs/pfs.py` | Identical |
| `Dirent.to_bytes` | `mkpfs/pfs.py` | Identical |
| `Inode.to_bytes` / `to_bytes_signed32` | `mkpfs/pfs.py` | Identical |
| `scan_source_tree` | `mkpfs/pfs.py` | Identical |
| `fpt_hash` / `make_fpt_and_collision_blob` | `mkpfs/pfs.py` | Identical |
| `compute_file_storage` | `mkpfs/pfs.py` | Identical |
| `build_pfs` | `mkpfs/pfs.py` | **Critical: inode flags for signed (`INODE_FLAG_SIGNED_EXTRA`), collision renumber, `ndblock += 2` — must verify** |
| `parse_image_header` | `mkpfs/pfs.py` | **`readonly` field read from `0x1A` — must verify new reads same offset** |
| `parse_image_inode` / `parse_image_inodes` | `mkpfs/pfs.py` | Must verify D32/S32 packing offsets match |
| `parse_sig_record_block` | `mkpfs/pfs.py` | Must verify present |
| `block_hmac_without_slot` | `mkpfs/pfs.py` | Must verify present and zeroing logic identical |
| `verify_signed_image_signatures` | `mkpfs/pfs.py` | Most complex verification path — must verify field-by-field |
| `parse_superroot_and_indexes` | `mkpfs/pfs.py` | Must verify |
| `build_tree_from_uroot` | `mkpfs/pfs.py` | Must verify |
| `verify_file_payload_hashes` | `mkpfs/pfs.py` | Must verify CRC32+SHA256 manifest logic |
| `validate_fpt_maps` | `mkpfs/pfs.py` | Must verify |
| `validate_ps5_checklist` | `mkpfs/pfs.py` | Must verify |
| `validate_source_match` | `mkpfs/pfs.py` | Must verify |
| `run_image_check` | `mkpfs/cli.py` | legacy uses `print()` to stdout; new uses `info()` — **output channel difference** |
| `cmd_create`/`cmd_check`/`cmd_ls` | `mkpfs/cli.py` | legacy `check` has alias `verify` in `build_cli`; new doesn't expose it |
| `build_cli` (legacy) | `cli_mkpfs_main_parsers` (new) | Legacy has `verify` alias; new omits `info`/`analyze`/`extract` from legacy entirely |

## Known divergences to investigate

1. **`validate_d32_ranges`**: legacy uses `UINT32_MAX` for inode number/flags/blocks; new uses `INT32_MAX` for flags/blocks — potential parity issue for large values.
2. **`HEADER_DIGEST_OFFSET` / `HEADER_DIGEST_SIZE`**: these constants may not be in `mkpfs/consts.py` — needed for signed header verification.
3. **`INODE_FLAG_SIGNED_EXTRA = 0x4 | 0x8`**: may be missing from `mkpfs/consts.py`.
4. **`ZERO_EKPFS` / `ZERO_PFS_SEED`**: may be inline in `pfs.py` rather than named constants.
5. **`ndblock += 2` in signed build_pfs**: this skips 2 blocks for the superroot directory + uroot directory before assigning signed inodes — must verify present in new build_pfs.
6. **`readonly` at header offset `0x1A`**: legacy reads from offset `0x1A`, not the mode flags — must verify new parser reads from same offset.
7. **`check` alias `verify`**: legacy `build_cli` registers `verify` as an alias for `check`; new `cli_mkpfs_main_parsers` omits this alias.
8. **Output channel**: legacy `run_image_check` prints to stdout with `print()`; new version routes through `info()` logging. Semantic output is identical but channel differs — document this intentional divergence.
9. **`parse_image_header`: `nblock` field**: legacy reads `nblock` from `0x28` but the field comment calls it "nblock start" — verify new reads same offset and uses same semantics.
10. **`block_hmac_without_slot`**: in legacy verification of inode *table* blocks, `signed=False` is passed, meaning no zeroing is done. Verify new implementation does the same.

---

## File structure (files to create or modify)

| File | Action | Responsibility |
|---|---|---|
| `mkpfs/consts.py` | Modify | Add any missing constants identified above |
| `mkpfs/pfs.py` | Modify | Fix any logic divergences found in audit |
| `mkpfs/cli.py` | Modify | Add `verify` alias for `check`; fix any divergences |
| `tests/mkpfs/test_parity_consts.py` | Create | Verify all constants match legacy values |
| `tests/mkpfs/test_parity_structs.py` | Create | Verify Dirent/Inode serialization sizes and byte layout |
| `tests/mkpfs/test_parity_fpt.py` | Create | Verify fpt_hash and collision blob byte output |
| `tests/mkpfs/test_parity_builder.py` | Create | Side-by-side build_pfs parity (calls legacy + new on same input) |
| `tests/mkpfs/test_parity_reader.py` | Create | Side-by-side parse/check/ls parity |
| `tests/mkpfs/test_parity_signed.py` | Create | Signed image build + verify parity |
| `tests/mkpfs/fixtures/__init__.py` | Create | Empty package marker |
| `tests/mkpfs/fixtures/helpers.py` | Create | Shared fixture builders (minimal app tree, collision names, etc.) |
| `current-plan/progress.html` | Create | Fancy HTML dashboard — update status after each task |

---

## Task 1: Audit and fix constants parity

**Files:**
- Read: `legacy/ffpfs.py` (lines 27–79)
- Read: `mkpfs/consts.py`
- Modify: `mkpfs/consts.py`
- Create: `tests/mkpfs/test_parity_consts.py`

- [x] **Step 1: Read legacy constants block**

  Open `legacy/ffpfs.py` lines 27–79. The complete constant set is:
  ```
  PFS_MAGIC = 20130315
  PFS_VERSION_PS4 = 1, PFS_VERSION_PS5 = 2
  PFS_MODE_SIGNED = 0x1, PFS_MODE_64BIT_INODES = 0x2, PFS_MODE_ENCRYPTED = 0x4, PFS_MODE_CASE_INSENSITIVE = 0x8
  INODE_MODE_O_READ = 0x001 ... INODE_MODE_DIR = 0x4000, INODE_MODE_FILE = 0x8000
  INODE_MODE_ANY_WRITE = 0x092, INODE_RX_ONLY = 0x149
  INODE_FLAG_COMPRESSED = 0x1, INODE_FLAG_READONLY = 0x10, INODE_FLAG_INTERNAL = 0x20000
  INODE_FLAG_SIGNED_EXTRA = 0x4 | 0x8 = 0xC
  DIRENT_TYPE_FILE = 2, DIRENT_TYPE_DIRECTORY = 3, DIRENT_TYPE_DOT = 4, DIRENT_TYPE_DOTDOT = 5
  INODE_D32_SIZE = 0xA8, INODE_S32_SIZE = 0x2C8, INODE_S64_SIZE = 0x310
  MAX_DIRECT_BLOCKS = 12, MAX_INDIRECT_BLOCKS = 5
  SIG_ENTRY_SIZE = 36, SIG_SIZE = 32
  UINT32_MAX = 0xFFFFFFFF, INT32_MAX = 0x7FFFFFFF
  INODE_FLAG_SIGNED_EXTRA = 0xC
  ZERO_EKPFS = b"\x00" * 32, ZERO_PFS_SEED = b"\x00" * 16
  HEADER_DIGEST_OFFSET = 0x380, HEADER_DIGEST_SIZE = 0x5A0
  ```

- [x] **Step 2: Read current mkpfs/consts.py**

  Run: `source .venv/bin/activate && python -c "import mkpfs.consts as c; print(dir(c))"`
  Note which of the above constants are missing or have wrong values.

- [x] **Step 3: Write the failing test**

  Create `tests/mkpfs/test_parity_consts.py`:
  ```python
  """Verify all mkpfs constants match legacy/ffpfs.py values exactly."""
  import mkpfs.consts as c


  def test_pfs_magic():
      assert c.PFS_MAGIC == 20130315


  def test_pfs_versions():
      assert c.PFS_VERSION_PS4 == 1
      assert c.PFS_VERSION_PS5 == 2


  def test_pfs_mode_flags():
      assert c.PFS_MODE_SIGNED == 0x1
      assert c.PFS_MODE_64BIT_INODES == 0x2
      assert c.PFS_MODE_ENCRYPTED == 0x4
      assert c.PFS_MODE_CASE_INSENSITIVE == 0x8


  def test_inode_mode_bits():
      assert c.INODE_MODE_O_READ == 0x001
      assert c.INODE_MODE_O_WRITE == 0x002
      assert c.INODE_MODE_O_EXEC == 0x004
      assert c.INODE_MODE_G_READ == 0x008
      assert c.INODE_MODE_G_WRITE == 0x010
      assert c.INODE_MODE_G_EXEC == 0x020
      assert c.INODE_MODE_U_READ == 0x040
      assert c.INODE_MODE_U_WRITE == 0x080
      assert c.INODE_MODE_U_EXEC == 0x100
      assert c.INODE_MODE_DIR == 0x4000
      assert c.INODE_MODE_FILE == 0x8000
      assert c.INODE_MODE_ANY_WRITE == (0x002 | 0x010 | 0x080)
      assert c.INODE_RX_ONLY == (0x001 | 0x004 | 0x008 | 0x020 | 0x040 | 0x100)


  def test_inode_flags():
      assert c.INODE_FLAG_COMPRESSED == 0x1
      assert c.INODE_FLAG_READONLY == 0x10
      assert c.INODE_FLAG_INTERNAL == 0x20000
      assert c.INODE_FLAG_SIGNED_EXTRA == 0xC  # 0x4 | 0x8


  def test_dirent_types():
      assert c.DIRENT_TYPE_FILE == 2
      assert c.DIRENT_TYPE_DIRECTORY == 3
      assert c.DIRENT_TYPE_DOT == 4
      assert c.DIRENT_TYPE_DOTDOT == 5


  def test_inode_sizes():
      assert c.INODE_D32_SIZE == 0xA8   # 168 bytes
      assert c.INODE_S32_SIZE == 0x2C8  # 712 bytes
      assert c.INODE_S64_SIZE == 0x310  # 784 bytes


  def test_pointer_counts():
      assert c.MAX_DIRECT_BLOCKS == 12
      assert c.MAX_INDIRECT_BLOCKS == 5


  def test_sig_sizes():
      assert c.SIG_SIZE == 32
      assert c.SIG_ENTRY_SIZE == 36  # SIG_SIZE + 4 byte block pointer


  def test_integer_limits():
      assert c.UINT32_MAX == 0xFFFFFFFF
      assert c.INT32_MAX == 0x7FFFFFFF


  def test_zero_key_constants():
      assert c.ZERO_EKPFS == b"\x00" * 32
      assert c.ZERO_PFS_SEED == b"\x00" * 16


  def test_header_digest_offsets():
      assert c.HEADER_DIGEST_OFFSET == 0x380
      assert c.HEADER_DIGEST_SIZE == 0x5A0
  ```

- [x] **Step 4: Run test to see what fails**

  ```bash
  source .venv/bin/activate
  uv run --frozen pytest tests/mkpfs/test_parity_consts.py -v
  ```
  Expected: some tests FAIL (missing constants).

- [x] **Step 5: Add missing constants to mkpfs/consts.py**

  Open `mkpfs/consts.py` and add every missing constant. Do not remove existing ones. Each new constant needs a one-line comment referencing the legacy source, for example:
  ```python
  # Flags set on inodes in signed images (legacy/ffpfs.py:INODE_FLAG_SIGNED_EXTRA)
  INODE_FLAG_SIGNED_EXTRA: int = 0x4 | 0x8   # = 0xC

  # Zero master key and seed used when building/verifying signed images with zero credentials
  ZERO_EKPFS: bytes = b"\x00" * 32
  ZERO_PFS_SEED: bytes = b"\x00" * 16

  # Header region covered by the signed-image digest (legacy/ffpfs.py:HEADER_DIGEST_OFFSET)
  HEADER_DIGEST_OFFSET: int = 0x380
  HEADER_DIGEST_SIZE: int = 0x5A0
  ```

- [x] **Step 6: Run test to verify all pass**

  ```bash
  uv run --frozen pytest tests/mkpfs/test_parity_consts.py -v
  ```
  Expected: ALL PASS.

- [x] **Step 7: Run full test suite to confirm no regression**

  ```bash
  ./run-tests.sh
  ```
  Expected: all previously passing tests still pass.

- [x] **Step 8: Commit**

  ```bash
  git add mkpfs/consts.py tests/mkpfs/test_parity_consts.py
  git commit -m "test(parity): add constant parity tests; fix missing consts vs legacy/ffpfs.py"
  ```

---

## Task 2: Audit and fix validate_d32_ranges

**Files:**
- Read: `legacy/ffpfs.py` lines 91–115
- Modify: `mkpfs/pfs.py` (function `validate_d32_ranges`)
- Modify: `tests/mkpfs/test_parity_consts.py` or create a new focused test

The legacy code uses `UINT32_MAX` for `inode.number`, `inode.flags`, and `inode.blocks`. The current new code uses `INT32_MAX` for flags and blocks — this allows values like `INODE_FLAG_INTERNAL = 0x20000` but would reject `INODE_FLAG_READONLY = 0x10` combined with other flags in large images.

- [x] **Step 1: Write failing test**

  Add to `tests/mkpfs/test_parity_consts.py` or create `tests/mkpfs/test_parity_validate.py`:
  ```python
  """Verify validate_d32_ranges matches legacy/ffpfs.py behaviour."""
  import pytest
  from mkpfs.pfs import Inode, validate_d32_ranges
  import mkpfs.consts as c


  def _make_inode(number: int = 0, mode: int = 0, nlink: int = 1,
                  flags: int = 0, blocks: int = 1) -> Inode:
      return Inode(number=number, mode=mode, nlink=nlink, flags=flags,
                   size=0, size_compressed=0, blocks=blocks)


  def test_inode_number_at_uint32_max_passes():
      # Legacy: 0 <= ino.number <= UINT32_MAX
      ino = _make_inode(number=c.UINT32_MAX)
      validate_d32_ranges([ino], final_ndblock=0)  # must not raise


  def test_inode_number_above_uint32_max_raises():
      ino = _make_inode(number=c.UINT32_MAX + 1)
      with pytest.raises(Exception):
          validate_d32_ranges([ino], final_ndblock=0)


  def test_inode_flags_at_uint32_max_passes():
      # Legacy: 0 <= ino.flags <= UINT32_MAX
      ino = _make_inode(flags=c.UINT32_MAX)
      validate_d32_ranges([ino], final_ndblock=0)  # must not raise


  def test_inode_blocks_at_uint32_max_passes():
      # Legacy: 0 <= ino.blocks <= UINT32_MAX
      ino = _make_inode(blocks=c.UINT32_MAX)
      validate_d32_ranges([ino], final_ndblock=0)  # must not raise


  def test_final_ndblock_above_int32_max_raises():
      ino = _make_inode()
      with pytest.raises(Exception):
          validate_d32_ranges([ino], final_ndblock=c.INT32_MAX + 1)
  ```

- [x] **Step 2: Run to see what fails**

  ```bash
  uv run --frozen pytest tests/mkpfs/test_parity_validate.py -v
  ```

- [x] **Step 3: Fix validate_d32_ranges in mkpfs/pfs.py**

  Change the upper bound checks for `ino.number`, `ino.flags`, and `ino.blocks` to use `consts.UINT32_MAX` (matching legacy), while keeping `final_ndblock` capped at `consts.INT32_MAX` (unchanged). Also update the docstring to state the ranges explicitly and cite the legacy source.

  ```python
  def validate_d32_ranges(inodes: list[Inode], final_ndblock: int) -> None:
      """Validate values that will be serialized into 32-bit inode structures.

      Matches legacy/ffpfs.py:validate_d32_ranges exactly:
      - inode.number, .flags, .blocks must be in [0, UINT32_MAX]
      - inode.mode, .nlink must be in [0, 0xFFFF]
      - final_ndblock and all db/ib pointers must not exceed INT32_MAX
        (they are stored as signed int32 on disk, -1 is the sentinel)

      Args:
          inodes: List of Inode objects to validate.
          final_ndblock: The final data block index after layout assignment.

      Raises:
          BuildError: When a value is out of the supported range.
      """
      if final_ndblock > consts.INT32_MAX:
          raise BuildError(
              f"Image requires block index {final_ndblock}, exceeds D32 pointer limit {consts.INT32_MAX}"
          )

      for ino in inodes:
          if not (0 <= ino.number <= consts.UINT32_MAX):
              raise BuildError(f"Inode number {ino.number} out of uint32 range")
          if not (0 <= ino.mode <= 0xFFFF):
              raise BuildError(f"Inode mode {ino.mode} out of uint16 range")
          if not (0 <= ino.nlink <= 0xFFFF):
              raise BuildError(f"Inode nlink {ino.nlink} out of uint16 range")
          if not (0 <= ino.flags <= consts.UINT32_MAX):
              raise BuildError(f"Inode flags {ino.flags} out of uint32 range")
          if not (0 <= ino.blocks <= consts.UINT32_MAX):
              raise BuildError(f"Inode blocks {ino.blocks} out of uint32 range")

          for ptr in ino.db:
              if not (-1 <= ptr <= consts.INT32_MAX):
                  raise BuildError(f"Direct block pointer {ptr} out of int32 range")
          for ptr in ino.ib:
              if not (-1 <= ptr <= consts.INT32_MAX):
                  raise BuildError(f"Indirect block pointer {ptr} out of int32 range")
  ```

- [x] **Step 4: Run test to verify it passes**

  ```bash
  uv run --frozen pytest tests/mkpfs/test_parity_validate.py -v
  ./run-tests.sh
  ```

- [x] **Step 5: Commit**

  ```bash
  git add mkpfs/pfs.py tests/mkpfs/test_parity_validate.py
  git commit -m "fix(parity): validate_d32_ranges uses UINT32_MAX for number/flags/blocks, matching legacy"
  ```

---

## Task 3: Audit Dirent and Inode serialization byte layout

**Files:**
- Read: `legacy/ffpfs.py` lines 278–358
- Modify/verify: `mkpfs/pfs.py` (`Dirent.to_bytes`, `Inode.to_bytes`, `Inode.to_bytes_signed32`)
- Create: `tests/mkpfs/test_parity_structs.py`

- [x] **Step 1: Write serialization parity tests**

  Create `tests/mkpfs/test_parity_structs.py`:
  ```python
  """Verify Dirent and Inode serialization matches legacy/ffpfs.py byte-for-byte."""
  import struct
  import mkpfs.consts as c
  from mkpfs.pfs import Dirent, Inode


  def test_dirent_to_bytes_known_vector():
      # Encode a file dirent for inode 5, name "eboot.bin" (9 chars)
      # name_length=9, ent_size = (9+17=26, padded to 32) -> 32
      d = Dirent(inode_number=5, type_code=c.DIRENT_TYPE_FILE, name="eboot.bin")
      assert d.name_length == 9
      assert d.ent_size == 32  # (9+17=26) -> round up to next 8 -> 32
      b = d.to_bytes()
      assert len(b) == 32
      ino_num, type_code, name_len, ent_sz = struct.unpack_from("<Iiii", b, 0)
      assert ino_num == 5
      assert type_code == c.DIRENT_TYPE_FILE
      assert name_len == 9
      assert ent_sz == 32
      assert b[16:25] == b"eboot.bin"
      assert b[25:32] == b"\x00" * 7


  def test_dirent_dot():
      d = Dirent(inode_number=2, type_code=c.DIRENT_TYPE_DOT, name=".")
      # name_length=1, ent_size = (1+17=18) -> round up to 24
      assert d.ent_size == 24
      b = d.to_bytes()
      assert len(b) == 24


  def test_dirent_dotdot():
      d = Dirent(inode_number=0, type_code=c.DIRENT_TYPE_DOTDOT, name="..")
      # name_length=2, ent_size = (2+17=19) -> round up to 24
      assert d.ent_size == 24
      b = d.to_bytes()
      assert len(b) == 24


  def test_inode_d32_size():
      ino = Inode(number=1, mode=0x81A9, nlink=1, flags=c.INODE_FLAG_READONLY,
                  size=1024, size_compressed=1024, blocks=1)
      b = ino.to_bytes()
      assert len(b) == c.INODE_D32_SIZE  # 0xA8 = 168


  def test_inode_d32_field_layout():
      # Verify field positions match legacy parse_image_inode offsets
      # mode at 0x00, nlink at 0x02, flags at 0x04
      # size at 0x08, size_compressed at 0x10
      # blocks at 0x60
      # db[0..11] at 0x64, ib[0..4] at 0x94
      ino = Inode(number=7, mode=0x8000, nlink=3, flags=0x10,
                  size=512, size_compressed=512, blocks=1)
      ino.db[0] = 42
      ino.ib[0] = 99
      b = ino.to_bytes()
      assert struct.unpack_from("<H", b, 0x00)[0] == 0x8000   # mode
      assert struct.unpack_from("<H", b, 0x02)[0] == 3         # nlink
      assert struct.unpack_from("<I", b, 0x04)[0] == 0x10      # flags
      assert struct.unpack_from("<q", b, 0x08)[0] == 512       # size
      assert struct.unpack_from("<q", b, 0x10)[0] == 512       # size_compressed
      assert struct.unpack_from("<I", b, 0x60)[0] == 1         # blocks
      assert struct.unpack_from("<i", b, 0x64)[0] == 42        # db[0]
      assert struct.unpack_from("<i", b, 0x64 + 12 * 4)[0] == 99  # ib[0] at 0x94


  def test_inode_s32_size():
      ino = Inode(number=1, mode=0x81A9, nlink=1, flags=0,
                  size=0, size_compressed=0, blocks=1)
      b = ino.to_bytes_signed32()
      assert len(b) == c.INODE_S32_SIZE  # 0x2C8 = 712


  def test_inode_s32_db_layout():
      # In S32 layout: each db entry is 32-byte sig + 4-byte block pointer
      # db[0] starts at 0x64: sig at 0x64..0x83, block at 0x84
      ino = Inode(number=1, mode=0x8000, nlink=1, flags=0,
                  size=0, size_compressed=0, blocks=1)
      ino.db[0] = 55
      b = ino.to_bytes_signed32()
      # sig at 0x64 (32 bytes of zeros)
      assert b[0x64:0x64 + 32] == b"\x00" * 32
      # block pointer at 0x64 + 32 = 0x84
      assert struct.unpack_from("<i", b, 0x84)[0] == 55
  ```

- [x] **Step 2: Run tests**

  ```bash
  uv run --frozen pytest tests/mkpfs/test_parity_structs.py -v
  ```
  Expected: all PASS (no changes needed if layout matches). Fix any failures in `mkpfs/pfs.py`.

- [x] **Step 3: Commit**

  ```bash
  git add tests/mkpfs/test_parity_structs.py
  git commit -m "test(parity): add Dirent and Inode byte-layout parity tests vs legacy/ffpfs.py"
  ```

---

## Task 4: Audit and fix parse_image_header field offsets

**Files:**
- Read: `legacy/ffpfs.py` lines 1615–1637
- Modify/verify: `mkpfs/pfs.py` (`parse_image_header`)
- Add tests to `tests/mkpfs/test_parity_structs.py`

Legacy reads:
```
version, magic   at 0x00 (two q / 8 bytes each)
readonly         at 0x1A (single B, not from mode flags)
mode             at 0x1C (H)
block_size       at 0x20 (I)
nblock           at 0x28 (q)
dinode_count     at 0x30 (q)
ndblock          at 0x38 (q)
dinode_block_count at 0x40 (q)
seed             at 0x370:0x380 (16 bytes)
```

- [x] **Step 1: Write header parsing test**

  Add to `tests/mkpfs/test_parity_structs.py`:
  ```python
  import io
  from mkpfs.pfs import parse_image_header


  def test_parse_image_header_field_offsets():
      # Build a minimal 0x400-byte header blob with known values
      hdr = bytearray(0x400)
      struct.pack_into("<qq", hdr, 0x00, 1, 20130315)   # version=1, magic
      struct.pack_into("<B", hdr, 0x1A, 1)              # readonly=1
      struct.pack_into("<H", hdr, 0x1C, 0x8)            # mode=case-insensitive
      struct.pack_into("<I", hdr, 0x20, 65536)           # block_size
      struct.pack_into("<q", hdr, 0x28, 100)             # nblock
      struct.pack_into("<q", hdr, 0x30, 50)              # dinode_count
      struct.pack_into("<q", hdr, 0x38, 200)             # ndblock
      struct.pack_into("<q", hdr, 0x40, 2)               # dinode_block_count
      seed_val = bytes(range(16))
      hdr[0x370:0x380] = seed_val

      fh = io.BytesIO(bytes(hdr))
      h = parse_image_header(fh)
      assert h.version == 1
      assert h.magic == 20130315
      assert h.readonly == 1
      assert h.mode == 0x8
      assert h.block_size == 65536
      assert h.nblock == 100
      assert h.dinode_count == 50
      assert h.ndblock == 200
      assert h.dinode_block_count == 2
      assert h.seed == seed_val
  ```

- [x] **Step 2: Run test**

  ```bash
  uv run --frozen pytest tests/mkpfs/test_parity_structs.py::test_parse_image_header_field_offsets -v
  ```
  Fix any offset mismatches found in `mkpfs/pfs.py:parse_image_header`.

- [x] **Step 3: Commit**

  ```bash
  git add mkpfs/pfs.py tests/mkpfs/test_parity_structs.py
  git commit -m "test(parity): add parse_image_header offset test; fix any field-offset divergence"
  ```

---

## Task 5: Audit and fix fpt_hash and collision blob

**Files:**
- Read: `legacy/ffpfs.py` lines 518–585
- Verify/fix: `mkpfs/pfs.py` (`fpt_hash`, `make_fpt_and_collision_blob`)
- Create: `tests/mkpfs/test_parity_fpt.py`

- [x] **Step 1: Write FPT parity tests**

  Create `tests/mkpfs/test_parity_fpt.py`:
  ```python
  """Verify fpt_hash and make_fpt_and_collision_blob match legacy/ffpfs.py."""
  import struct
  import mkpfs.consts as c
  from mkpfs.pfs import fpt_hash, make_fpt_and_collision_blob, DirNode, FileNode, Inode
  from pathlib import Path


  def test_fpt_hash_case_insensitive_known():
      # Hash of "/eboot.bin" case-insensitive must match legacy algorithm
      # h = sum of (ord(upper(c)) + 31*h) & 0xFFFFFFFF
      name = "/eboot.bin"
      expected: int = 0
      for ch in name:
          expected = (ord(ch.upper()) + 31 * expected) & 0xFFFFFFFF
      assert fpt_hash(name, case_insensitive=True) == expected


  def test_fpt_hash_case_sensitive():
      name = "/eboot.bin"
      expected: int = 0
      for ch in name:
          expected = (ord(ch) + 31 * expected) & 0xFFFFFFFF
      assert fpt_hash(name, case_insensitive=False) == expected


  def test_fpt_hash_differs_by_case_when_case_sensitive():
      assert fpt_hash("/ABC", case_insensitive=False) != fpt_hash("/abc", case_insensitive=False)


  def test_fpt_hash_same_by_case_when_case_insensitive():
      assert fpt_hash("/ABC", case_insensitive=True) == fpt_hash("/abc", case_insensitive=True)


  def _make_simple_inode(number: int) -> Inode:
      return Inode(number=number, mode=c.INODE_MODE_FILE | c.INODE_RX_ONLY,
                   nlink=1, flags=c.INODE_FLAG_READONLY, size=0, size_compressed=0, blocks=1)


  def test_fpt_no_collision_single_file():
      """Single file produces one FPT entry, no collision blob."""
      root_dir = DirNode(rel_dir="", name="uroot", parent_rel_dir=None)
      f = FileNode(rel_path="eboot.bin", abs_path=Path("/fake/eboot.bin"),
                   parent_rel_dir="", name="eboot.bin", raw_size=0)
      f_ino = _make_simple_inode(3)
      f.inode = f_ino

      inode_by_path = {"file:eboot.bin": f_ino}
      fpt, collision, has_collision = make_fpt_and_collision_blob(
          dirs_sorted=[root_dir],
          files_sorted=[f],
          inode_by_path=inode_by_path,
          case_insensitive=True,
      )
      assert not has_collision
      assert collision is None
      # FPT must have exactly one entry: 8 bytes
      assert len(fpt) == 8
      h, val = struct.unpack_from("<II", fpt, 0)
      assert h == fpt_hash("/eboot.bin", case_insensitive=True)
      # value = inode_number (no dir flag)
      assert val == 3


  def test_fpt_dir_flag_set():
      """Directory entries set bit 29 (0x20000000) in the FPT value."""
      d = DirNode(rel_dir="sce_sys", name="sce_sys", parent_rel_dir="")
      d_ino = Inode(number=4, mode=c.INODE_MODE_DIR | c.INODE_RX_ONLY,
                    nlink=2, flags=c.INODE_FLAG_READONLY, size=65536, size_compressed=65536, blocks=1)
      d.inode = d_ino

      inode_by_path = {"dir:sce_sys": d_ino}
      fpt, collision, _ = make_fpt_and_collision_blob(
          dirs_sorted=[DirNode(rel_dir="", name="uroot", parent_rel_dir=None), d],
          files_sorted=[],
          inode_by_path=inode_by_path,
          case_insensitive=True,
      )
      assert collision is None
      h, val = struct.unpack_from("<II", fpt, 0)
      # dir entries have 0x20000000 ORed in
      assert val == (4 | 0x20000000)


  def test_fpt_collision_blob_terminator():
      """Collision entries end with 0x18 bytes of zero padding."""
      # Two files that collide: craft names that hash to the same value
      # by finding a real collision via brute force is impractical here,
      # so test the structure if we manually inject colliding hashes via
      # a monkey-patch-free approach: pick names with known identical hash.
      # Instead, validate the terminator structure via a known collision pair.
      # We'll use two entries that we know will collide based on the hash algorithm.
      # hash("/a") and hash("/A") are the same when case_insensitive=True
      f1 = FileNode(rel_path="a", abs_path=Path("/fake/a"), parent_rel_dir="",
                    name="a", raw_size=0)
      f1.inode = _make_simple_inode(3)
      # We can't easily get a natural collision without brute force.
      # Instead verify the collision blob format via the structure test:
      # collision blob must end with 0x18 zeros per collision group.
      # We test this by directly invoking with two files that DO collide.
      # The only reliable way is to monkeypatch fpt_hash to force collision:
      import mkpfs.pfs as pfs_mod
      original_fpt_hash = pfs_mod.fpt_hash
      try:
          pfs_mod.fpt_hash = lambda name, case_insensitive=True: 0xDEADBEEF  # force all same hash
          f2 = FileNode(rel_path="b", abs_path=Path("/fake/b"), parent_rel_dir="",
                        name="b", raw_size=0)
          f2.inode = _make_simple_inode(4)
          inode_by_path = {"file:a": f1.inode, "file:b": f2.inode}
          root = DirNode(rel_dir="", name="uroot", parent_rel_dir=None)
          fpt, blob, has_collision = make_fpt_and_collision_blob(
              dirs_sorted=[root],
              files_sorted=[f1, f2],
              inode_by_path=inode_by_path,
              case_insensitive=True,
          )
          assert has_collision
          assert blob is not None
          # blob ends with 0x18 zero bytes per collision group
          assert blob[-0x18:] == b"\x00" * 0x18
          # FPT entry value must have 0x80000000 set (collision pointer)
          h, val = struct.unpack_from("<II", fpt, 0)
          assert val & 0x80000000 != 0
      finally:
          pfs_mod.fpt_hash = original_fpt_hash
  ```

- [x] **Step 2: Run tests**

  ```bash
  uv run --frozen pytest tests/mkpfs/test_parity_fpt.py -v
  ```
  Fix any divergence in `mkpfs/pfs.py`.

- [x] **Step 3: Commit**

  ```bash
  git add tests/mkpfs/test_parity_fpt.py
  git commit -m "test(parity): add fpt_hash and collision blob parity tests"
  ```

---

## Task 6: Audit and fix build_pfs — inode flags for signed images

**Files:**
- Read: `legacy/ffpfs.py` lines 844–986
- Modify/verify: `mkpfs/pfs.py` (`build_pfs`)
- Create: `tests/mkpfs/fixtures/helpers.py`
- Add tests to `tests/mkpfs/test_parity_builder.py`

Critical items from legacy `build_pfs`:
- `super_root_inode.flags = INODE_FLAG_INTERNAL | (0 if signed else INODE_FLAG_READONLY) | (INODE_FLAG_SIGNED_EXTRA if signed else 0)`
- `uroot_inode.flags = (0 if signed else INODE_FLAG_READONLY) | (INODE_FLAG_SIGNED_EXTRA if signed else 0)`
- non-root dirs: `flags = INODE_FLAG_READONLY | (INODE_FLAG_SIGNED_EXTRA if signed else 0)`
- files: `flags = INODE_FLAG_READONLY | (INODE_FLAG_COMPRESSED if ...) | (INODE_FLAG_SIGNED_EXTRA if signed else 0)`
- collision_inode: `flags = INODE_FLAG_INTERNAL | INODE_FLAG_READONLY | (INODE_FLAG_SIGNED_EXTRA if signed else 0)`
- `ndblock += 2` for signed images (skips 2 blocks for superroot + uroot dirs before signed layout)

- [x] **Step 1: Create fixture helper**

  Create `tests/mkpfs/fixtures/__init__.py` (empty).

  Create `tests/mkpfs/fixtures/helpers.py`:
  ```python
  """Shared test fixture builders for parity tests."""
  import json
  from pathlib import Path


  def make_minimal_app(tmp_path: Path) -> Path:
      """Create minimal valid app tree under tmp_path/app/."""
      app = tmp_path / "app"
      sce = app / "sce_sys"
      sce.mkdir(parents=True)
      (sce / "param.json").write_text(json.dumps({"titleId": "NPXS99999"}), encoding="utf-8")
      (app / "eboot.bin").write_bytes(b"\x00" * 128)
      return app


  def make_app_with_nested_dirs(tmp_path: Path) -> Path:
      """App tree with nested dirs and several files for FPT/tree coverage."""
      app = tmp_path / "app"
      sce = app / "sce_sys"
      sce.mkdir(parents=True)
      (sce / "param.json").write_text(json.dumps({"titleId": "NPXS99999"}), encoding="utf-8")
      (app / "eboot.bin").write_bytes(b"x" * 200)
      sub = app / "data" / "levels"
      sub.mkdir(parents=True)
      (sub / "level1.bin").write_bytes(b"L" * 300)
      (sub / "level2.bin").write_bytes(b"M" * 400)
      (app / "data" / "config.json").write_text('{"v":1}', encoding="utf-8")
      return app
  ```

- [x] **Step 2: Write builder flag parity tests**

  Create `tests/mkpfs/test_parity_builder.py`:
  ```python
  """Verify build_pfs inode flags match legacy/ffpfs.py."""
  import io, struct
  import pytest
  from pathlib import Path
  import mkpfs.consts as c
  from mkpfs.pfs import build_pfs, parse_image_header, parse_image_inodes
  from tests.mkpfs.fixtures.helpers import make_minimal_app, make_app_with_nested_dirs


  def _build(tmp_path: Path, signed: bool = False) -> Path:
      src = make_minimal_app(tmp_path / "src")
      out = tmp_path / "out.ffpfs"
      build_pfs(
          source_root=src, output_path=out, block_size=65536,
          pfs_version=c.PFS_VERSION_PS4, inode_bits=32,
          case_insensitive=True, signed=signed,
          compress=False, threshold_gain=20,
          cpu_count=1, zlib_level=9, dry_run=False, verbose=False,
      )
      return out


  def test_unsigned_superroot_flags(tmp_path):
      out = _build(tmp_path, signed=False)
      with out.open("rb") as fh:
          hdr = parse_image_header(fh)
          inodes = parse_image_inodes(fh, hdr)
      # inode 0 is superroot
      sr = inodes[0]
      assert sr.flags & c.INODE_FLAG_INTERNAL
      assert sr.flags & c.INODE_FLAG_READONLY
      assert not (sr.flags & c.INODE_FLAG_SIGNED_EXTRA)


  def test_signed_superroot_flags(tmp_path):
      out = _build(tmp_path, signed=True)
      with out.open("rb") as fh:
          hdr = parse_image_header(fh)
          inodes = parse_image_inodes(fh, hdr)
      sr = inodes[0]
      assert sr.flags & c.INODE_FLAG_INTERNAL
      assert not (sr.flags & c.INODE_FLAG_READONLY)   # cleared for signed
      assert sr.flags & c.INODE_FLAG_SIGNED_EXTRA


  def test_unsigned_uroot_flags(tmp_path):
      out = _build(tmp_path, signed=False)
      with out.open("rb") as fh:
          hdr = parse_image_header(fh)
          inodes = parse_image_inodes(fh, hdr)
      # uroot is inode 2 (no collision in minimal app)
      uroot = inodes[2]
      assert uroot.flags & c.INODE_FLAG_READONLY
      assert not (uroot.flags & c.INODE_FLAG_SIGNED_EXTRA)


  def test_signed_uroot_flags(tmp_path):
      out = _build(tmp_path, signed=True)
      with out.open("rb") as fh:
          hdr = parse_image_header(fh)
          inodes = parse_image_inodes(fh, hdr)
      uroot = inodes[2]
      assert not (uroot.flags & c.INODE_FLAG_READONLY)
      assert uroot.flags & c.INODE_FLAG_SIGNED_EXTRA


  def test_file_inode_flags_unsigned(tmp_path):
      out = _build(tmp_path, signed=False)
      with out.open("rb") as fh:
          hdr = parse_image_header(fh)
          inodes = parse_image_inodes(fh, hdr)
      # All file inodes must have READONLY set and no SIGNED_EXTRA
      file_inodes = [i for i in inodes if i.mode & c.INODE_MODE_FILE]
      for fi in file_inodes:
          assert fi.flags & c.INODE_FLAG_READONLY, f"inode {fi.number} missing READONLY"
          assert not (fi.flags & c.INODE_FLAG_SIGNED_EXTRA), f"inode {fi.number} has SIGNED_EXTRA in unsigned image"


  def test_file_inode_flags_signed(tmp_path):
      out = _build(tmp_path, signed=True)
      with out.open("rb") as fh:
          hdr = parse_image_header(fh)
          inodes = parse_image_inodes(fh, hdr)
      file_inodes = [i for i in inodes if i.mode & c.INODE_MODE_FILE
                     and not (i.flags & c.INODE_FLAG_INTERNAL)]
      for fi in file_inodes:
          assert fi.flags & c.INODE_FLAG_READONLY, f"inode {fi.number} missing READONLY"
          assert fi.flags & c.INODE_FLAG_SIGNED_EXTRA, f"inode {fi.number} missing SIGNED_EXTRA"
  ```

- [x] **Step 3: Run tests**

  ```bash
  uv run --frozen pytest tests/mkpfs/test_parity_builder.py -v
  ```
  Fix any missing `INODE_FLAG_SIGNED_EXTRA` assignments in `mkpfs/pfs.py:build_pfs`.

- [x] **Step 4: Commit**

  ```bash
  git add tests/mkpfs/fixtures/__init__.py tests/mkpfs/fixtures/helpers.py tests/mkpfs/test_parity_builder.py
  git commit -m "test(parity): add builder inode-flags parity tests; fix SIGNED_EXTRA if missing"
  ```

---

## Task 7: Audit and fix signed image build — ndblock gap and header sig

**Files:**
- Read: `legacy/ffpfs.py` lines 1004–1210 (signed build section)
- Modify/verify: `mkpfs/pfs.py` (`build_pfs` signed path, `verify_signed_image_signatures`)
- Create: `tests/mkpfs/test_parity_signed.py`

Critical legacy behaviour:
- `ndblock += 2` after assigning FPT (and optional collision) inodes but before assigning uroot/dir/file inodes
- `HEADER_DIGEST_OFFSET=0x380` and `HEADER_DIGEST_SIZE=0x5A0` are used when computing the header HMAC
- `block_hmac_without_slot` is called with `signed=False` for inode table blocks (no zeroing)
- `verify_signed_image_signatures` uses `ZERO_EKPFS` + `header.seed` to derive the sign key

- [x] **Step 1: Write signed-image round-trip test**

  Create `tests/mkpfs/test_parity_signed.py`:
  ```python
  """Verify signed image build produces a verifiable image (round-trip check)."""
  from pathlib import Path
  import mkpfs.consts as c
  from mkpfs.pfs import build_pfs
  from mkpfs.cli import run_image_check
  from tests.mkpfs.fixtures.helpers import make_minimal_app, make_app_with_nested_dirs


  def _build_signed(tmp_path: Path, src_fn=make_minimal_app) -> tuple[Path, Path]:
      src = src_fn(tmp_path / "src")
      out = tmp_path / "signed.ffpfs"
      build_pfs(
          source_root=src, output_path=out, block_size=65536,
          pfs_version=c.PFS_VERSION_PS4, inode_bits=32,
          case_insensitive=True, signed=True,
          compress=False, threshold_gain=20,
          cpu_count=1, zlib_level=9, dry_run=False, verbose=False,
      )
      return out, src


  def test_signed_image_passes_check(tmp_path):
      """A newly built signed image must pass run_image_check with zero errors."""
      out, src = _build_signed(tmp_path)
      errors, warnings, _tree, uroot = run_image_check(
          image=out, source=None, print_tree=False, emit_report=False
      )
      assert errors == [], f"signed image check produced errors: {errors}"


  def test_signed_image_mode_bit_set(tmp_path):
      """Built signed image must have PFS_MODE_SIGNED in the header mode field."""
      from mkpfs.pfs import parse_image_header
      out, _ = _build_signed(tmp_path)
      with out.open("rb") as fh:
          hdr = parse_image_header(fh)
      assert hdr.mode & c.PFS_MODE_SIGNED


  def test_signed_image_with_nested_dirs_passes_check(tmp_path):
      out, src = _build_signed(tmp_path, src_fn=make_app_with_nested_dirs)
      errors, _warnings, _tree, _uroot = run_image_check(
          image=out, source=None, print_tree=False, emit_report=False
      )
      assert errors == [], f"nested signed image errors: {errors}"


  def test_signed_image_source_match(tmp_path):
      """Signed image must also pass source-match validation."""
      out, src = _build_signed(tmp_path, src_fn=make_app_with_nested_dirs)
      errors, _warnings, _tree, _uroot = run_image_check(
          image=out, source=src, print_tree=False, emit_report=False
      )
      assert errors == [], f"source-match errors: {errors}"
  ```

- [x] **Step 2: Run tests**

  ```bash
  uv run --frozen pytest tests/mkpfs/test_parity_signed.py -v
  ```
  If any test fails because of signature mismatch or `ndblock` errors, trace through `build_pfs` in `mkpfs/pfs.py` and compare the `ndblock += 2` skip against `legacy/ffpfs.py` line ~1056. Also verify `HEADER_DIGEST_OFFSET`/`HEADER_DIGEST_SIZE` are used in `verify_signed_image_signatures`.

- [x] **Step 3: Verify `block_hmac_without_slot` inode-block arg**

  In `mkpfs/pfs.py:verify_signed_image_signatures`, find the call that verifies inode table blocks. Confirm `signed=False` is passed (no zeroing), matching legacy line 1748:
  ```python
  expected = hmac_sha256(sign_key, block_hmac_without_slot(block_data, 0, header.block_size, signed=False))
  ```

- [x] **Step 4: Commit**

  ```bash
  git add tests/mkpfs/test_parity_signed.py mkpfs/pfs.py
  git commit -m "test(parity): add signed image round-trip tests; fix ndblock/HMAC divergence if present"
  ```

---

## Task 8: Add `verify` alias to the check subcommand

**Files:**
- Read: `legacy/ffpfs.py` lines 2638–2663 (`build_cli`)
- Modify: `mkpfs/cli.py` (`cli_mkpfs_main_parsers`)
- Modify: `tests/test_main.py` (update help text assertion if needed)
- Add: `tests/mkpfs/test_cli_smoke.py`

Legacy `build_cli` registers:
```python
check_parser = sub.add_parser("check", aliases=["verify"], ...)
```
The new `cli_mkpfs_main_parsers` omits the `aliases=["verify"]` argument.

- [x] **Step 1: Write failing test**

  Add to `tests/mkpfs/test_cli_smoke.py`:
  ```python
  def test_verify_alias_exists():
      """'verify' must be an accepted alias for the check subcommand."""
      import subprocess, sys
      result = subprocess.run(
          [sys.executable, "-m", "mkpfs", "verify", "--help"],
          capture_output=True, text=True
      )
      assert result.returncode == 0, f"verify --help failed: {result.stderr}"
  ```

- [x] **Step 2: Run to confirm it fails**

  ```bash
  uv run --frozen pytest tests/mkpfs/test_cli_smoke.py::test_verify_alias_exists -v
  ```
  Expected: FAIL.

- [x] **Step 3: Add alias to mkpfs/cli.py**

  In `cli_mkpfs_main_parsers`, change:
  ```python
  check_parser = sub.add_parser("check", help="Validate image structure and contents")
  ```
  to:
  ```python
  check_parser = sub.add_parser("check", aliases=["verify"], help="Validate image structure and contents")
  ```

- [x] **Step 4: Run tests**

  ```bash
  uv run --frozen pytest tests/mkpfs/test_cli_smoke.py -v
  ./run-tests.sh
  ```
  Update `tests/test_main.py` help-text assertion if the help output changed.

- [x] **Step 5: Commit**

  ```bash
  git add mkpfs/cli.py tests/mkpfs/test_cli_smoke.py tests/test_main.py
  git commit -m "fix(cli): add 'verify' alias for check subcommand, matching legacy/ffpfs.py build_cli"
  ```

---

## Task 9: Side-by-side runtime parity — unsigned image byte comparison

**Files:**
- Read-only: `legacy/ffpfs.py`
- Create: `tests/mkpfs/test_parity_runtime.py`
- Temporary artifacts: `tmp/parity/`

This task runs both legacy and new implementations on the same source input and compares output images byte-for-byte.

- [x] **Step 1: Create runtime parity test**

  Create `tests/mkpfs/test_parity_runtime.py`:
  ```python
  """Side-by-side runtime parity: legacy/ffpfs.py vs mkpfs.pfs.build_pfs.

  Runs both implementations on identical inputs and compares output images
  and check/ls output byte-by-byte / line-by-line.

  Legacy is invoked via subprocess in read-only fashion.
  Temporary artifacts land in tmp/parity/ (not committed).
  """
  import subprocess, sys, json
  from pathlib import Path
  import pytest
  import mkpfs.consts as c
  from mkpfs.pfs import build_pfs, parse_image_header, parse_image_inodes
  from mkpfs.cli import run_image_check
  from tests.mkpfs.fixtures.helpers import make_minimal_app, make_app_with_nested_dirs

  LEGACY_SCRIPT = Path(__file__).parents[3] / "legacy" / "ffpfs.py"


  def _run_legacy_build(src: Path, out: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
      cmd = [
          sys.executable, str(LEGACY_SCRIPT), "create",
          "--path", str(src), "--output", str(out),
          "--no-compress", "--block-size", "65536",
          "--version", "PS4", "--inode-bits", "32",
          "--case-insensitive",
      ] + (extra_args or [])
      return subprocess.run(cmd, capture_output=True, text=True)


  def _build_new(src: Path, out: Path, signed: bool = False) -> None:
      build_pfs(
          source_root=src, output_path=out, block_size=65536,
          pfs_version=c.PFS_VERSION_PS4, inode_bits=32,
          case_insensitive=True, signed=signed,
          compress=False, threshold_gain=20,
          cpu_count=1, zlib_level=9, dry_run=False, verbose=False,
      )


  @pytest.fixture(autouse=True)
  def parity_tmp(tmp_path):
      parity = Path("tmp/parity")
      parity.mkdir(parents=True, exist_ok=True)
      return parity


  def test_unsigned_image_byte_identical(tmp_path):
      src = make_minimal_app(tmp_path / "src")

      legacy_out = tmp_path / "legacy.ffpfs"
      result = _run_legacy_build(src, legacy_out)
      assert result.returncode == 0, f"Legacy build failed: {result.stderr}"

      new_out = tmp_path / "new.ffpfs"
      _build_new(src, new_out)

      assert legacy_out.read_bytes() == new_out.read_bytes(), (
          "Unsigned image bytes differ between legacy and new implementation"
      )


  def test_unsigned_check_agrees(tmp_path):
      """New check passes on a legacy-built image and vice versa."""
      src = make_minimal_app(tmp_path / "src")

      legacy_out = tmp_path / "legacy.ffpfs"
      result = _run_legacy_build(src, legacy_out)
      assert result.returncode == 0

      errors, _warnings, _tree, _uroot = run_image_check(
          image=legacy_out, source=None, print_tree=False, emit_report=False
      )
      assert errors == [], f"New check found errors in legacy-built image: {errors}"


  def test_legacy_check_accepts_new_image(tmp_path):
      """Legacy check command accepts a new-built image."""
      src = make_minimal_app(tmp_path / "src")
      new_out = tmp_path / "new.ffpfs"
      _build_new(src, new_out)

      result = subprocess.run(
          [sys.executable, str(LEGACY_SCRIPT), "check", "--image", str(new_out)],
          capture_output=True, text=True
      )
      assert result.returncode == 0, f"Legacy check rejected new image: {result.stdout}\n{result.stderr}"


  def test_nested_dirs_unsigned_byte_identical(tmp_path):
      src = make_app_with_nested_dirs(tmp_path / "src")

      legacy_out = tmp_path / "legacy.ffpfs"
      result = _run_legacy_build(src, legacy_out)
      assert result.returncode == 0, f"Legacy build failed: {result.stderr}"

      new_out = tmp_path / "new.ffpfs"
      _build_new(src, new_out)

      assert legacy_out.read_bytes() == new_out.read_bytes(), (
          "Nested-dir unsigned image bytes differ"
      )
  ```

- [x] **Step 2: Run tests**

  ```bash
  uv run --frozen pytest tests/mkpfs/test_parity_runtime.py -v
  ```
  For any byte difference, use a hex dump to identify the differing offset and trace it to the responsible field in `build_pfs`.

  ```bash
  python3 -c "
  a = open('tmp/parity/legacy.ffpfs','rb').read()
  b = open('tmp/parity/new.ffpfs','rb').read()
  for i,(x,y) in enumerate(zip(a,b)):
      if x!=y: print(f'0x{i:08X}: legacy=0x{x:02X} new=0x{y:02X}')
  " 2>&1 | head -30
  ```

- [x] **Step 3: Fix any divergence found**

  Trace every byte difference back to its source field in `legacy/ffpfs.py`, fix `mkpfs/pfs.py`, re-run until images are identical.

- [x] **Step 4: Commit**

  ```bash
  git add tests/mkpfs/test_parity_runtime.py
  git commit -m "test(parity): add side-by-side runtime byte-comparison against legacy/ffpfs.py"
  ```

---

## Task 10: Side-by-side runtime parity — signed image

**Files:**
- Extend: `tests/mkpfs/test_parity_runtime.py`

- [x] **Step 1: Add signed image runtime tests**

  Append to `tests/mkpfs/test_parity_runtime.py`:
  ```python
  def test_signed_image_byte_identical(tmp_path):
      src = make_minimal_app(tmp_path / "src")

      legacy_out = tmp_path / "legacy_signed.ffpfs"
      result = _run_legacy_build(src, legacy_out, extra_args=["--signed"])
      assert result.returncode == 0, f"Legacy signed build failed: {result.stderr}"

      new_out = tmp_path / "new_signed.ffpfs"
      _build_new(src, new_out, signed=True)

      assert legacy_out.read_bytes() == new_out.read_bytes(), (
          "Signed image bytes differ between legacy and new implementation"
      )


  def test_signed_legacy_check_accepts_new_signed(tmp_path):
      src = make_minimal_app(tmp_path / "src")
      new_out = tmp_path / "new_signed.ffpfs"
      _build_new(src, new_out, signed=True)

      result = subprocess.run(
          [sys.executable, str(LEGACY_SCRIPT), "check", "--image", str(new_out)],
          capture_output=True, text=True
      )
      assert result.returncode == 0, f"Legacy check rejected new signed image:\n{result.stdout}\n{result.stderr}"
  ```

- [x] **Step 2: Run tests**

  ```bash
  uv run --frozen pytest tests/mkpfs/test_parity_runtime.py::test_signed_image_byte_identical -v
  uv run --frozen pytest tests/mkpfs/test_parity_runtime.py::test_signed_legacy_check_accepts_new_signed -v
  ```

- [x] **Step 3: Fix and commit**

  ```bash
  git add tests/mkpfs/test_parity_runtime.py mkpfs/pfs.py
  git commit -m "test(parity): add signed image side-by-side runtime comparison vs legacy"
  ```

---

## Task 11: Audit and fix all docstrings, comments, and type annotations

**Files:**
- Modify: `mkpfs/pfs.py`, `mkpfs/cli.py`, `mkpfs/consts.py`, `mkpfs/utils.py`

Criteria (from CLAUDE.md):
- Every function has a Google-style docstring (Args, Returns, Raises sections).
- All local variables have explicit type annotations at their definition site.
- No `Optional[X]` — use `X | None`. No `List[X]` — use `list[X]`.
- No em dashes in prose.
- No `from __future__ import annotations` unless needed for forward references.
- Block comments above each logical phase in functions > 30 lines.

- [x] **Step 1: Scan for missing/wrong docstrings**

  ```bash
  uv run --frozen ruff check . --select D
  ```
  Review output and fix each issue manually.

- [x] **Step 2: Scan for type annotation issues**

  ```bash
  uv run --frozen ruff check . --select ANN
  ```

- [x] **Step 3: Fix all issues in mkpfs/pfs.py**

  For every function without a docstring: add one. For functions with a docstring that doesn't match the actual behavior (cross-check against legacy): rewrite it. Add block comments above phases in long functions (`build_pfs`, `verify_signed_image_signatures`, `run_image_check`).

- [x] **Step 4: Fix all issues in mkpfs/cli.py**

  `print_build_parameters`, `print_summary`, `prompt_overwrite`, `parse_args`, `cli_mkpfs_create_run`, `cli_mkpfs_check_run`, `cli_mkpfs_ls_run`, `cli_mkpfs_info_run`, `cli_mkpfs_analyze_run`, `cli_mkpfs_extract_run`, `run_image_check`, `cli_mkpfs_main_parsers`, `cli_mkpfs_main`, `main` — each must have a proper docstring.

- [x] **Step 5: Run ruff and pytest**

  ```bash
  ./run-tests.sh
  ```

- [x] **Step 6: Commit**

  ```bash
  git add mkpfs/pfs.py mkpfs/cli.py mkpfs/consts.py mkpfs/utils.py
  git commit -m "refactor: fix docstrings, type annotations, and block comments across all mkpfs modules"
  ```

---

## Task 12: Final pre-release verification

**Files:**
- Verify: full test suite, ruff, mkdocs build, twine check

- [x] **Step 1: Activate venv and run full checks**

  ```bash
  source .venv/bin/activate
  ./run-tests.sh
  ```
  Expected: all tests pass, ruff clean.

- [x] **Step 2: Build docs**

  ```bash
  uv run mkdocs build --strict
  ```
  Fix any broken links.

- [x] **Step 3: Build and validate package**

  ```bash
  uv build
  uv run --frozen twine check dist/*
  ```
  Expected: PASSED.

- [x] **Step 4: Update HTML dashboard**

  Open `current-plan/progress.html` and mark all tasks complete.

- [x] **Step 5: Final commit**

  ```bash
  git add current-plan/progress.html
  git commit -m "chore: mark parity audit complete; all checks pass"
  ```

---

## Verification summary

After all tasks, the following must be true:

1. `uv run --frozen pytest` — all green
2. `uv run --frozen ruff check .` — clean
3. Legacy-built image passes new `check` — verified in Task 9
4. New-built image passes legacy `check` — verified in Task 9
5. Byte-identical images for unsigned + signed on same input — verified in Tasks 9 and 10
6. `verify` alias works — verified in Task 8
7. Signed image round-trip with `run_image_check` producing zero errors — verified in Task 7
8. `uv build && twine check dist/*` — PASSED
