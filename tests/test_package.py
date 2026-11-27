import vn_addr


def test_version_is_a_string() -> None:
    assert isinstance(vn_addr.__version__, str)
