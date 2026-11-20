"""
Layout of the stage flow of the deployment page (docs/features/web-ui-deployment-page.md#stage-flow).

Input: the stages of a deployment as dicts with `id`, `name`, `next` (names of the next stages), `status`,
and optional `waiting_for`. Output: the column and row of each stage, the size of the grid, and the connections
as SVG paths in pixels. The template draws the stages in a CSS grid with the sizes below and the connections
as one SVG over it. Nothing here is HTML.

* Column: the longest way from START. A connection back to an earlier stage doesn't change the columns.
* Row: the first next stage stays in the row of its stage, each other next stage starts a new row below.
* Each stage is placed once, also if several stages lead to it.
* Connections fork in the gap after their stage and join in the gap before the next one, never across a stage.
  A connection which skips columns runs in a row which is free there.
"""
from dataclasses import dataclass, field


COL_WIDTH = 148       # a stage: circle, name and status below it
COL_GAP = 56
ROW_HEIGHT = 84
ROW_GAP = 12
CIRCLE = 32           # diameter of the circle of a stage
CIRCLE_TOP = 6        # its distance from the top of the cell
MARGIN = COL_GAP // 2  # room left of the first column for connections back to it

START = 'START'



@dataclass
class Layout:
    nodes: list = field(default_factory=list)         # dicts: the stage, plus col, row, number
    connections: list = field(default_factory=list)   # dicts: d (SVG path), kind ('out'|'in'), done, back, source, target
    columns: int = 0
    rows: int = 0

    @property
    def width(self) -> int:
        return MARGIN + self.columns * COL_WIDTH + max(self.columns - 1, 0) * COL_GAP + MARGIN

    @property
    def height(self) -> int:
        return self.rows * ROW_HEIGHT + max(self.rows - 1, 0) * ROW_GAP

    def css(self) -> dict:
        """Sizes for the grid of the template"""
        return {'columns': self.columns, 'rows': self.rows, 'col_width': COL_WIDTH, 'col_gap': COL_GAP,
                'row_height': ROW_HEIGHT, 'row_gap': ROW_GAP, 'margin': MARGIN, 'width': self.width, 'height': self.height}



def cell_left(col: int) -> float:
    return MARGIN + col * (COL_WIDTH + COL_GAP)


def center_x(col: int) -> float:
    return cell_left(col) + COL_WIDTH / 2


def center_y(row: int) -> float:
    return row * (ROW_HEIGHT + ROW_GAP) + CIRCLE_TOP + CIRCLE / 2


def gap_after(col: int) -> float:
    """x in the middle of the gap right of a column (col -1: left of the first column)"""
    return cell_left(col) + COL_WIDTH + COL_GAP / 2



def path(points: list) -> str:
    return 'M ' + ' L '.join(f"{x:g} {y:g}" for x, y in points)



def get_layout(stages: list[dict], start: str = START) -> Layout:

    by_name = {stage['name']: stage for stage in stages}
    next_of = {name: [n for n in dict.fromkeys(stage.get('next') or []) if n in by_name] for name, stage in by_name.items()}

    if not by_name:
        return Layout()

    first = start if start in by_name else stages[0]['name']

    # Depth first from START: a connection to a stage on the current way is a connection back
    back = set()
    visited = set()
    post_order = []

    def walk(name: str, way: set) -> None:
        visited.add(name)
        way.add(name)
        for n in next_of[name]:
            if n in way:
                back.add((name, n))
            elif n not in visited:
                walk(n, way)
        way.discard(name)
        post_order.append(name)

    walk(first, set())
    # Stages which can't be reached from START are shown too
    unreachable = [name for name in by_name if name not in visited]
    for name in unreachable:
        if name not in visited:
            walk(name, set())

    forward = {name: [n for n in next_of[name] if (name, n) not in back] for name in by_name}

    # Columns: the longest way, in topological order (reverse post order)
    col = {name: 0 for name in by_name}
    for name in reversed(post_order):
        for n in forward[name]:
            col[n] = max(col[n], col[name] + 1)

    # Rows: the first next stage stays in the row
    row = {}
    next_row = [0]

    def place(name: str, r: int) -> None:
        row[name] = r
        first_next = True
        for n in forward[name]:
            if n in row:
                continue
            if first_next:
                first_next = False
                place(n, r)
            else:
                next_row[0] += 1
                place(n, next_row[0])

    place(first, 0)
    for name in by_name:
        if name not in row:
            next_row[0] += 1
            place(name, next_row[0])

    rows = next_row[0] + 1
    columns = max(col.values()) + 1
    occupied = {(col[name], row[name]) for name in by_name}

    def is_free(r: int, from_col: int, to_col: int) -> bool:
        return all((c, r) not in occupied for c in range(from_col, to_col + 1))

    # Numbers of the circles: in the order of the flow
    order = sorted(by_name, key=lambda name: (col[name], row[name]))
    number = {name: i + 1 for i, name in enumerate(order)}

    layout = Layout(columns=columns, rows=rows)
    layout.nodes = [{**by_name[name], 'col': col[name], 'row': row[name], 'number': number[name]} for name in order]

    finished = {name for name, stage in by_name.items() if stage.get('status') == 'finished'}
    predecessors = {name: [p for p in by_name if name in forward[p]] for name in by_name}

    r = CIRCLE / 2
    lanes_used = 0
    targets_drawn = set()

    for source in order:
        for target in next_of[source]:

            a, b = (col[source], row[source]), (col[target], row[target])
            start_point = (center_x(a[0]) + r, center_y(a[1]))
            x_in = gap_after(b[0] - 1)
            end_y = center_y(b[1])

            if (source, target) in back:
                # Below all stages, in a row of its own
                lane = rows + lanes_used
                lanes_used += 1
                x_out = gap_after(a[0])
                points = [start_point, (x_out, start_point[1]), (x_out, center_y(lane)), (x_in, center_y(lane)), (x_in, end_y)]
            elif a[1] == b[1] and is_free(a[1], a[0] + 1, b[0] - 1):
                points = [start_point, (x_in, end_y)]
            elif is_free(b[1], a[0] + 1, b[0] - 1):
                x_out = gap_after(a[0])
                points = [start_point, (x_out, start_point[1]), (x_out, end_y), (x_in, end_y)]
            elif is_free(a[1], a[0] + 1, b[0] - 1):
                points = [start_point, (x_in, start_point[1]), (x_in, end_y)]
            else:
                # A row which is free between the two columns, below the others if there is none
                lane = next((r_ for r_ in range(rows) if is_free(r_, a[0] + 1, b[0] - 1)), None)
                if lane is None:
                    lane = rows + lanes_used
                    lanes_used += 1
                x_out = gap_after(a[0])
                points = [start_point, (x_out, start_point[1]), (x_out, center_y(lane)), (x_in, center_y(lane)), (x_in, end_y)]

            layout.connections.append({'d': path(points), 'kind': 'out', 'done': source in finished,
                                       'back': (source, target) in back, 'source': source, 'target': target})

            # The last piece into a stage: one for all connections into it. Done when all stages before it are finished.
            if target not in targets_drawn:
                targets_drawn.add(target)
                done = all(p in finished for p in predecessors[target]) if predecessors[target] else source in finished
                layout.connections.append({'d': path([(x_in, end_y), (center_x(b[0]) - r, end_y)]), 'kind': 'in', 'done': done,
                                           'back': False, 'source': None, 'target': target})

    layout.rows = rows + lanes_used

    return layout
