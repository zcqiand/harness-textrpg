def test_package_importable():
    import text_rpg

    assert text_rpg.__version__ == "0.1.0"
