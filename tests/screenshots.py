"""
Screenshots of the documentation (README.md, docs/img/) from test data.

Runs the real web app of tests/web_server.py with own workflows and deployments, and takes the pictures with Playwright
(docs/features/web-ui-browser-tests.md, requirement 6). Renew them after a change of the layout:

    .venv/bin/python tests/screenshots.py              # writes docs/img/*.png
    .venv/bin/python tests/screenshots.py --out /tmp/x  # somewhere else, to compare first

Needs Playwright and its Chromium, like the browser tests.
No real names or paths: users and workflows come from this file, the directory of the test copy is replaced.
"""
import argparse, os, shutil, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web_server import ROOT_DIR, Web_Server


# The files of README.md
SCREENSHOTS = ['deployment', 'workflow-list', 'parallel', 'details', 'history', 'history-detail',
               'object-list', 'http-token', 'rollback', 'rollback-started']

VIEWPORT = {'width': 1440, 'height': 900}
SCALE = 1.5
SHOWN_DIRECTORY = '/home/ireleaser/i-releaser'

ALL = ['admin', 'read', 'start workflow', 'run', 'cancel workflow', 'edit-custom-data', 'change check error']
USERS = {'anna': {'roles': [], 'permissions': {'general': ALL, 'workflows': {}}}}


def step(name: str, command: str) -> dict:
    return {'processing_step': name, 'environment': 'PASE', 'execute': command, 'check_error': True}


WORKFLOWS = {
    'erp_release': {
        'name': 'erp_release',
        'default_project': 'erp',
        'editable_fields': ['$.ticket'],
        'create_fields': ['$.ticket', '$.commit'],
        'step_action': [
            step('prepare', "echo 'Prepare release'"),
            step('checkout', 'echo git checkout 4f2a9c1'),
            step('compile', "echo 'CRTBNDRPG PGM(DEVLIB/ORD001) SRCSTMF(src/ord001.rpgle)'; echo 'CRTSRVPGM SRVPGM(DEVLIB/ORDSRV)'"),
            step('deploy_test', "echo 'RSTOBJ OBJ(*ALL) SAVLIB(PRODLIB) DEV(*SAVF) RSTLIB(TESTLIB)'"),
            step('deploy_prod', "echo 'RSTOBJ OBJ(*ALL) SAVLIB(PRODLIB) DEV(*SAVF) RSTLIB(PRODLIB)'"),
        ],
        'stages': [
            {'name': 'START', 'next_stages': ['BUILD'], 'host': 'localhost', 'processing_steps': ['prepare']},
            {'name': 'BUILD', 'description': 'Builds the objects', 'next_stages': ['TEST'], 'host': 'localhost', 'processing_steps': ['checkout', 'compile']},
            {'name': 'TEST', 'next_stages': ['PROD'], 'host': 'localhost', 'processing_steps': ['deploy_test']},
            {'name': 'PROD', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['deploy_prod']},
            {'name': 'END', 'description': 'Finished'},
        ],
    },
    'parallel_release': {
        'name': 'parallel_release',
        'default_project': 'test',
        'parallel_deployment_execution_allowed': True,
        'step_action': [step('pre', "echo 'Pre script'"), step('copy', "echo 'copy objects'")],
        'stages': [
            {'name': 'START', 'next_stages': ['STAGE 2.1', 'STAGE 2.2'], 'host': 'localhost', 'processing_steps': ['pre']},
            {'name': 'STAGE 2.1', 'next_stages': ['STAGE 3'], 'host': 'localhost', 'processing_steps': ['pre', 'copy']},
            {'name': 'STAGE 2.2', 'next_stages': ['STAGE 3'], 'host': 'localhost', 'processing_steps': ['pre', 'copy']},
            {'name': 'STAGE 3', 'next_stages': ['END'], 'after_stages_finished': ['STAGE 2.1', 'STAGE 2.2'], 'host': 'localhost', 'processing_steps': ['pre']},
            {'name': 'END', 'description': 'Finished'},
        ],
    },
    'rollback_deployment': {
        'name': 'rollback_deployment',
        'default_project': 'erp',
        'parallel_deployment_execution_allowed': True,
        'editable_fields': ['$.version'],
        'create_fields': ['$.project', '$.version'],
        'step_action': [step('restore', "echo 'Restore the saved objects'")],
        'stages': [
            {'name': 'START', 'next_stages': ['ROLLBACK'], 'host': 'localhost', 'processing_steps': ['restore']},
            {'name': 'ROLLBACK', 'description': 'Restores the objects of the deployment', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['restore']},
            {'name': 'END', 'description': 'Finished'},
        ],
    },
}

