import unittest, sys, os, re, random, logging, tempfile, shutil, importlib.util
from types import SimpleNamespace
from unittest.mock import patch, Mock

# The repository root, so `etc` and `modules` are found
I_RELEASER_DIR = os.path.realpath(f"{os.path.dirname(__file__)}/..")
sys.path.insert(0, I_RELEASER_DIR)

# Before meta_file (circular import)
from modules import deploy_version  # noqa: F401
from modules import deploy_object as do
from modules.object_status import Status as Obj_Status
from modules.db_deployment import connection, catalog, mapping, state, journal, sync, objects, prepare, cutover, cleanup
from modules.db_deployment.state import Phase, Replaced_Object, Table_State



def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)



def load_example_script(name: str):
    spec = importlib.util.spec_from_file_location(f"example_{name}", f"{I_RELEASER_DIR}/scripts/examples/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



class Fake_Error(Exception):
    """Like pyodbc.Error: SQLSTATE first, message last"""
    def __init__(self, sqlstate: str, message: str='error'):
        super().__init__(sqlstate, message)



class Fake_Db:
    """Records the statements and answers them by rules: the first rule whose pattern matches wins"""

    def __init__(self):
        self.calls = []
        self.rules = []

    def on(self, pattern: str, result):
        self.rules.append((re.compile(pattern, re.S | re.I), result))
        return self

    def result(self, sql, params, default):
        for pattern, result in self.rules:
            if pattern.search(sql):
                if isinstance(result, Exception):
                    raise result
                if callable(result):
                    return result(sql, params)
                return result
        return default

    def execute(self, sql, params=None):
        self.calls.append(('execute', sql, params))
        return self.result(sql, params, 0)

    def query(self, sql, params=None):
        self.calls.append(('query', sql, params))
        return self.result(sql, params, [])

    def query_value(self, sql, params=None):
        rows = self.query(sql, params)
        if isinstance(rows, list):
            return next(iter(rows[0].values())) if rows else None
        return rows

    def qcmdexc(self, cmd, ignore_errors=False):
        self.calls.append(('cl', cmd, None))
        try:
            self.result(cmd, None, None)
            return True
        except Exception as e:
            if ignore_errors:
                return False
            raise connection.Db_Deployment_Exception(f"{cmd} failed: {e}") from e

    def close(self):
        pass

    def sqls(self, kind=None) -> list[str]:
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def index(self, pattern: str) -> int:
        """Index of the first call which matches"""
        for i, c in enumerate(self.calls):
            if re.search(pattern, c[1], re.S | re.I):
                return i
        raise AssertionError(f"No call matches {pattern}: {self.sqls()}")



def column(name, data_type='CHAR', nullable='Y', has_default='N', identity='NO', generation=None):
    return {'column_name': name, 'system_column_name': name, 'data_type': data_type, 'is_nullable': nullable,
            'has_default': has_default, 'is_identity': identity, 'identity_generation': generation}



SHADOW = 'S000000001'
SETTINGS = dict(connection.DEFAULT_SETTINGS)



def make_state(db, phase=Phase.COPIED, **kwargs) -> Table_State:
    st = Table_State(db, SHADOW, 1, 'PRODLIB', 'ORDERS')
    st.exists = True
    st.phase = phase
    st.journal_lib = 'JRNLIB'
    st.journal_name = 'JRN'
    st.config_hash = objects.get_config_hash({})
    for k, v in kwargs.items():
        setattr(st, k, v)
    return st



def make_sync(db, **kwargs) -> sync.Table_Sync:
    m = mapping.Column_Mapping([column('ID', 'INTEGER'), column('TEXT')], [column('ID', 'INTEGER'), column('TEXT')])
    return sync.Table_Sync(db, make_state(db, **kwargs), m, dict(SETTINGS))



class TestConnection(unittest.TestCase):


    def test_connection_string(self):

        config = {'connections': {'PROD400': {'system': 'prod.example.com', 'user': 'IREL', 'password': 'a;b}c',
                                              'options': {'QueryTimeout': '0'}}}}
        cs = connection.get_connection_string(config, 'prod400')

        self.assertEqual(cs, "DRIVER=IBM i Access ODBC Driver;SYSTEM=prod.example.com;UID=IREL;PWD={a;b}}c};QueryTimeout=0")
        self.assertNotIn('a;b', connection.mask_password(cs))


    def test_password_from_environment(self):

        config = {'connections': {'localhost': {'user': 'IREL', 'password_env': 'I_RELEASER_TEST_DB_PWD'}}}

        with patch.dict(os.environ, {'I_RELEASER_TEST_DB_PWD': 'secret'}):
            self.assertIn('PWD=secret', connection.get_connection_string(config, None))

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'I_RELEASER_TEST_DB_PWD'):
                connection.get_connection_string(config, 'localhost')


    def test_unknown_host(self):
        with self.assertRaisesRegex(connection.Db_Deployment_Exception, "No DB connection for host 'other'"):
            connection.get_connection_string({'connections': {'localhost': {}}}, 'other')


    def test_settings(self):

        settings = connection.get_settings({'defaults': {'batch_size': 10, 'lock_wait_seconds': 5}}, {'batch_size': 3, 'unknown': 1})

        self.assertEqual(settings['batch_size'], 3)
        self.assertEqual(settings['lock_wait_seconds'], 5)
        self.assertEqual(settings['apply_batch_size'], connection.DEFAULT_SETTINGS['apply_batch_size'])
        self.assertNotIn('unknown', settings)


    def test_row_errors(self):
        self.assertTrue(connection.is_row_error(Fake_Error('23505')))
        self.assertTrue(connection.is_row_error(Fake_Error('22018')))
        self.assertFalse(connection.is_row_error(Fake_Error('42704')))
        self.assertFalse(connection.is_row_error(Exception('communication link failure')))



class TestMapping(unittest.TestCase):


    def test_columns(self):

        old = [column('ID', 'INTEGER'), column('NAME'), column('ORDDT8', 'DECIMAL'), column('OLDCOL')]
        new = [column('ID', 'INTEGER'), column('NAME'), column('ORDDAT', 'DATE'), column('NEWCOL', has_default='Y'),
               column('NOTE', 'CLOB')]

        m = mapping.Column_Mapping(old, new, {'orddat': "DATE(TIMESTAMP_FORMAT(DIGITS(ORDDT8), 'YYYYMMDD'))", 'NOTE': "'-'"})

        self.assertEqual(m.columns, ['ID', 'NAME', 'ORDDAT', 'NOTE'])
        self.assertEqual(m.expressions, ['"ID"', '"NAME"', "DATE(TIMESTAMP_FORMAT(DIGITS(ORDDT8), 'YYYYMMDD'))", "'-'"])
        self.assertEqual(m.update_columns, m.columns)
        self.assertEqual(m.compare_columns, ['ID', 'NAME', 'ORDDAT'])
        self.assertFalse(m.overriding)
        self.assertTrue(any('ORDDT8' in w and 'OLDCOL' in w for w in m.warnings))


    def test_default(self):
        m = mapping.Column_Mapping([column('ID'), column('A')], [column('ID'), column('A')], {'A': '*default'})
        self.assertEqual(m.columns, ['ID'])


    def test_new_column_without_default(self):
        with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'NEWCOL'):
            mapping.Column_Mapping([column('ID')], [column('ID'), column('NEWCOL', nullable='N')])


    def test_unknown_expression(self):
        with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'XYZ'):
            mapping.Column_Mapping([column('ID')], [column('ID')], {'XYZ': '1'})


    def test_generated_columns(self):

        new = [column('ID', 'BIGINT', has_default='I', identity='YES', generation='ALWAYS'),
               column('CHANGED', 'TIMESTAMP', has_default='E'),
               column('TEXT')]
        m = mapping.Column_Mapping([column('ID', 'BIGINT'), column('CHANGED', 'TIMESTAMP'), column('TEXT')], new)

        self.assertEqual(m.columns, ['ID', 'TEXT'])
        self.assertTrue(m.overriding)
        self.assertEqual(m.update_columns, ['TEXT'])
        self.assertEqual(m.identity_columns, ['ID'])
        self.assertTrue(any('CHANGED' in w for w in m.warnings))


    def test_identity_by_default(self):
        new = [column('ID', 'BIGINT', has_default='I', identity='YES', generation='BY DEFAULT'), column('TEXT')]
        m = mapping.Column_Mapping([column('ID', 'BIGINT'), column('TEXT')], new)
        self.assertFalse(m.overriding)
        self.assertEqual(m.update_columns, ['ID', 'TEXT'])



