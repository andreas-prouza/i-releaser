"""Version numbers, database updates, backups and connections"""
import json, os, shutil, sqlite3, stat, subprocess, sys, tempfile, threading, unittest
from unittest.mock import patch

from etc import constants
# Before meta_file (circular import)
from modules import deploy_version
from modules import errors, files, version
from modules.db import app_info_data, app_sqlite, compression
from modules.db.updates import v_2_0_1, v_2_0_2, v_3_1_0
from modules.deploy_version import Deploy_Version
from modules.meta_file_status import Meta_file_status


class Database_Test(unittest.TestCase):


    def setUp(self):

        self.tmp_dir = tempfile.mkdtemp()
        self.db_file = os.path.join(self.tmp_dir, 'app.sqlite')
        self.db_defaults = app_sqlite.get_db_connection.__defaults__
        app_sqlite.get_db_connection.__defaults__ = (self.db_file,)
        app_sqlite.create_tables(self.db_file)


    def tearDown(self):
        app_sqlite.get_db_connection.__defaults__ = self.db_defaults
        os.chmod(self.tmp_dir, stat.S_IRWXU)
        shutil.rmtree(self.tmp_dir)


    def get_user_version(self) -> int:
        with app_sqlite.get_db_connection() as conn:
            return conn.execute("PRAGMA user_version").fetchone()[0]


    def set_old_database(self, app_version: str) -> None:
        """A database of a version before the schema version"""

        with app_sqlite.get_db_connection() as conn:
            conn.execute("PRAGMA user_version = 0")
            conn.execute("INSERT INTO app_info (version, data) VALUES (?, '')", (app_version,))



class TestVersionNumbers(Database_Test):


    def next_version(self, project: str) -> int:
        return Deploy_Version.get_next_deploy_version(project, Meta_file_status.NEW)['version']


    def test_each_project_counts_on_its_own(self):

        versions = {'a': [], 'b': []}

        for _ in range(3):
            for project in versions:
                versions[project].append(self.next_version(project))

        self.assertEqual(versions, {'a': [1, 2, 3], 'b': [1, 2, 3]})


    def test_next_version_after_a_gap(self):

        with app_sqlite.get_db_connection() as conn:
            for v in [1, 2, 7]:
                conn.execute("INSERT INTO deploy_versions (project, version) VALUES ('a', ?)", (v,))

        self.assertEqual(self.next_version('a'), 8)


    def test_parallel_creation(self):

        results = []

        def create():
            results.append(self.next_version('a'))

        threads = [threading.Thread(target=create) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sorted(results), list(range(1, 11)))



class TestConnection(Database_Test):


    def test_with_closes_the_connection(self):

        with app_sqlite.get_db_connection() as conn:
            conn.execute("SELECT 1")

        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


    def test_with_commits(self):

        with app_sqlite.get_db_connection() as conn:
            conn.execute("INSERT INTO deploy_versions (project, version) VALUES ('a', 1)")

        with app_sqlite.get_db_connection() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM deploy_versions").fetchone()[0], 1)