OBJECTS = [
    # level, prod_lib, lib, name, type, attribute
    (1, 'prodlib', 'devlib', 'orders', 'file', 'pf'),
    (1, 'prodlib', 'devlib', 'customer', 'file', 'pf'),
    (2, 'prodlib', 'devlib', 'ordersl1', 'file', 'lf'),
    (2, 'prodlib', 'devlib', 'orderd', 'file', 'dspf'),
    (3, 'prodlib', 'devlib', 'ord001', 'pgm', 'rpgle'),
    (3, 'prodlib', 'devlib', 'ord002', 'pgm', 'sqlrpgle'),
    (3, 'prodsrv', 'devsrv', 'ordsrv', 'srvpgm', 'rpgle'),
    (4, 'prodlib', 'devlib', 'ordmenu', 'pgm', 'clle'),
]


# Shown on every page of the test server, and the directory of the test copy
CLEAN_PAGE = """(directory) => {
    document.querySelectorAll('.alert-danger').forEach((alert) => {
        if (alert.textContent.includes('Local debugging mode')) alert.remove();
    });
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
        if (walker.currentNode.nodeValue.includes(directory)) {
            walker.currentNode.nodeValue = walker.currentNode.nodeValue.split(directory).join('%s');
        }
    }
}""" % SHOWN_DIRECTORY



def create_server() -> Web_Server:

    server = Web_Server(workflows=WORKFLOWS, users=USERS, log_level='INFO')

    # The rollback button of docs/scripts.md#scripts-of-custom-templates
    example = os.path.join(ROOT_DIR, 'docs', 'examples', 'rollback')
    shutil.copy(os.path.join(example, 'deployment_status.html'), os.path.join(server.web_dir, 'templates', 'custom_templates', 'deployment_status.html'))
    os.makedirs(os.path.join(server.web_dir, 'static', 'custom'), exist_ok=True)
    shutil.copy(os.path.join(example, 'rollback.js'), os.path.join(server.web_dir, 'static', 'custom', 'rollback.js'))

    with open(os.path.join(server.web_dir, 'etc', 'global_cfg.py'), 'a') as f:
        f.write("\nC_DEFAULT_PROJECT = 'erp'\n")

    return server.start()



def create_data(server: Web_Server) -> dict:
    """Deployments for the pictures. Returns their ids."""

    anna = server.client('anna')

    # erp 1: finished (rollback)
    finished = anna.create_deployment('erp_release', {'ticket': 'ERP-128', 'commit': '9be03d7'})
    anna.finish_deployment(finished, stages=('START', 'BUILD', 'TEST', 'PROD'))

    # erp 2: built, waits for the test stage
    current = anna.create_deployment('erp_release', {'ticket': 'ERP-142', 'commit': '4f2a9c1'})
    db = sqlite3.connect(os.path.join(server.directory, 'var', 'app.sqlite'), timeout=10)
    for level, prod_lib, lib, name, type, attribute in OBJECTS:
        db.execute("""INSERT INTO deploy_objects (meta_file_id, level, prod_lib, lib, name, type, attribute, deploy_status, ready, properties)
                      VALUES (?, ?, ?, ?, ?, ?, ?, 'new', 1, '{}')""", (current, level, prod_lib, lib, name, type, attribute))
    db.commit()
    db.close()

    for stage in ['START', 'BUILD']:
        assert anna.run_stage(current, stage)[0] == 200
        anna.wait_for_stage(current, stage)

    anna.post(f"/api/set_source_ready_4_deployment/{current}", {'lib': 'devlib', 'name': 'ordmenu', 'type': 'pgm', 'checked': False})

    # test 1: parallel stages, one of them finished
    parallel = anna.create_deployment('parallel_release')
    for stage in ['START', 'STAGE 2.2']:
        assert anna.run_stage(parallel, stage)[0] == 200
        anna.wait_for_stage(parallel, stage)

    # A token for the user page
    anna.post('/api/generate_user_key')

    return {'finished': finished, 'current': current, 'parallel': parallel}