class TestJournal(unittest.TestCase):


    def test_classify(self):
        self.assertEqual(journal.classify('R', 'PT'), journal.ROW)
        self.assertEqual(journal.classify('R', 'DL'), journal.ROW)
        self.assertEqual(journal.classify('R', 'UR'), journal.ROW)
        self.assertEqual(journal.classify('R', 'IL'), journal.IGNORE)
        self.assertEqual(journal.classify('F', 'OP'), journal.IGNORE)
        self.assertEqual(journal.classify('F', 'MS'), journal.IGNORE)
        self.assertEqual(journal.classify('F', 'CR'), journal.CLEAR)
        self.assertEqual(journal.classify('F', 'RG'), journal.FAIL)
        self.assertEqual(journal.classify('F', 'EJ'), journal.FAIL)
        self.assertEqual(journal.classify('D', 'CG'), journal.FAIL)
        self.assertEqual(journal.classify('C', 'CM'), journal.IGNORE)


    def entry(self, seq, code, entry_type, rrn=0, receiver='RCV0001'):
        return {'sequence_number': seq, 'journal_code': code, 'journal_entry_type': entry_type, 'count_or_rrn': rrn,
                'receiver_library': 'JRNLIB    ', 'receiver_name': receiver}


    def test_read(self):

        db = Fake_Db()
        st = make_state(db)
        reader = journal.Journal_Reader(db, st, batch_size=3)
        queued, cleared = [], []

        pages = [[self.entry(10, 'R', 'PT', 5), self.entry(11, 'R', 'IL', 99), self.entry(12, 'R', 'UP', 7)],
                 [self.entry(13, 'R', 'DL', 5, 'RCV0002')]]

        with patch.object(journal.Journal_Reader, 'fetch', side_effect=pages):
            count = reader.read(queued.append, lambda: cleared.append(True))

        self.assertEqual(count, 4)
        self.assertEqual(queued, [{5, 7}, {5}])
        self.assertEqual(cleared, [])
        self.assertEqual((st.receiver_lib, st.receiver_name, st.journal_sequence), ('JRNLIB', 'RCV0002', 13))


    def test_read_clear_and_fail(self):

        db = Fake_Db()
        st = make_state(db)
        reader = journal.Journal_Reader(db, st, batch_size=10)
        queued, cleared = [], []

        page = [self.entry(1, 'R', 'PT', 1), self.entry(2, 'F', 'CR'), self.entry(3, 'R', 'PT', 2), self.entry(4, 'F', 'RG'),
                self.entry(5, 'R', 'PT', 3)]

        with patch.object(journal.Journal_Reader, 'fetch', side_effect=[page]):
            with self.assertRaisesRegex(journal.Journal_Exception, 'F/RG'):
                reader.read(queued.append, lambda: cleared.append(True))

        # Rows before the clear are not needed anymore, rows before the failing entry are queued
        self.assertEqual(cleared, [True])
        self.assertEqual(queued, [{2}])
        self.assertEqual(st.journal_sequence, 3)


    def test_fetch_position(self):

        db = Fake_Db()
        st = make_state(db, start_time='2026-10-22 10:00:00')
        reader = journal.Journal_Reader(db, st, batch_size=100)

        reader.fetch()
        self.assertIn("STARTING_RECEIVER_NAME => '*CURCHAIN'", db.calls[-1][1])
        self.assertEqual(db.calls[-1][2][2], '2026-10-22 10:00:00')

        st.receiver_lib, st.receiver_name, st.journal_sequence = 'JRNLIB', 'RCV0002', 4711
        reader.fetch()
        self.assertIn('WHERE SEQUENCE_NUMBER > ?', db.calls[-1][1])
        self.assertEqual(db.calls[-1][2], ['JRNLIB', 'JRN', 'JRNLIB', 'RCV0002', 4711, 'PRODLIB', 'ORDERS', 4711, 100])



