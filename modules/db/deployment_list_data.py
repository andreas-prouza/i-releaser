"""
Queries of the lists of the web app (docs/features/web-ui-lists.md): open deployments per project,
the current stage of each deployment of a list, and the objects page by page.
"""
from modules.db import app_sqlite


CLOSED = ('finished', 'canceled')

# The stage of a deployment the list shows: the first which applies
STAGE_ORDER = ['failed', 'running', 'queued', 'ready']
RUNNING = ('in process', 'in preperation', 'prepare')



def _workflow_filter(column: str, workflows: list[str]|None) -> tuple[str, list]:
    """SQL and parameters which limit to deployments of readable workflows (None: all)"""

    if workflows is None:
        return '', []
    if not workflows:
        return ' AND 0', []
    return f" AND {column} IN (SELECT meta_file_id FROM workflow_definitions WHERE name IN ({', '.join('?' * len(workflows))}))", list(workflows)



def get_open_counts(workflows: list[str]|None=None) -> dict:
    """Project -> number of its deployments which are not finished or canceled"""

    where, params = _workflow_filter('mf.id', workflows)

    with app_sqlite.get_db_connection() as conn:
        rows = conn.execute(f"""SELECT dv.project, count(*) FROM meta_files mf
                                JOIN deploy_versions dv ON dv.id = mf.deploy_version_id
                                WHERE mf.status NOT IN (?, ?) {where}
                                GROUP BY dv.project""", (*CLOSED, *params)).fetchall()

    return {row[0]: row[1] for row in rows}



def get_current_stages(project: str) -> dict:
    """
    Meta file id -> {'name', 'status'} of the stage the deployment waits for: failed, else running,
    else queued (processing service), else ready. With parallel stages the first one. One query for the whole list.
    """

    with app_sqlite.get_db_connection() as conn:
        stages = conn.execute("""SELECT s.meta_file_id, s.id, s.name, s.status FROM stages s
                                 JOIN meta_files mf ON mf.id = s.meta_file_id
                                 JOIN deploy_versions dv ON dv.id = mf.deploy_version_id
                                 WHERE dv.project = ? AND mf.status NOT IN (?, ?)
                                 ORDER BY s.id""", (project, *CLOSED)).fetchall()
        queued = {row[0] for row in conn.execute("""SELECT j.stage_id FROM processing_jobs j
                                                    JOIN meta_files mf ON mf.id = j.meta_file_id
                                                    JOIN deploy_versions dv ON dv.id = mf.deploy_version_id
                                                    WHERE dv.project = ? AND j.status = 'queued'""", (project,)).fetchall()}

    candidates = {}
    for meta_file_id, stage_id, name, status in stages:
        state = 'queued' if stage_id in queued else 'running' if status in RUNNING else status
        if state not in STAGE_ORDER:
            continue
        rank = STAGE_ORDER.index(state)
        best = candidates.get(meta_file_id)
        if best is None or rank < best[0]:
            candidates[meta_file_id] = (rank, {'name': name, 'status': 'queued' if state == 'queued' else status})

    return {meta_file_id: value for meta_file_id, (_, value) in candidates.items()}



# Columns of the object list which can be sorted, and their SQL
OBJECT_SORT = {
    'project': 'project',
    'prod_lib': 'prod_lib',
    'name': 'name',
    'type': 'type',
    'attribute': 'attribute',
    'last_deployment': 'last_deployment',
    'deployments': 'deployments',
}
# Filters: exact value (select) or part of the value (text)
OBJECT_FILTER_EXACT = ['project', 'type', 'attribute']
OBJECT_FILTER_PART = ['prod_lib', 'name']
MAX_LIMIT = 500



def get_objects(search: str='', filters: dict|None=None, sort: str|None=None, order: str='desc', offset: int=0, limit: int=25,
                workflows: list[str]|None=None) -> dict:
    """
    One page of the objects of all deployments, one row per object (project, library, name, type, attribute).

    Returns:
        dict: total (all rows which match), rows
    """

    where, params = _workflow_filter('do.meta_file_id', workflows)

    for column, value in (filters or {}).items():
        if value in (None, ''):
            continue
        if column in OBJECT_FILTER_EXACT:
            where += f" AND {'mf.project' if column == 'project' else 'do.' + column} = ?"
            params.append(str(value))
        elif column in OBJECT_FILTER_PART:
            where += f" AND do.{column} LIKE ? ESCAPE '\\'"
            params.append('%' + _escape_like(str(value)) + '%')

    if search:
        where += " AND (do.name LIKE ? ESCAPE '\\' OR do.prod_lib LIKE ? ESCAPE '\\' OR mf.project LIKE ? ESCAPE '\\')"
        params += ['%' + _escape_like(search) + '%'] * 3

    sort_sql = OBJECT_SORT.get(sort or '', 'last_deployment')
    order_sql = 'ASC' if (order or '').lower() == 'asc' else 'DESC'
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))

    grouped = f"""SELECT mf.project AS project, do.prod_lib AS prod_lib, do.name AS name, do.type AS type, do.attribute AS attribute,
                         DATETIME(max(mf.create_time)) AS last_deployment, count(*) AS deployments
                  FROM deploy_objects do
                  JOIN meta_files mf ON mf.id = do.meta_file_id
                  WHERE 1=1 {where}
                  GROUP BY mf.project, do.prod_lib, do.name, do.type, do.attribute"""

    with app_sqlite.get_db_connection() as conn:
        total = conn.execute(f"SELECT count(*) FROM ({grouped})", params).fetchone()[0]
        rows = conn.execute(f"{grouped} ORDER BY {sort_sql} {order_sql}, project, prod_lib, name, type, attribute LIMIT ? OFFSET ?",
                            (*params, limit, offset)).fetchall()

    return {'total': total, 'rows': [dict(row) for row in rows]}



def get_object_values(column: str, workflows: list[str]|None=None) -> list[str]:
    """The values of a column of the object list, for the select of its filter"""

    if column not in OBJECT_FILTER_EXACT:
        return []

    where, params = _workflow_filter('do.meta_file_id', workflows)
    sql_column = 'mf.project' if column == 'project' else f"do.{column}"

    with app_sqlite.get_db_connection() as conn:
        rows = conn.execute(f"""SELECT DISTINCT {sql_column} FROM deploy_objects do JOIN meta_files mf ON mf.id = do.meta_file_id
                                WHERE {sql_column} IS NOT NULL {where} ORDER BY 1""", params).fetchall()

    return [row[0] for row in rows]



def get_object_history(project: str, prod_lib: str, name: str, type: str, attribute: str, workflows: list[str]|None=None) -> list[dict]:
    """The deployments of an object, newest first"""

    where, params = _workflow_filter('do.meta_file_id', workflows)

    with app_sqlite.get_db_connection() as conn:
        rows = conn.execute(f"""SELECT do.meta_file_id, mf.project, dv.version, wd.name AS workflow, mf.status AS deployment_status,
                                       do.deploy_status AS object_status, mf.create_time, do.lib, do.source
                                FROM deploy_objects do
                                JOIN meta_files mf ON mf.id = do.meta_file_id
                                LEFT JOIN deploy_versions dv ON dv.id = mf.deploy_version_id
                                LEFT JOIN workflow_definitions wd ON wd.meta_file_id = mf.id
                                WHERE mf.project = ? AND do.prod_lib = ? AND do.name = ? AND do.type = ? AND do.attribute = ? {where}
                                ORDER BY do.meta_file_id DESC""", (project, prod_lib, name, type, attribute, *params)).fetchall()

    return [dict(row) for row in rows]



def _escape_like(value: str) -> str:
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
