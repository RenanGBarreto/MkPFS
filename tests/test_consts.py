import mkpfs.consts as consts


def test_basic_consts() -> None:
    assert consts.PFS_MAGIC == 20130315
    assert consts.PFS_VERSION_PS4 in (1,)
    assert consts.SIG_SIZE == 32