def make_screenshots(out_dir: str, browser=None) -> list[str]:
    """Takes all screenshots. Returns the written files.

    `browser`: a Chromium of Playwright which is already running (the browser tests). Without it one is started.
    """

    if browser is None:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            chromium = playwright.chromium.launch()
            try:
                return make_screenshots(out_dir, chromium)
            finally:
                chromium.close()

    os.makedirs(out_dir, exist_ok=True)
    written = []

    server = create_server()

    try:
        ids = create_data(server)
        origin = f"http://127.0.0.1:{server.port}"

        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=SCALE)
        context.add_cookies([{'name': 'session_id', 'value': server.client('anna').session_id, 'url': origin}])
        page = context.new_page()

        def open_page(path: str):
            page.goto(origin + path, wait_until='networkidle')
            page.evaluate(CLEAN_PAGE, server.directory)

        def save(name: str, target=None, height: int|None=None):
            file = os.path.join(out_dir, f"{name}.png")
            if target is not None:
                target.screenshot(path=file)
            else:
                page.screenshot(path=file, clip={'x': 0, 'y': 0, 'width': VIEWPORT['width'], 'height': height or VIEWPORT['height']})
            written.append(file)

        def popup():
            page.wait_for_selector('.swal2-popup', state='visible')
            page.wait_for_timeout(400)
            # Logs contain the directory of the test copy too
            page.evaluate(CLEAN_PAGE, server.directory)
            return page.locator('.swal2-popup')

        def close_popup():
            page.evaluate("Swal.close()")
            page.wait_for_timeout(300)

        current = f"/show_details/{ids['current']}"

        open_page(current)
        save('deployment', height=620)

        page.locator('img[title="Open details"]').nth(1).click()
        page.wait_for_selector('.swal2-popup table.stage_info')
        save('details', popup())
        close_popup()

        page.locator('a[title="Show history"]').click()
        save('history', popup())
        close_popup()

        page.locator('img[onclick^="showLog"]').last.click()
        save('history-detail', popup())
        close_popup()

        table = page.locator('.bootstrap-table')
        table.scroll_into_view_if_needed()
        save('object-list', table)

        open_page('/workflows')
        save('workflow-list', height=520)

        open_page(f"/show_details/{ids['parallel']}")
        save('parallel', page.locator('#flow_html_container'))

        open_page('/user')
        save('http-token', height=360)

        open_page(f"/show_details/{ids['finished']}")
        page.locator('[data-rollback]').click()
        popup()
        save('rollback', height=640)

        with page.expect_navigation():
            page.locator('.swal2-confirm').click()
        page.wait_for_load_state('networkidle')
        page.evaluate(CLEAN_PAGE, server.directory)
        page.locator('details', has_text='Show custom data').evaluate("details => details.open = true")
        save('rollback-started', height=620)

        context.close()
    finally:
        server.close()

    return written



def main() -> None:

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', default=os.path.join(ROOT_DIR, 'docs', 'img'), help='Directory of the pictures (default: docs/img)')
    args = parser.parse_args()

    for file in make_screenshots(args.out):
        print(file)



if __name__ == '__main__':
    main()