class TestUpdates(Database_Test):


    def setUp(self):

        super().setUp()
        self.calls = []


    def fake_updates(self, failing: int|None=None) -> list:

        def update(number: int):

            def run():
                if number == failing:
                    with app_sqlite.get_db_connection() as conn:
                        conn.execute("INSERT INTO deploy_versions (project, version) VALUES ('half done', 1)")
                    raise Exception('Update failed')
                self.calls.append(number)

            return run

        return [(number, update(number)) for number in range(1, app_sqlite.SCHEMA_VERSION + 1)]


    def backups(self) -> list[str]:
        directory = os.path.join(self.tmp_dir, 'backup')
        return os.listdir(directory) if os.path.isdir(directory) else []


    def test_new_database_needs_no_update(self):

        with patch.object(app_sqlite, 'get_updates', return_value=self.fake_updates()):
            app_sqlite.check_updates()

        self.assertEqual(self.calls, [])
        self.assertEqual(self.get_user_version(), app_sqlite.SCHEMA_VERSION)
        self.assertEqual(self.backups(), [])


    def test_updates_run_once(self):

        self.set_old_database('2.0.2')

        with patch.object(app_sqlite, 'get_updates', return_value=self.fake_updates()):
            app_sqlite.check_updates()
            first = list(self.calls)
            app_sqlite.check_updates()

        self.assertEqual(first, list(range(3, app_sqlite.SCHEMA_VERSION + 1)))
        self.assertEqual(self.calls, first)
        self.assertEqual(self.get_user_version(), app_sqlite.SCHEMA_VERSION)


    def test_old_version_in_the_app_info_does_not_matter_anymore(self):

        with app_sqlite.get_db_connection() as conn:
            conn.execute("INSERT INTO app_info (version, data) VALUES ('2.0.0', '')")

        with patch.object(app_sqlite, 'get_updates', return_value=self.fake_updates()):
            app_sqlite.check_updates()

        self.assertEqual(self.calls, [])


    def test_failing_update_restores_the_database(self):

        self.set_old_database('2.0.2')

        with app_sqlite.get_db_connection() as conn:
            conn.execute("INSERT INTO deploy_versions (project, version) VALUES ('before', 1)")

        with patch.object(app_sqlite, 'get_updates', return_value=self.fake_updates(failing=5)):
            with self.assertRaises(errors.App_Error) as e:
                app_sqlite.check_updates()

        self.assertIn('restored', str(e.exception))
        self.assertEqual(len(self.backups()), 1)

        with app_sqlite.get_db_connection() as conn:
            self.assertEqual([row[0] for row in conn.execute("SELECT project FROM deploy_versions")], ['before'])

        self.assertEqual(self.get_user_version(), 0)


    def test_backup_can_be_opened(self):

        self.set_old_database('2.0.2')

        with patch.object(app_sqlite, 'get_updates', return_value=self.fake_updates()):
            app_sqlite.check_updates()

        backup = os.path.join(self.tmp_dir, 'backup', self.backups()[0])
        conn = sqlite3.connect(backup)

        self.assertEqual(conn.execute("SELECT version FROM app_info").fetchone()[0], '2.0.2')
        conn.close()


    @unittest.skipIf(os.geteuid() == 0, 'root can write everywhere')
    def test_no_update_without_backup(self):

        self.set_old_database('2.0.2')
        os.makedirs(os.path.join(self.tmp_dir, 'backup'))
        os.chmod(os.path.join(self.tmp_dir, 'backup'), stat.S_IRUSR | stat.S_IXUSR)

        try:
            with patch.object(app_sqlite, 'get_updates', return_value=self.fake_updates()):
                with self.assertRaises(Exception):
                    app_sqlite.check_updates()

            self.assertEqual(self.calls, [])

        finally:
            os.chmod(os.path.join(self.tmp_dir, 'backup'), stat.S_IRWXU)


    def test_only_the_newest_backups_are_kept(self):

        with patch.object(constants, 'C_DB_BACKUP_COUNT', 2):
            for _ in range(4):
                app_sqlite.backup_database(1)

        self.assertEqual(len(self.backups()), 2)


    def test_check_schema_version(self):

        app_sqlite.check_schema_version()

        self.set_old_database('2.0.2')

        with self.assertRaises(errors.App_Error) as e:
            app_sqlite.check_schema_version()

        self.assertIn('Start the web app first', str(e.exception))


    def test_version_comes_from_one_place(self):

        with open(os.path.join(os.path.dirname(__file__), '..', 'VERSION')) as f:
            self.assertEqual(version.APP_VERSION, f.read().strip())

        with open(os.path.join(os.path.dirname(__file__), '..', 'CHANGELOG.md')) as f:
            self.assertEqual(f.readline().strip(), f"# {version.APP_VERSION}")

        self.assertFalse(hasattr(constants, 'C_APP_VERSION'))