class TestSync(unittest.TestCase):


    def test_repair(self):

        db = Fake_Db().on('SYSPARTITIONSTAT', [{'number_rows': 90, 'number_deleted_rows': 15}])
        t = make_sync(db, target_size=100)

        t.repair()

        self.assertIn('DELETE FROM "S000000001"."ORDERS" T WHERE RRN(T) > ?', db.sqls('execute'))
        self.assertEqual(db.calls[-1][2], [100])
        self.assertIn('"S000000001"."IRMAP001" WHERE TGT_RRN > ?', db.calls[-1][1])


    def test_no_repair_needed(self):

        db = Fake_Db().on('SYSPARTITIONSTAT', [{'number_rows': 100, 'number_deleted_rows': 0}])
        make_sync(db, target_size=100).repair()
        self.assertFalse(any(s.startswith('DELETE') for s in db.sqls('execute')))


    def test_insert_block(self):

        sizes = iter([10, 13])
        db = Fake_Db() \
            .on('SYSPARTITIONSTAT', lambda sql, params: [{'number_rows': next(sizes), 'number_deleted_rows': 0}]) \
            .on('^INSERT INTO "S000000001"."ORDERS"', 3) \
            .on('SELECT COUNT\\(\\*\\) FROM \\(SELECT RRN\\(T\\)', 3)
        t = make_sync(db)

        t.insert_block(5, 9, 3)

        self.assertEqual(t.state.target_size, 13)
        self.assertEqual(t.inserted, 3)
        insert = db.sqls('execute')[db.index('^INSERT INTO "S000000001"."ORDERS"')]
        self.assertIn('ORDER BY IR_SRC_RRN', insert)
        map_insert = next(c for c in db.calls if 'INTO "S000000001"."IRMAP001"' in c[1])
        self.assertEqual(map_insert[2], [10, 5, 9])
        # The size before the insert is saved first
        self.assertLess(db.index('UPDATE "S000000001"."IRSTATE"'), db.index('^INSERT INTO "S000000001"."ORDERS"'))


    def test_insert_block_wrong_order(self):

        sizes = iter([10, 13])
        db = Fake_Db() \
            .on('SYSPARTITIONSTAT', lambda sql, params: [{'number_rows': next(sizes), 'number_deleted_rows': 0}]) \
            .on('^INSERT INTO "S000000001"."ORDERS"', 3) \
            .on('SELECT COUNT\\(\\*\\) FROM \\(SELECT RRN\\(T\\)', 2)
        t = make_sync(db)

        with self.assertRaises(sync.Verify_Exception):
            t.insert_block(5, 9, 3)
        self.assertEqual(t.state.target_size, 10)


    def test_insert_rows_bisect(self):

        t = make_sync(Fake_Db())
        blocks, errors = [], []

        def insert_block(first, last, count):
            if first <= 5 <= last:
                raise Fake_Error('23505', 'duplicate key')
            blocks.append((first, last, count))

        with patch.object(t, 'insert_block', side_effect=insert_block), \
             patch.object(t, 'repair') as repair, \
             patch.object(t, 'add_error', side_effect=lambda rrn, e: errors.append((rrn, e.args[0]))):
            t.insert_rows([1, 2, 3, 5, 8, 9])

        self.assertEqual(errors, [(5, '23505')])
        self.assertEqual(sorted(r for b in blocks for r in range(b[0], b[1] + 1) if r in [1, 2, 3, 5, 8, 9]), [1, 2, 3, 8, 9])
        self.assertTrue(repair.called)


    def test_insert_rows_other_error(self):

        t = make_sync(Fake_Db())
        with patch.object(t, 'insert_block', side_effect=Fake_Error('08S01', 'communication link failure')):
            with self.assertRaises(Fake_Error):
                t.insert_rows([1, 2])


    def test_insert_rows_single_verify_error(self):

        t = make_sync(Fake_Db())
        calls = []

        def insert_block(first, last, count):
            calls.append(count)
            if count > 1:
                raise sync.Verify_Exception('order')

        with patch.object(t, 'insert_block', side_effect=insert_block), patch.object(t, 'repair'):
            t.insert_rows([1, 2, 3])
        self.assertEqual(calls, [3, 1, 2, 1, 1])

        with patch.object(t, 'insert_block', side_effect=sync.Verify_Exception('size')), patch.object(t, 'repair'):
            with self.assertRaises(sync.Verify_Exception):
                t.insert_rows([1])


    def test_stage_range_bisect(self):

        def stage(sql, params):
            if params[0] <= 7 <= params[1]:
                raise Fake_Error('22018', 'invalid character')
            return 1

        db = Fake_Db().on('^INSERT INTO "QTEMP"."IRNEW001"', stage)
        t = make_sync(db)
        errors = []

        with patch.object(t, 'add_error', side_effect=lambda rrn, e: errors.append(rrn)):
            t.stage_range(1, 10)

        self.assertEqual(errors, [7])
        staged = [c[2] for c in db.calls if c[1].startswith('INSERT INTO "QTEMP"') and not (c[2][0] <= 7 <= c[2][1])]
        self.assertEqual(sorted(r for first, last in staged for r in range(first, last + 1)), [1, 2, 3, 4, 5, 6, 8, 9, 10])


    def test_apply_batch(self):

        db = Fake_Db().on('SELECT SRC_RRN, TGT_RRN FROM', [{'src_rrn': 1, 'tgt_rrn': 101}, {'src_rrn': 3, 'tgt_rrn': 103},
                                                         {'src_rrn': 4, 'tgt_rrn': 104}])
        t = make_sync(db)
        deleted = []

        with patch.object(t, 'stage_rrns') as stage_rrns, \
             patch.object(t, 'get_staged', return_value=[1, 2, 4]), \
             patch.object(t, 'update_rows', return_value=[4]) as update_rows, \
             patch.object(t, 'delete_rows', side_effect=lambda rrns, mapped: deleted.append(list(rrns))), \
             patch.object(t, 'insert_rows') as insert_rows:
            t.apply_batch([1, 2, 3, 4])

        stage_rrns.assert_called_once_with([1, 2, 3, 4])
        # 3 doesn't exist anymore, 4 couldn't be updated: both are deleted, 4 is inserted again
        self.assertEqual(deleted, [[3], [4]])
        update_rows.assert_called_once_with([1, 4], {1: 101, 3: 103, 4: 104})
        insert_rows.assert_called_once_with([2, 4])
        self.assertIn('DELETE FROM "QTEMP"."IRNEW001" WHERE IR_SRC_RRN IN (1)', db.sqls('execute'))
        self.assertIn('DELETE FROM "S000000001"."IRCHG001" WHERE SRC_RRN IN (1, 2, 3, 4)', db.sqls('execute'))
        self.assertLess(db.index('DELETE FROM "S000000001"."IRERR001"'), db.index('DELETE FROM "S000000001"."IRCHG001"'))
        self.assertEqual(t.state.rows_applied, 4)


    def test_update_rows(self):

        db = Fake_Db().on('^UPDATE "S000000001"."ORDERS"', 1).on('SELECT RRN\\(T\\) AS RRN', [{'rrn': 101}])
        t = make_sync(db)

        self.assertEqual(t.update_rows([1, 2], {1: 101, 2: 102}), [2])
        update = db.sqls('execute')[0]
        self.assertIn('SET ("ID", "TEXT") = (SELECT S."ID", S."TEXT" FROM', update)
        self.assertIn('WHERE RRN(T) IN (101, 102)', update)


    def test_update_rows_duplicate(self):

        def update(sql, params):
            if '102' in sql:
                raise Fake_Error('23505', 'duplicate key')
            return sql.count(',') - 1

        db = Fake_Db().on('^UPDATE', update)
        t = make_sync(db)

        self.assertEqual(t.update_rows([1, 2], {1: 101, 2: 102}), [2])


    def test_delete_rows(self):

        db = Fake_Db()
        make_sync(db).delete_rows([3, 4], {3: 103, 4: 104})

        # Map entries are deleted after the rows, so a row is never left without its map entry
        self.assertEqual(db.sqls(), ['DELETE FROM "S000000001"."ORDERS" T WHERE RRN(T) IN (103, 104)',
                                     'DELETE FROM "S000000001"."IRMAP001" WHERE SRC_RRN IN (3, 4)'])


    def test_queue_rrns(self):

        db = Fake_Db()
        make_sync(db).queue_rrns({3, 1, 2})
        self.assertIn('(VALUES (1), (2), (3)) V (SRC_RRN)', db.sqls()[0])


    def test_copy(self):

        db = Fake_Db().on('SYSPARTITIONSTAT', [{'number_rows': 25, 'number_deleted_rows': 0}])
        t = make_sync(db, phase=Phase.PREPARED)
        t.settings['batch_size'] = 10
        ranges = []

        with patch.object(t, 'stage_range', side_effect=lambda first, last: ranges.append((first, last))), \
             patch.object(t, 'get_staged', return_value=[1]), \
             patch.object(t, 'insert_rows'):
            t.copy()

        self.assertEqual(ranges, [(1, 10), (11, 20), (21, 25)])
        self.assertEqual(t.state.phase, Phase.COPIED)
        self.assertEqual(t.state.copy_next_rrn, 26)


    def test_copy_continues(self):

        db = Fake_Db()
        t = make_sync(db, phase=Phase.COPYING, copy_next_rrn=11, copy_end_rrn=25)
        t.settings['batch_size'] = 10
        ranges = []

        with patch.object(t, 'stage_range', side_effect=lambda first, last: ranges.append((first, last))), \
             patch.object(t, 'get_staged', return_value=[]), \
             patch.object(t, 'insert_rows'):
            t.copy()

        self.assertEqual(ranges, [(11, 20), (21, 25)])


    def test_read_journal_fails(self):

        t = make_sync(Fake_Db())
        with patch.object(journal.Journal_Reader, 'read', side_effect=journal.Journal_Exception('reorganized')):
            with self.assertRaises(journal.Journal_Exception):
                t.read_journal()
        self.assertEqual(t.state.phase, Phase.FAILED)
        self.assertEqual(t.state.message, 'reorganized')


    def test_catch_up(self):

        t = make_sync(Fake_Db())
        t.settings['catch_up_threshold'] = 100

        with patch.object(t, 'read_journal', return_value=1), \
             patch.object(t, 'get_backlog', side_effect=[5000, 500, 50]), \
             patch.object(t, 'apply_changes') as apply_changes, \
             patch.object(t, 'retry_errors'), \
             patch.object(t, 'get_error_count', return_value=0):
            t.catch_up()

        self.assertEqual(apply_changes.call_count, 3)


    def test_drain(self):

        t = make_sync(Fake_Db())

        with patch.object(t, 'read_journal', side_effect=[3, 0]), \
             patch.object(t, 'retry_errors'), \
             patch.object(t, 'apply_changes', return_value=3), \
             patch.object(t, 'get_backlog', return_value=0), \
             patch.object(t, 'get_error_count', return_value=0):
            t.drain()


    def test_drain_with_errors(self):

        t = make_sync(Fake_Db())

        with patch.object(t, 'read_journal', return_value=0), \
             patch.object(t, 'retry_errors'), \
             patch.object(t, 'apply_changes', return_value=1), \
             patch.object(t, 'get_backlog', return_value=0), \
             patch.object(t, 'get_error_count', side_effect=[2, 1, 1]), \
             patch.object(t, 'get_errors', return_value=[{'src_rrn': 5, 'sql_state': '23505', 'message': 'duplicate key'}]):
            with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'RRN 5: 23505 duplicate key'):
                t.drain()


    def test_verify_counts(self):

        db = Fake_Db().on('COUNT\\(\\*\\) FROM "PRODLIB"', 10).on('COUNT\\(\\*\\) FROM "S000000001"."ORDERS"', 10) \
                      .on('COUNT\\(\\*\\) FROM "S000000001"."IRMAP001"', 9)
        with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'IRMAP001" 9'):
            make_sync(db).verify_counts()


    def test_max_errors(self):

        t = make_sync(Fake_Db())
        t.settings['max_errors'] = 1
        t.add_error(1, Fake_Error('22018', 'bad'))
        with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'More than 1 rows'):
            t.add_error(2, Fake_Error('22018', 'bad'))


    def test_copy_table_phases(self):

        db = Fake_Db()

        for phase, message in [(Phase.NEW, "hasn't been prepared"), (Phase.FAILED, 'has failed')]:
            with patch.object(Table_State, 'load', lambda self, phase=phase: (setattr(self, 'phase', phase), self)[1]):
                with self.assertRaisesRegex(connection.Db_Deployment_Exception, message):
                    sync.copy_table(db, SHADOW, {'no': 1, 'lib': 'PRODLIB', 'name': 'ORDERS'}, SETTINGS)

        with patch.object(Table_State, 'load', lambda self: (setattr(self, 'phase', Phase.DONE), self)[1]), \
             patch.object(sync, 'open_table_sync') as open_table_sync:
            sync.copy_table(db, SHADOW, {'no': 1, 'lib': 'PRODLIB', 'name': 'ORDERS'}, SETTINGS)
        open_table_sync.assert_not_called()



