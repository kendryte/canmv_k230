# mcbytepp/lap.py - linear assignment + IoU costs.
#
# ByteTrack calls scipy/lap's lapjv.  Neither exists on the K230, so this is a
# self-contained Jonker-Volgenant shortest-augmenting-path solver over plain
# Python lists.  Track counts here are small (tens), where the O(n^3) cost is
# a few milliseconds at most.

BIG = 1e5


def linear_assignment(cost, thresh, n_rows, n_cols):
    """Solve the assignment problem, rejecting pairs costing more than thresh.

    cost is a list of rows (rows = tracks, cols = detections).  The shape is
    passed explicitly because a matrix with no rows still has columns, and the
    caller needs those back as unmatched -- that is how new tracks get born.
    Returns (matches, unmatched_rows, unmatched_cols).
    """
    n = n_rows
    m = n_cols
    if n == 0 or m == 0:
        return [], list(range(n)), list(range(m))

    # Pairs above the threshold must never be chosen in preference to leaving
    # a row unmatched, so price them out of the solver; they are filtered again
    # afterwards using the original costs.
    gated = [[(c if c <= thresh else BIG) for c in row] for row in cost]

    assignment = _jv(gated, n, m)

    matches = []
    matched_rows = set()
    matched_cols = set()
    for r, c in assignment:
        if cost[r][c] <= thresh:
            matches.append((r, c))
            matched_rows.add(r)
            matched_cols.add(c)
    u_rows = [i for i in range(n) if i not in matched_rows]
    u_cols = [j for j in range(m) if j not in matched_cols]
    return matches, u_rows, u_cols


def _jv(a, n, m):
    """Jonker-Volgenant on a rectangular matrix; returns [(row, col), ...]."""
    # The solver needs at least as many columns as rows.
    transposed = False
    if n > m:
        flipped = [[a[i][j] for i in range(n)] for j in range(m)]
        a = flipped
        n, m = m, n
        transposed = True

    INF = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)          # p[j] = row assigned to column j (1-based)
    way = [0] * (m + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = a[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1

    out = []
    for j in range(1, m + 1):
        if p[j]:
            r, c = p[j] - 1, j - 1
            out.append((c, r) if transposed else (r, c))
    return out


def iou(a, b):
    """IoU of two boxes in [x1, y1, x2, y2] form."""
    ix1 = a[0] if a[0] > b[0] else b[0]
    iy1 = a[1] if a[1] > b[1] else b[1]
    ix2 = a[2] if a[2] < b[2] else b[2]
    iy2 = a[3] if a[3] < b[3] else b[3]
    iw = ix2 - ix1
    ih = iy2 - iy1
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def iou_distance(tracks, boxes):
    """Cost matrix of 1 - IoU between track predictions and detections."""
    cost = []
    for t in tracks:
        tb = t.tlbr
        cost.append([1.0 - iou(tb, b) for b in boxes])
    return cost
