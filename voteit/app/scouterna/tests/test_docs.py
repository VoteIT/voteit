from doctest import DocTestSuite


def load_tests(loader, tests, ignore):
    from voteit.app.scouterna import backends

    tests.addTests(DocTestSuite(backends))
    return tests