class TestPrepare(unittest.TestCase):


    def test_shadow_sql(self):

        text = '\n'.join([
            'CREATE OR REPLACE TABLE PRODLIB.ORDERS (ID INTEGER);',
            'LABEL ON TABLE "PRODLIB"."ORDERS" IS \'Orders\';',
            'LABEL ON COLUMN prodlib/orders.ID IS \'Id\';',
            'CREATE INDEX DEVLIB.ORDERS1 ON DEVLIB.ORDERS (ID);',
            'SELECT * FROM PRODLIB.CUSTOMERS, XPRODLIB.ORDERS, PRODLIB.ORDERS2;',
        ])

        result = prepare.get_shadow_sql(text, ['devlib', 'prodlib'], ['orders', 'ORDERS1'], SHADOW)

        self.assertEqual(result.split('\n'), [
            'CREATE OR REPLACE TABLE S000000001.ORDERS (ID INTEGER);',
            'LABEL ON TABLE S000000001."ORDERS" IS \'Orders\';',
            'LABEL ON COLUMN S000000001.orders.ID IS \'Id\';',
            'CREATE INDEX S000000001.ORDERS1 ON S000000001.ORDERS (ID);',
            'SELECT * FROM PRODLIB.CUSTOMERS, XPRODLIB.ORDERS, PRODLIB.ORDERS2;',
        ])


    def test_shadow_sql_set_schema(self):
        with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'SET SCHEMA'):
            prepare.get_shadow_sql('SET SCHEMA PRODLIB;\nCREATE OR REPLACE TABLE ORDERS (ID INTEGER);', ['PRODLIB'], ['ORDERS'], SHADOW)


    def make_meta_file(self, deploy_objects=(), tables=()) -> SimpleNamespace:
        objs = do.Deploy_Object_List()
        for o in deploy_objects:
            objs.add_object(o)
        return SimpleNamespace(id=1, deploy_objects=objs, custom_data={'db_deployment': {'tables': list(tables)}},
                               backup_deploy_lib='b000000001', meta_dir=tempfile.gettempdir(), save=Mock())


    def test_replaced_objects(self):

        mf = self.make_meta_file([
            do.Deploy_Object(prod_lib='prodlib', lib='devlib', name='orders', type='file', attribute='sqltable'),
            do.Deploy_Object(prod_lib='prodlib', lib='devlib', name='orderl1', type='file', attribute='lf'),
            do.Deploy_Object(prod_lib='prodlib', lib='devlib', name='orderv2', type='file', attribute='sqlview'),
            do.Deploy_Object(prod_lib='prodlib', lib='devlib', name='ordersi9', type='file', attribute='sqlindex'),
        ])
        dependents = [{'lib': 'PRODLIB', 'name': 'ORDERL1', 'kind': 'lf'}, {'lib': 'PRODLIB', 'name': 'ORDERI1', 'kind': 'index'},
                      {'lib': 'OTHERLIB', 'name': 'ORDERL3', 'kind': 'lf'}, {'lib': 'PRODLIB', 'name': 'ORDERV1', 'kind': 'view'},
                      {'lib': 'PRODLIB', 'name': 'ORDERV2', 'kind': 'view'}]
        table = {'no': 1, 'lib': 'PRODLIB', 'name': 'ORDERS', 'dependents': [('PRODLIB', 'ORDERSI9')]}

        with patch.object(catalog, 'get_dependents', return_value=dependents), patch.object(catalog, 'object_exists', return_value=False):
            replaced = prepare.get_replaced_objects(Fake_Db(), mf, table)

        self.assertEqual([(o.prod_lib, o.name, o.kind, o.origin, o.in_prod) for o in replaced], [
            ('PRODLIB', 'ORDERS', 'table', 'deployment', True),
            ('PRODLIB', 'ORDERL1', 'lf', 'deployment', True),
            ('PRODLIB', 'ORDERI1', 'index', 'generated', True),
            ('OTHERLIB', 'ORDERL3', 'lf', 'source', True),
            ('PRODLIB', 'ORDERV1', 'view', 'view', True),
            ('PRODLIB', 'ORDERSI9', 'index', 'deployment', False),
        ])
        self.assertEqual([o.seq for o in replaced], [0, 1, 2, 3, 4, 5])


    def test_prepare_again_on_changed_config(self):

        db = Fake_Db().on('OBJECT_STATISTICS', [{'n': 1}]).on('SYSTABLES', 1)
        mf = self.make_meta_file()
        table = {'no': 1, 'lib': 'PRODLIB', 'name': 'ORDERS'}
        st = make_state(db, phase=Phase.COPIED)

        with patch.object(Table_State, 'load', lambda s: st), patch.object(state, 'load_objects', return_value=[]), \
             patch.object(prepare, 'remove_shadow_objects') as remove, patch.object(prepare, 'check_table', side_effect=StopIteration):

            self.assertEqual(prepare.prepare_table(db, mf, table, SETTINGS), [])
            remove.assert_not_called()

            with self.assertRaises(StopIteration):
                prepare.prepare_table(db, mf, dict(table, columns={'A': '1'}), SETTINGS)
            remove.assert_called_once()

            # The cut-over has started: it's not prepared again
            st.phase = Phase.SWAPPED
            self.assertEqual(prepare.prepare_table(db, mf, dict(table, columns={'A': '2'}), SETTINGS), [])
            remove.assert_called_once()


    def test_replaced_objects_unsupported(self):

        mf = self.make_meta_file()
        with patch.object(catalog, 'get_dependents', return_value=[{'lib': 'PRODLIB', 'name': 'MQT', 'kind': 'table'}]):
            with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'MQT'):
                prepare.get_replaced_objects(Fake_Db(), mf, {'no': 1, 'lib': 'PRODLIB', 'name': 'ORDERS'})


    def test_check_table(self):

        mf = self.make_meta_file([do.Deploy_Object(prod_lib='prodlib', lib='devlib', name='orders', type='file', attribute='pf')])
        db = Fake_Db() \
            .on('FROM QSYS2.SYSTABLES', [{'table_schema': 'PRODLIB', 'table_name': 'ORDERS', 'system_table_schema': 'PRODLIB',
                                          'system_table_name': 'ORDERS', 'table_type': 'P', 'file_type': 'D'}]) \
            .on('FROM QSYS2.SYSPARTITIONSTAT', 1) \
            .on('FROM QSYS2.SYSTRIGGERS', [{'trigger_schema': 'PRODLIB', 'trigger_name': 'ORDERT1'}])

        with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'PRODLIB.ORDERT1'):
            prepare.check_table(db, mf, 'PRODLIB', 'ORDERS')


    def test_build_pf_from_source(self):

        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        os.makedirs(f"{tmp_dir}/src/prodlib/qddssrc")
        open(f"{tmp_dir}/src/prodlib/qddssrc/orders.pf.file", 'w').close()

        obj = do.Deploy_Object(prod_lib='prodlib', lib='devlib', name='orders', type='file', attribute='pf',
                               source='prodlib/qddssrc/orders.pf.file')
        mf = self.make_meta_file([obj])
        mf.meta_dir = tmp_dir
        db = Fake_Db()

        prepare.build_from_source(db, mf, obj, SHADOW, ['DEVLIB', 'PRODLIB'], ['ORDERS'])

        cmds = db.sqls('cl')
        self.assertIn(f"CPYFRMSTMF FROMSTMF('{os.path.realpath(tmp_dir)}/src/prodlib/qddssrc/orders.pf.file') "
                      "TOMBR('/QSYS.LIB/QTEMP.LIB/IRSRC.FILE/ORDERS.MBR') MBROPT(*REPLACE)", cmds)
        self.assertEqual(cmds[-1], f"CRTPF FILE({SHADOW}/ORDERS) SRCFILE(QTEMP/IRSRC) SRCMBR(ORDERS)")


    def test_build_sql_from_source(self):

        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        os.makedirs(f"{tmp_dir}/src/prodlib/qsqlsrc")
        with open(f"{tmp_dir}/src/prodlib/qsqlsrc/orders.sqltable.file", 'w') as f:
            f.write('CREATE OR REPLACE TABLE PRODLIB.ORDERS (ID INTEGER);')

        obj = do.Deploy_Object(prod_lib='prodlib', lib='devlib', name='orders', type='file', attribute='sqltable',
                               source='prodlib/qsqlsrc/orders.sqltable.file')
        mf = self.make_meta_file([obj])
        mf.meta_dir = tmp_dir
        db = Fake_Db()

        prepare.build_from_source(db, mf, obj, SHADOW, ['DEVLIB', 'PRODLIB'], ['ORDERS'])

        path = f"{tmp_dir}/db_deployment/ORDERS.sqltable.sql"
        with open(path) as f:
            self.assertEqual(f.read(), f'CREATE OR REPLACE TABLE {SHADOW}.ORDERS (ID INTEGER);')
        self.assertEqual(db.sqls('cl')[-1], f"RUNSQLSTM SRCSTMF('{path}') COMMIT(*NONE) NAMING(*SQL) DFTRDBCOL({SHADOW}) ERRLVL(21)")


    def test_start_journaling(self):

        db = Fake_Db().on('OBJECT_STATISTICS', [{'objowner': 'OWNER', 'journaled': 'NO'}])
        st = make_state(db, journal_lib='', journal_name='')

        prepare.start_journaling(db, st)

        self.assertIn(f"STRJRNPF FILE(PRODLIB/ORDERS) JRN({SHADOW}/IRJRN) IMAGES(*AFTER) OMTJRNE(*OPNCLO)", db.sqls('cl'))
        self.assertEqual((st.journal_lib, st.journal_name, st.journal_started), (SHADOW, 'IRJRN', True))


    def test_existing_journal(self):

        db = Fake_Db().on('OBJECT_STATISTICS', [{'journaled': 'YES', 'journal_library': 'APPJRN', 'journal_name': 'JRN1'}])
        st = make_state(db, journal_lib='', journal_name='')

        prepare.start_journaling(db, st)

        self.assertEqual(db.sqls('cl'), [])
        self.assertEqual((st.journal_lib, st.journal_name, st.journal_started), ('APPJRN', 'JRN1', False))



