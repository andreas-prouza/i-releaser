"""
The database of the tests which run in the test process (docs/features/code-quality-tooling.md, requirement 2).

    class My_Test(unittest.TestCase):
        def setUp(self):
            db_tools.use_temp_db(self)          # sets self.tmp_dir and self.db_file

    def test_something(temp_db):                # fixture of conftest.py: the directory
        ...

Each test gets a new database and meta directory. With addCleanup the database of the installation is set back and the
directory removed even if setUp fails after the call: the next test never works on the database of another one.
All modules use the default parameter of app_sqlite.get_db_connection, so it's replaced.
"""
import os
import shutil
import tempfile
from unittest.mock import patch

from etc import constants
from modules.db import app_sqlite



def use_temp_db(test) -> str:
    """
    Args:
        test: a unittest.TestCase, or anything with addCleanup(function, *args)

    Returns:
        str: the temporary directory (also test.tmp_dir); the database is test.db_file
    """

    tmp_dir = tempfile.mkdtemp(prefix='ir-db-')
    test.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)

    db_file = os.path.join(tmp_dir, 'app.sqlite')
    defaults = app_sqlite.get_db_connection.__defaults__
    test.addCleanup(setattr, app_sqlite.get_db_connection, '__defaults__', defaults)
    app_sqlite.get_db_connection.__defaults__ = (db_file,)
    app_sqlite.create_tables(db_file)

    meta_dir = patch.object(constants, 'C_META_DIR', os.path.join(tmp_dir, 'meta', '{project}', '{create_date}', '{deploy_version}'))
    meta_dir.start()
    test.addCleanup(meta_dir.stop)

    test.tmp_dir = tmp_dir
    test.db_file = db_file
    return tmp_dir



class Cleanups:
    """addCleanup of a pytest fixture: the functions run when the test ends, the last one first"""

    def __init__(self, request):
        self.request = request

    def addCleanup(self, function, *args, **kwargs):
        self.request.addfinalizer(lambda: function(*args, **kwargs))