class TestUpdateSteps(Database_Test):


    def test_tokens_are_removed_from_custom_data(self):

        with app_sqlite.get_db_connection() as conn:
            conn.execute("INSERT INTO meta_files (custom_data) VALUES (?)", (compression.compress_field(json.dumps({'auth-token': 'secret', 'a': '1'})),))
            conn.execute("INSERT INTO meta_files (custom_data) VALUES (?)", (compression.compress_field(json.dumps({'auth-token': 'secret'})),))
            conn.execute("INSERT INTO meta_files (custom_data) VALUES (?)", (compression.compress_field(json.dumps({'a': '2'})),))

        v_3_1_0.remove_tokens_from_custom_data()

        with app_sqlite.get_db_connection() as conn:
            rows = [row[0] for row in conn.execute("SELECT custom_data FROM meta_files ORDER BY id")]

        self.assertEqual(json.loads(compression.decompress_field(rows[0])), {'a': '1'})
        self.assertIsNone(rows[1])
        self.assertEqual(json.loads(compression.decompress_field(rows[2])), {'a': '2'})


    def test_action_options_are_added_to_an_old_database(self):

        with app_sqlite.get_db_connection() as conn:
            conn.execute("ALTER TABLE actions DROP COLUMN fail_on_stderr")
            conn.execute("ALTER TABLE actions DROP COLUMN timeout_seconds")

        v_3_1_0.add_action_options()
        # Can be repeated
        v_3_1_0.add_action_options()

        with app_sqlite.get_db_connection() as conn:
            columns = [row['name'] for row in conn.execute("PRAGMA table_info(actions)")]

        self.assertIn('fail_on_stderr', columns)
        self.assertIn('timeout_seconds', columns)


    def test_parallel_options_are_added_to_an_old_database(self):

        with app_sqlite.get_db_connection() as conn:
            conn.execute("ALTER TABLE actions DROP COLUMN parallel_group")
            conn.execute("ALTER TABLE actions DROP COLUMN parallel")

        v_3_1_0.add_parallel_options()
        # Can be repeated
        v_3_1_0.add_parallel_options()

        with app_sqlite.get_db_connection() as conn:
            columns = [row['name'] for row in conn.execute("PRAGMA table_info(actions)")]

        self.assertIn('parallel_group', columns)
        self.assertIn('parallel', columns)


    def test_decompress_returns_text(self):

        self.assertEqual(compression.decompress_field(compression.compress_field('text')), 'text')
        self.assertEqual(compression.decompress_field(compression.compress_field(compression.compress_field('text'))), 'text')
        self.assertEqual(compression.decompress_field('text'), 'text')


    def test_old_updates_can_be_repeated(self):

        meta_dir = os.path.join(self.tmp_dir, 'meta')
        log_file = os.path.join(meta_dir, 'logs', 'run_history', '1.log')

        with app_sqlite.get_db_connection() as conn:
            conn.execute("INSERT INTO meta_files (meta_dir) VALUES (?)", (meta_dir,))
            conn.execute("INSERT INTO run_history (meta_file_id, log) VALUES (1, 'the log')")

        for _ in range(2):
            v_2_0_1.add_compression()
            v_2_0_2.extract_logs_2_meta_dir()

        self.assertEqual(files.readFile(log_file), 'the log')



class TestFiles(unittest.TestCase):


    def test_write_json_is_atomic(self):

        directory = tempfile.mkdtemp()
        file = os.path.join(directory, 'a.json')
        files.writeJson({'a': 1}, file)

        with self.assertRaises(TypeError):
            files.writeJson({'a': object()}, file)

        self.assertEqual(files.getJson(file), {'a': 1})
        self.assertEqual(os.listdir(directory), ['a.json'])
        shutil.rmtree(directory)