class TestCutover(unittest.TestCase):


    def setUp(self):

        self.db = Fake_Db().on('OBJECT_STATISTICS', []).on('SELECT COUNT', 1)
        self.st = make_state(self.db, phase=Phase.COPIED)
        self.replaced = [
            Replaced_Object(1, 0, 'table', 'deployment', 'PRODLIB', 'ORDERS', True),
            Replaced_Object(1, 1, 'index', 'generated', 'PRODLIB', 'ORDERSI1', True),
            Replaced_Object(1, 2, 'view', 'view', 'PRODLIB', 'ORDERSV', True),
            Replaced_Object(1, 3, 'lf', 'deployment', 'PRODLIB', 'ORDERSL2', False),
        ]
        self.table_sync = Mock()
        for name in ['open', 'catch_up', 'drain', 'verify_counts']:
            getattr(self.table_sync, name).side_effect = lambda name=name: self.db.calls.append(('sync', name, None))
        self.meta_file = SimpleNamespace(id=1, backup_deploy_lib='b000000001', meta_dir=tempfile.gettempdir())

        self.patches = [
            patch.object(Table_State, 'load', lambda s: self.st),
            patch.object(state, 'load_objects', return_value=self.replaced),
            patch.object(sync, 'open_table_sync', return_value=self.table_sync),
            patch.object(cutover, 'finish_new_table', side_effect=lambda *a: self.db.calls.append(('sync', 'finish_new_table', None))),
            patch.object(cutover.os.path, 'isfile', return_value=True),
        ]
        for p in self.patches:
            p.start()


    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()


    def run_cutover(self):
        return cutover.cutover_table(self.db, self.meta_file, {'no': 1, 'lib': 'PRODLIB', 'name': 'ORDERS'}, SETTINGS)


    def test_order(self):

        self.run_cutover()

        db = self.db
        order = [db.index('^catch_up$'),
                 db.index('^ALCOBJ OBJ\\(\\(PRODLIB/ORDERS \\*FILE \\*EXCL\\) \\(PRODLIB/ORDERSI1 \\*FILE \\*EXCL\\) \\(PRODLIB/ORDERSV \\*FILE \\*EXCL\\)\\)'),
                 db.index('^drain$'),
                 db.index('^verify_counts$'),
                 db.index('^finish_new_table$'),
                 db.index('^MOVOBJ OBJ\\(PRODLIB/ORDERSI1\\) OBJTYPE\\(\\*FILE\\) TOLIB\\(B000000001\\)'),
                 db.index('^MOVOBJ OBJ\\(PRODLIB/ORDERS\\) OBJTYPE\\(\\*FILE\\) TOLIB\\(B000000001\\)'),
                 db.index(f'^MOVOBJ OBJ\\({SHADOW}/ORDERS\\) OBJTYPE\\(\\*FILE\\) TOLIB\\(PRODLIB\\)'),
                 db.index(f'^MOVOBJ OBJ\\({SHADOW}/ORDERSI1\\)'),
                 db.index(f'^MOVOBJ OBJ\\({SHADOW}/ORDERSL2\\)'),
                 db.index('^RUNSQLSTM SRCSTMF\\(.*PRODLIB.ORDERSV.view.sql'),
                 db.index('^DLCOBJ OBJ\\(\\(B000000001/ORDERS ')]
        self.assertEqual(order, sorted(order))

        moves = [c for c in db.sqls('cl') if c.startswith('MOVOBJ')]
        self.assertEqual(len(moves), 5)
        self.assertIn('DLCOBJ OBJ((PRODLIB/ORDERSV *FILE *EXCL))', db.sqls('cl'))
        self.assertEqual(self.st.phase, Phase.DONE)
        self.assertTrue(all(o.new_moved for o in self.replaced if o.is_moved()))


    def test_lock_fails(self):

        self.db.rules.insert(0, (re.compile('^ALCOBJ'), Fake_Error('38501', 'CPF1002 Cannot allocate')))
        self.db.rules.insert(0, (re.compile('OBJECT_LOCK_INFO'), [{'job_name': '123456/USER/QZDASOINIT', 'lock_state': '*SHRRD'}]))

        with self.assertRaisesRegex(connection.Db_Deployment_Exception, '123456/USER/QZDASOINIT'):
            self.run_cutover()

        self.assertNotIn('drain', self.db.sqls('sync'))
        self.assertFalse(any(c.startswith('MOVOBJ') for c in self.db.sqls('cl')))


    def test_drain_fails(self):

        self.table_sync.drain.side_effect = connection.Db_Deployment_Exception('duplicate keys')

        with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'duplicate keys'):
            self.run_cutover()

        self.assertFalse(any(c.startswith('MOVOBJ') for c in self.db.sqls('cl')))
        self.assertIn('DLCOBJ OBJ((PRODLIB/ORDERS *FILE *EXCL))', self.db.sqls('cl'))
        self.assertEqual(self.st.phase, Phase.CUTOVER)


    def test_swap_fails(self):

        self.db.rules.insert(0, (re.compile(f'^MOVOBJ OBJ\\({SHADOW}/ORDERSI1\\)'), Fake_Error('38501', 'CPF3202 in use')))

        with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'CPF3202'):
            self.run_cutover()

        moves = [c for c in self.db.sqls('cl') if c.startswith('MOVOBJ')]
        self.assertEqual(moves[-3:], [f'MOVOBJ OBJ(PRODLIB/ORDERS) OBJTYPE(*FILE) TOLIB({SHADOW})',
                                      'MOVOBJ OBJ(B000000001/ORDERS) OBJTYPE(*FILE) TOLIB(PRODLIB)',
                                      'MOVOBJ OBJ(B000000001/ORDERSI1) OBJTYPE(*FILE) TOLIB(PRODLIB)'])
        self.assertFalse(any(o.old_moved or o.new_moved for o in self.replaced))
        self.assertEqual(self.st.phase, Phase.CUTOVER)


    def test_continue_swap(self):

        self.st.phase = Phase.CUTOVER
        for o in self.replaced[:2]:
            o.old_moved = True

        self.run_cutover()

        self.assertNotIn('catch_up', self.db.sqls('sync'))
        moves = [c for c in self.db.sqls('cl') if c.startswith('MOVOBJ')]
        self.assertEqual(moves, [f'MOVOBJ OBJ({SHADOW}/ORDERS) OBJTYPE(*FILE) TOLIB(PRODLIB)',
                                 f'MOVOBJ OBJ({SHADOW}/ORDERSI1) OBJTYPE(*FILE) TOLIB(PRODLIB)',
                                 f'MOVOBJ OBJ({SHADOW}/ORDERSL2) OBJTYPE(*FILE) TOLIB(PRODLIB)'])
        self.assertEqual(self.st.phase, Phase.DONE)


    def test_move_back_old_dependents(self):

        self.st.phase = Phase.CUTOVER
        self.replaced[1].old_moved = True

        self.run_cutover()

        self.assertEqual(self.db.sqls('cl')[0], 'MOVOBJ OBJ(B000000001/ORDERSI1) OBJTYPE(*FILE) TOLIB(PRODLIB)')
        self.assertLess(self.db.index('^MOVOBJ OBJ\\(B000000001/ORDERSI1\\)'), self.db.index('^catch_up$'))


    def test_not_copied(self):

        self.st.phase = Phase.COPYING
        with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'run step db-copy first'):
            self.run_cutover()



class TestCleanup(unittest.TestCase):


    def test_cleanup(self):

        db = Fake_Db().on('OBJECT_STATISTICS', lambda sql, params: [{'journaled': 'YES', 'journal_library': SHADOW, 'journal_name': 'IRJRN'}]
                                                                    if params[1] == '*FILE' else [{'n': 1}])
        db.on('SYSTABLES', 1)
        meta_file = SimpleNamespace(id=1, backup_deploy_lib='b000000001')
        st = make_state(db, phase=Phase.DONE, journal_started=True)

        with patch.object(Table_State, 'load', lambda s: st):
            cleanup.cleanup(db, meta_file, [{'no': 1, 'lib': 'PRODLIB', 'name': 'ORDERS'}])

        cmds = db.sqls('cl')
        self.assertEqual(cmds[0], f"ENDJRNPF FILE(B000000001/ORDERS) JRN({SHADOW}/IRJRN)")
        self.assertEqual(cmds[-1], f"DLTLIB LIB({SHADOW})")
        self.assertIn(f"DLTJRN JRN({SHADOW}/IRJRN)", cmds)


    def test_cleanup_unfinished_cutover(self):

        db = Fake_Db().on('OBJECT_STATISTICS', [{'n': 1}]).on('SYSTABLES', 1)
        st = make_state(db, phase=Phase.SWAPPED)

        with patch.object(Table_State, 'load', lambda s: st):
            with self.assertRaisesRegex(connection.Db_Deployment_Exception, "hasn't been finished"):
                cleanup.cleanup(db, SimpleNamespace(id=1, backup_deploy_lib=None), [{'no': 1, 'lib': 'PRODLIB', 'name': 'ORDERS'}])
        self.assertEqual(db.sqls('cl'), [])



class TestObjects(unittest.TestCase):


    def make_meta_file(self, tables, deploy_objects=()):
        objs = do.Deploy_Object_List()
        for o in deploy_objects:
            objs.add_object(o)
        return SimpleNamespace(id=4711, custom_data={'db_deployment': {'tables': tables}}, deploy_objects=objs,
                               backup_deploy_lib='b000004711', meta_dir=tempfile.gettempdir(), save=Mock())


    def test_libraries(self):
        mf = self.make_meta_file([])
        self.assertEqual(objects.get_shadow_lib(mf), 'S000004711')
        self.assertEqual(objects.get_backup_lib(mf), 'B000004711')


    def test_table_configs(self):

        mf = self.make_meta_file([{'lib': 'prodlib', 'name': 'orders', 'dependents': ['prodlib/ordersi1'], 'batch_size': 10},
                                  {'lib': 'PRODLIB', 'name': 'ITEMS'}])
        tables = objects.get_table_configs(mf)

        self.assertEqual([(t['no'], t['lib'], t['name']) for t in tables], [(1, 'PRODLIB', 'ORDERS'), (2, 'PRODLIB', 'ITEMS')])
        self.assertEqual(tables[0]['dependents'], [('PRODLIB', 'ORDERSI1')])
        self.assertEqual(tables[0]['batch_size'], 10)
        self.assertEqual(objects.get_table_configs(SimpleNamespace(custom_data=None)), [])

        for invalid in [[{'lib': 'PRODLIB'}], [{'lib': 'PRODLIB', 'name': 'TOOLONGNAME1'}], [{'lib': 'A', 'name': 'B'}, {'lib': 'a', 'name': 'b'}],
                        [{'lib': 'A', 'name': 'B', 'dependents': ['C']}]]:
            with self.assertRaises(connection.Db_Deployment_Exception):
                objects.get_table_configs(self.make_meta_file(invalid))


    def test_config_hash(self):

        table = {'no': 1, 'lib': 'PRODLIB', 'name': 'ORDERS', 'columns': {'a': '1'}, 'batch_size': 10}
        st = make_state(Fake_Db(), config_hash=objects.get_config_hash(table))

        st.check_config(dict(table, batch_size=20, columns={'A': '1'}))
        with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'has changed since db-prepare'):
            st.check_config(dict(table, columns={'A': '2'}))
        with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'has changed since db-prepare'):
            st.check_config(dict(table, dependents=[('PRODLIB', 'ORDERSI9')]))


    def test_check_deploy_object(self):

        table = do.Deploy_Object(prod_lib='prodlib', lib='devlib', name='orders', type='file', attribute='sqltable')
        index = do.Deploy_Object(prod_lib='prodlib', lib='devlib', name='ordersi1', type='file', attribute='sqlindex', properties={})
        program = do.Deploy_Object(prod_lib='prodlib', lib='devlib', name='pgm1', type='pgm', attribute='rpgle')
        mf = self.make_meta_file([{'lib': 'PRODLIB', 'name': 'ORDERS'}], [table, index, program])

        self.assertFalse(objects.check_deploy_object(mf, program))
        self.assertFalse(objects.check_deploy_object(mf, index))
        with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'Run step db-cutover first'):
            objects.check_deploy_object(mf, table)

        objects.set_status([index], objects.C_PREPARED)
        with self.assertRaises(connection.Db_Deployment_Exception):
            objects.check_deploy_object(mf, index)
        self.assertTrue(objects.is_db_deployment_object(mf, index))

        objects.set_status([table, index], objects.C_DEPLOYED)
        self.assertTrue(objects.check_deploy_object(mf, table))
        self.assertTrue(objects.check_deploy_object(mf, index))
        self.assertEqual(table.deploy_status, Obj_Status.FINISHED)
        self.assertFalse(objects.is_db_deployment_object(mf, program))



class TestScripts(unittest.TestCase):


    def setUp(self):
        self.script = load_example_script('db_deployment')
        self.db = Fake_Db()
        self.table = do.Deploy_Object(prod_lib='prodlib', lib='devlib', name='orders', type='file', attribute='sqltable')
        self.index = do.Deploy_Object(prod_lib='prodlib', lib='devlib', name='ordersi1', type='file', attribute='sqlindex')
        objs = do.Deploy_Object_List()
        objs.add_object(self.table)
        objs.add_object(self.index)
        self.meta_file = SimpleNamespace(id=1, custom_data={'db_deployment': {'tables': [{'lib': 'PRODLIB', 'name': 'ORDERS'}]}},
                                         deploy_objects=objs, backup_deploy_lib='b000000001', meta_dir=tempfile.gettempdir(), save=Mock())
        self.stage = SimpleNamespace(name='DEPLOY', host='localhost')


    def test_cutover_marks_objects(self):

        replaced = [Replaced_Object(1, 0, 'table', 'deployment', 'PRODLIB', 'ORDERS', True),
                    Replaced_Object(1, 1, 'index', 'deployment', 'PRODLIB', 'ORDERSI1', True),
                    Replaced_Object(1, 2, 'index', 'generated', 'PRODLIB', 'ORDERSI2', True)]

        with patch.object(connection, 'load_config', return_value={}), \
             patch.object(connection, 'connect', return_value=self.db) as connect, \
             patch.object(cutover, 'cutover_table', return_value=replaced) as cutover_table:
            self.script.cutover_tables(self.meta_file, self.stage, None)

        connect.assert_called_once_with({}, 'localhost')
        self.assertEqual(cutover_table.call_args[0][2]['name'], 'ORDERS')
        self.assertEqual(self.table.properties[objects.C_PROPERTY], objects.C_DEPLOYED)
        self.assertEqual(self.index.deploy_status, Obj_Status.FINISHED)
        self.meta_file.save.assert_called()


    def test_no_tables(self):

        self.meta_file.custom_data = {}
        with patch.object(connection, 'connect') as connect:
            self.script.copy_tables(self.meta_file, self.stage, None)
        connect.assert_not_called()


    def test_backup_skips_tables(self):

        backup = load_example_script('backup_old_objects')
        program = do.Deploy_Object(prod_lib='prodlib', lib='devlib', name='pgm1', type='pgm', attribute='rpgle')
        self.meta_file.deploy_objects.add_object(program)
        other_lib = do.Deploy_Object(prod_lib='otherlib', lib='devlib2', name='orders', type='file', attribute='sqltable')
        self.meta_file.deploy_objects.add_object(other_lib)
        objects.set_status([self.index], objects.C_PREPARED)

        self.stage.actions = []
        self.stage.clear_files = False
        action = Mock(processing_step='backup', check_error=True)
        action.sub_actions.add_action.side_effect = lambda a: a
        commands = []

        with patch.object(backup.ibm_i_commands, 'IBM_i_commands') as cmd:
            cmd.return_value.execute_action.side_effect = lambda stage, action: commands.append(action.cmd)
            backup.backup_objects_on_target(self.meta_file, self.stage, action)

        savlib = [c for c in commands if c.startswith('SAVLIB')]
        self.assertEqual(len(savlib), 2)
        self.assertIn('(*INCLUDE pgm1 *pgm)', savlib[0])
        self.assertNotIn('orders', savlib[0])
        self.assertNotIn('ordersi1', savlib[0])
        self.assertIn('SAVLIB LIB(otherlib)', savlib[1])
        self.assertIn('(*INCLUDE orders *file)', savlib[1])
        self.assertNotIn('pgm1', savlib[1])



def ints(text: str) -> list[int]:
    return [int(x) for x in re.findall(r'-?\d+', text)]



class Sim_Db:
    """
    Simulates Db2 for i for the statements of sync.Table_Sync, with rows identified by RRN.

    * Old table: reuses deleted records like REUSEDLT(*YES), journals each change
    * New table: appends (REUSEDLT(*NO)), optional unique key on ID. A multi-row insert or update stops at
      the first duplicate key (no commitment control), a failed insert uses up a record.
    * Rows with TEXT 'BAD' can't be converted
    """

    def __init__(self, unique=True, keep_order=True):
        self.prod, self.prod_size, self.prod_free = {}, 0, []
        self.shadow, self.shadow_size = {}, 0
        self.map, self.changes, self.errors, self.stage = {}, set(), {}, {}
        self.journal, self.seq, self.start_seq = [], 0, 0
        self.unique, self.keep_order = unique, keep_order

    # Changes of the users in the old table

    def log(self, entry_type, rrn, code='R'):
        self.seq += 1
        self.journal.append({'sequence_number': self.seq, 'journal_code': code, 'journal_entry_type': entry_type, 'count_or_rrn': rrn,
                             'receiver_library': 'JRNLIB', 'receiver_name': 'RCV0001'})

    def p_insert(self, row):
        if self.prod_free:
            rrn = self.prod_free.pop(0)
        else:
            self.prod_size += 1
            rrn = self.prod_size
        self.prod[rrn] = row
        self.log('PT', rrn)
        return rrn

    def p_update(self, rrn, row):
        self.prod[rrn] = row
        self.log('UP', rrn)

    def p_delete(self, rrn):
        del self.prod[rrn]
        self.prod_free.append(rrn)
        self.log('DL', rrn)

    def p_clear(self):
        self.prod, self.prod_size, self.prod_free = {}, 0, []
        self.log('CR', 0, code='F')

    # Statements

    def check_unique(self, row, own_rrn=None):
        if self.unique and any(r[0] == row[0] and t != own_rrn for t, r in self.shadow.items()):
            raise Fake_Error('23505', f"duplicate key {row[0]}")

    def stage_rows(self, rrns):
        for rrn in sorted(rrns):
            if rrn in self.prod:
                if self.prod[rrn][1] == 'BAD':
                    raise Fake_Error('22018', 'invalid character')
                self.stage[rrn] = self.prod[rrn]

    def staged_between(self, first, last):
        return [r for r in sorted(self.stage) if first <= r <= last]

    def in_list(self, sql):
        return ints(sql.split('IN (')[-1])

    def execute(self, sql, params=None):

        if sql.startswith(('DROP TABLE', 'CREATE TABLE')) or 'IRSTATE' in sql:
            return 0

        if sql.startswith('INSERT INTO "QTEMP"."IRNEW001"'):
            before = len(self.stage)
            self.stage_rows(range(params[0], params[1] + 1) if 'BETWEEN' in sql else self.in_list(sql))
            return len(self.stage) - before

        if sql.startswith('DELETE FROM "QTEMP"."IRNEW001"'):
            if 'BETWEEN' in sql:
                rrns = self.staged_between(*params)
            elif 'IN (' in sql:
                rrns = self.in_list(sql)
            else:
                rrns = list(self.stage)
            for r in rrns:
                self.stage.pop(r, None)
            return len(rrns)

        if sql.startswith('INSERT INTO "S000000001"."ORDERS"'):
            rrns = self.staged_between(*params)
            if not self.keep_order and len(rrns) > 1:
                rrns = rrns[1:] + rrns[:1]
            for rrn in rrns:
                self.shadow_size += 1
                self.check_unique(self.stage[rrn])
                self.shadow[self.shadow_size] = self.stage[rrn]
            return len(rrns)

        if sql.startswith('INSERT INTO "S000000001"."IRMAP001"'):
            base, first, last = params
            for i, rrn in enumerate(self.staged_between(first, last), start=1):
                assert rrn not in self.map, f"map has {rrn} already"
                self.map[rrn] = base + i
            return 0

        if sql.startswith('DELETE FROM "S000000001"."ORDERS" T WHERE RRN(T) > ?'):
            gone = [t for t in self.shadow if t > params[0]]
        elif sql.startswith('DELETE FROM "S000000001"."ORDERS" T WHERE RRN(T) IN'):
            gone = [t for t in self.in_list(sql) if t in self.shadow]
        elif sql == 'DELETE FROM "S000000001"."ORDERS"':
            gone = list(self.shadow)
        else:
            gone = None
        if gone is not None:
            for t in gone:
                del self.shadow[t]
            return len(gone)

        if sql.startswith('DELETE FROM "S000000001"."IRMAP001" WHERE TGT_RRN > ?'):
            self.map = {s: t for s, t in self.map.items() if t <= params[0]}
            return 0

        if sql.startswith('DELETE FROM "S000000001"."IRMAP001" WHERE SRC_RRN IN'):
            for s in self.in_list(sql):
                self.map.pop(s, None)
            return 0

        if sql.startswith('UPDATE "S000000001"."ORDERS" T SET'):
            source = {t: s for s, t in self.map.items()}
            count = 0
            for t in self.in_list(sql):
                if t in self.shadow:
                    row = self.stage[source[t]]
                    self.check_unique(row, own_rrn=t)
                    self.shadow[t] = row
                    count += 1
            return count

        if sql.startswith('INSERT INTO "S000000001"."IRCHG001" (SRC_RRN) SELECT V.SRC_RRN'):
            self.changes.update(ints(sql.split('(VALUES')[1].split(') V (')[0]))
            return 0

        if sql.startswith('INSERT INTO "S000000001"."IRCHG001" (SRC_RRN) SELECT E.SRC_RRN'):
            self.changes.update(self.errors)
            return 0

        if sql.startswith('DELETE FROM "S000000001"."IRCHG001" WHERE SRC_RRN IN'):
            self.changes -= set(self.in_list(sql))
            return 0

        if sql.startswith('DELETE FROM "S000000001"."IRERR001" WHERE SRC_RRN IN'):
            for s in self.in_list(sql):
                self.errors.pop(s, None)
            return 0

        if sql.startswith('DELETE FROM "S000000001"."IRERR001" WHERE SRC_RRN = ?'):
            self.errors.pop(params[0], None)
            return 0

        if sql.startswith('INSERT INTO "S000000001"."IRERR001"'):
            self.errors[params[0]] = (params[1], params[2])
            return 1

        if sql == 'DELETE FROM "S000000001"."IRMAP001"':
            self.map.clear()
            return 0
        if sql == 'DELETE FROM "S000000001"."IRCHG001"':
            self.changes.clear()
            return 0
        if sql == 'DELETE FROM "S000000001"."IRERR001"':
            self.errors.clear()
            return 0

        raise AssertionError(f"Unexpected statement: {sql}")

    def query(self, sql, params=None):

        if 'SYSPARTITIONSTAT' in sql:
            size = self.shadow_size if params[0] == SHADOW else self.prod_size
            return [{'number_rows': size, 'number_deleted_rows': 0}]

        if sql.startswith('SELECT IR_SRC_RRN FROM "QTEMP"."IRNEW001"'):
            return [{'ir_src_rrn': r} for r in sorted(self.stage)]

        if sql.startswith('SELECT COUNT(*) FROM (SELECT RRN(T) AS IR_RRN'):
            first_rrn, last_rrn, base, first, last = params
            staged = self.staged_between(first, last)
            matched = sum(1 for i, s in enumerate(staged, start=1) if self.shadow.get(base + i) == self.stage[s])
            return [{'n': matched}]

        if sql.startswith('SELECT SRC_RRN, TGT_RRN FROM "S000000001"."IRMAP001" WHERE SRC_RRN IN'):
            return [{'src_rrn': s, 'tgt_rrn': self.map[s]} for s in self.in_list(sql) if s in self.map]

        if sql.startswith('SELECT RRN(T) AS RRN FROM "S000000001"."ORDERS" T WHERE RRN(T) IN'):
            return [{'rrn': t} for t in self.in_list(sql) if t in self.shadow]

        if sql.startswith('SELECT SRC_RRN FROM "S000000001"."IRCHG001" ORDER BY SRC_RRN FETCH FIRST'):
            return [{'src_rrn': r} for r in sorted(self.changes)[:ints(sql.split('FETCH FIRST')[1])[0]]]

        if sql.startswith('SELECT SRC_RRN, SQL_STATE, MESSAGE FROM "S000000001"."IRERR001"'):
            return [{'src_rrn': s, 'sql_state': e[0], 'message': e[1]} for s, e in sorted(self.errors.items())]

        counts = {'"S000000001"."IRCHG001"': lambda: len(self.changes), '"S000000001"."IRERR001"': lambda: len(self.errors),
                  '"PRODLIB"."ORDERS"': lambda: len(self.prod), '"S000000001"."ORDERS"': lambda: len(self.shadow),
                  '"S000000001"."IRMAP001"': lambda: len(self.map)}
        for table, count in counts.items():
            if sql == f"SELECT COUNT(*) FROM {table}":
                return [{'n': count()}]

        raise AssertionError(f"Unexpected query: {sql}")

    def query_value(self, sql, params=None):
        rows = self.query(sql, params)
        return next(iter(rows[0].values())) if rows else None

    def fetch_journal(self, reader):
        after = reader.state.journal_sequence or self.start_seq
        return [e for e in self.journal if e['sequence_number'] > after][:reader.batch_size]



class TestSyncSimulation(unittest.TestCase):
    """Copy and apply while the old table is changed: afterwards the new table has to equal the old one"""


    def setUp(self):
        self.sims = []
        fetch = patch.object(journal.Journal_Reader, 'fetch', lambda reader: self.sim.fetch_journal(reader))
        fetch.start()
        self.addCleanup(fetch.stop)


    def make(self, unique=True, keep_order=True, rows=200, seed=1):

        self.sim = sim = Sim_Db(unique=unique, keep_order=keep_order)
        rnd = random.Random(seed)

        for i in range(1, rows + 1):
            sim.p_insert((i, f"t{i}"))
        for rrn in rnd.sample(range(1, rows + 1), rows // 10):
            sim.p_delete(rrn)
        sim.start_seq = sim.seq

        settings = dict(SETTINGS, batch_size=17, apply_batch_size=7, journal_batch_size=5, catch_up_threshold=3)
        t = sync.Table_Sync(sim, make_state(sim, phase=Phase.PREPARED), mapping.Column_Mapping(
            [column('ID', 'INTEGER'), column('TEXT')], [column('ID', 'INTEGER'), column('TEXT')]), settings)
        return sim, t, rnd


    def work(self, sim: Sim_Db, rnd: random.Random, changes: int) -> None:
        """Changes of the users. IDs stay unique in the old table."""

        for _ in range(changes):
            rrns = sorted(sim.prod)
            ids = {row[0] for row in sim.prod.values()}
            action = rnd.random()

            if action < 0.25 or len(rrns) < 2:
                new_id = rnd.choice([i for i in range(1, 400) if i not in ids])
                sim.p_insert((new_id, f"new{new_id}"))
            elif action < 0.5:
                rrn = rnd.choice(rrns)
                sim.p_update(rrn, (sim.prod[rrn][0], f"upd{rnd.randint(0, 9999)}"))
            elif action < 0.7:
                sim.p_delete(rnd.choice(rrns))
            elif action < 0.85:
                # Two rows swap their keys
                r1, r2 = rnd.sample(rrns, 2)
                (id1, text1), (id2, text2) = sim.prod[r1], sim.prod[r2]
                sim.p_update(r1, (-1, text1))
                sim.p_update(r2, (id1, text2))
                sim.p_update(r1, (id2, text1))
            else:
                # A row takes over the key of a deleted one
                r1, r2 = rnd.sample(rrns, 2)
                key = sim.prod[r1][0]
                sim.p_delete(r1)
                sim.p_update(r2, (key, sim.prod[r2][1]))


    def run_deployment(self, sim, t, rnd):

        original_stage_range = t.stage_range

        def stage_range(first, last):
            self.work(sim, rnd, 3)
            original_stage_range(first, last)

        with patch.object(t, 'stage_range', side_effect=stage_range):
            t.open()
            t.copy()

        self.work(sim, rnd, 40)
        t.catch_up()
        self.work(sim, rnd, 40)
        t.catch_up()
        t.drain()
        t.verify_counts()


    def assert_equal(self, sim):
        self.assertEqual(sorted(sim.shadow.values()), sorted(sim.prod.values()))
        self.assertEqual(sorted(sim.map), sorted(sim.prod))
        for src, tgt in sim.map.items():
            self.assertEqual(sim.shadow[tgt], sim.prod[src])


    def test_unique_key(self):
        for seed in range(25):
            with self.subTest(seed=seed):
                sim, t, rnd = self.make(seed=seed)
                self.run_deployment(sim, t, rnd)
                self.assert_equal(sim)
                self.assertEqual(t.state.phase, Phase.COPIED)


    def test_without_key(self):
        for seed in range(10):
            with self.subTest(seed=seed):
                sim, t, rnd = self.make(unique=False, seed=seed)
                self.run_deployment(sim, t, rnd)
                self.assert_equal(sim)


    def test_insert_order_not_kept(self):
        for seed in range(5):
            with self.subTest(seed=seed):
                sim, t, rnd = self.make(keep_order=False, seed=seed)
                self.run_deployment(sim, t, rnd)
                self.assert_equal(sim)


    def test_resume_after_interrupted_insert(self):
        """The job ended after rows have been inserted, before they have been mapped: they are removed again"""

        sim, t, rnd = self.make(rows=50)
        t.open()
        original_execute = sim.execute

        def execute(sql, params=None):
            if sql.startswith('INSERT INTO "S000000001"."IRMAP001"') and t.state.copy_next_rrn > 20:
                raise ConnectionError('job ended')
            return original_execute(sql, params)

        with patch.object(sim, 'execute', side_effect=execute):
            with self.assertRaises(ConnectionError):
                t.copy()

        self.assertGreater(len(sim.shadow), len(sim.map))

        t2 = sync.Table_Sync(sim, t.state, t.mapping, t.settings)
        t2.open()
        self.assertEqual(len(sim.shadow), len(sim.map))
        t2.copy()
        t2.catch_up()
        t2.drain()

        self.assert_equal(sim)


    def test_bad_row_is_fixed(self):

        sim, t, rnd = self.make(rows=30)
        bad = sorted(sim.prod)[5]
        sim.prod[bad] = (sim.prod[bad][0], 'BAD')

        t.open()
        t.copy()
        self.assertEqual(list(sim.errors), [bad])

        with self.assertRaisesRegex(connection.Db_Deployment_Exception, f'RRN {bad}: 22018'):
            t.drain()

        # The row is corrected by a user
        sim.p_update(bad, (sim.prod[bad][0], 'good'))
        t.drain()

        self.assert_equal(sim)


    def test_duplicate_in_old_data(self):
        """The new table has a unique key which the old data violates"""

        sim, t, rnd = self.make(rows=30)
        first, second = sorted(sim.prod)[:2]
        sim.prod[second] = (sim.prod[first][0], 'same key')

        t.open()
        t.copy()
        with self.assertRaisesRegex(connection.Db_Deployment_Exception, "1 rows .* can't be applied"):
            t.drain()


    def test_cleared_table(self):

        sim, t, rnd = self.make(rows=40)

        t.open()
        t.copy()
        sim.p_update(sorted(sim.prod)[0], (1, 'changed before clear'))
        sim.p_clear()
        sim.p_insert((1, 'after clear'))
        t.drain()

        self.assert_equal(sim)
        self.assertEqual(list(sim.shadow.values()), [(1, 'after clear')])



if __name__ == '__main__':
    unittest.main()



class TestSystemNames(unittest.TestCase):


    def test_invalid_names(self):

        for name in ['A) X(', 'LIB/X', 'A B', '"X"', '1ABC', '', 'ABCDEFGHIJK', "A'B"]:
            with self.assertRaises(connection.Db_Deployment_Exception, msg=name):
                objects.check_system_name(name, 'test')


    def test_valid_names(self):

        self.assertEqual(objects.check_system_name('orders', 'test'), 'ORDERS')
        self.assertEqual(objects.check_system_name('$ORD#1', 'test'), '$ORD#1')
        self.assertEqual(objects.check_system_name('@X_Y.Z', 'test'), '@X_Y.Z')


    def test_dependents(self):

        self.assertEqual(objects.split_object_name('prodlib/orders9'), ('PRODLIB', 'ORDERS9'))

        for name in ['PRODLIB/A) X(', 'PROD LIB/ORDERS']:
            with self.assertRaises(connection.Db_Deployment_Exception, msg=name):
                objects.split_object_name(name)



def load_example_script(name: str):
    """The templates, not the local scripts of an installation"""

    path = os.path.join(I_RELEASER_DIR, 'scripts', 'examples', f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"example_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



class TestExampleScripts(unittest.TestCase):
    """Commands of the example scripts for a deployment with a table of the DB deployment"""


    def setUp(self):

        from types import SimpleNamespace
        from unittest.mock import patch

        self.objects = do.Deploy_Object_List()

        for name, attribute, obj_type in [('orders', 'sqltable', 'file'), ('orders1', 'sqlindex', 'file'), ('prog', 'rpgle', 'pgm')]:
            self.objects.add_object(do.Deploy_Object(level=1, prod_lib='prodlib', lib='devlib', name=name, type=obj_type, attribute=attribute, properties={}))

        self.meta_file = SimpleNamespace(
            id=123, custom_data={'db_deployment': {'tables': [{'lib': 'PRODLIB', 'name': 'ORDERS'}]}}, deploy_objects=self.objects,
            main_deploy_lib='d000000123', backup_deploy_lib='b000000123', remote_deploy_lib='r000000123', meta_dir='/tmp/meta/1', save=lambda: None
        )

        self.stage = SimpleNamespace(name='DEPLOY', clear_files=False, lib_replacement_necessary=False, lib_mapping={}, actions=None)
        self.action = SimpleNamespace(processing_step='step', check_error=True, sub_actions=da_list())
        self.commands = []

        def execute_action(_, stage, action, continue_run=True):
            self.commands.append(action.cmd)

        self.patch = patch('modules.ibm_i_commands.IBM_i_commands.execute_action', execute_action)
        self.patch.start()


    def tearDown(self):
        self.patch.stop()


    def set_replaced(self) -> None:
        """Like the cut-over"""

        for obj in self.objects:
            if obj.name.startswith('orders'):
                obj.properties[objects.C_PROPERTY] = objects.C_DEPLOYED


    def get_commands(self, start: str) -> str:
        return ' '.join(cmd for cmd in self.commands if cmd.startswith(start))


    def test_save_leaves_out_tables_of_the_db_deployment(self):

        self.objects[1].properties[objects.C_PROPERTY] = objects.C_PREPARED

        load_example_script('save_objects').save_objects_to_savf(self.meta_file, self.stage, self.action)

        save = self.get_commands('SAVLIB')

        self.assertIn('*INCLUDE prog *pgm', save)
        self.assertNotIn('orders', save)


    def test_restore_leaves_out_replaced_tables(self):

        self.set_replaced()

        load_example_script('target_deployment').restore_objects_on_target(self.meta_file, self.stage, self.action)

        restore = self.get_commands('RSTLIB')

        self.assertIn('*INCLUDE prog *pgm', restore)
        self.assertNotIn('orders', restore)
        self.assertNotIn('prouzalib', ' '.join(self.commands).lower())


    def test_restore_before_the_cut_over_fails(self):

        with self.assertRaisesRegex(connection.Db_Deployment_Exception, 'Run step db-cutover first'):
            load_example_script('target_deployment').restore_objects_on_target(self.meta_file, self.stage, self.action)


    def test_library_mapping(self):

        self.set_replaced()
        self.stage.lib_replacement_necessary = True
        self.stage.lib_mapping = {'prodlib': 'testlib'}

        load_example_script('target_deployment').restore_objects_on_target(self.meta_file, self.stage, self.action)

        self.assertIn('RSTLIB(testlib)', self.get_commands('RSTLIB'))


    def test_object_names_are_not_escaped(self):

        self.objects[2].name = '$prog'

        self.set_replaced()
        load_example_script('target_deployment').restore_objects_on_target(self.meta_file, self.stage, self.action)

        self.assertIn('(*INCLUDE $prog *pgm)', self.get_commands('RSTLIB'))



def da_list():
    from modules import deploy_action
    return deploy_action.Deploy_Action_List_list()
