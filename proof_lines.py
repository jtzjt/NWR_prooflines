"""
File: proof_lines.py
Author: Junting Zhong
Date: 2026-03-11

Requirements: Python 3.8+ (standard library only)

Summary:
- Implements graph-orientation search based on the paper's algorithms.
- Computes number of proof-lines and can emit detailed proof lines.

Key Features:
- Validates adjacency matrices and enumerates Lemma 1 cycles.
- Applies forced-orientation rules and optional Theorem 5 pivot constraints.
- Branches on edge orientations to count proof lines or output proof lines.

Usage Examples:
- python3 proof_lines.py --txt graph.txt --algorithm 2 --progress
- python3 proof_lines.py --zip graphs.zip --algorithm 3 --theorem5 source --pivot auto-max-degree
"""

import argparse
import time
import zipfile
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional, Set, Callable, Sequence


def read_adjacency_matrix(text: str) -> List[List[int]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Empty adjacency matrix")
    n = len(lines)
    matrix = []
    for line in lines:
        if any(ch not in "01" for ch in line):
            raise ValueError("Adjacency matrix contains non-binary characters")
        if len(line) != n:
            raise ValueError("Adjacency matrix is not square")
        matrix.append([int(ch) for ch in line])
    for i in range(n):
        if matrix[i][i] != 0:
            raise ValueError("Adjacency matrix diagonal must be 0")
        for j in range(n):
            if matrix[i][j] != matrix[j][i]:
                raise ValueError("Adjacency matrix must be symmetric (undirected graph)")
    return matrix


def build_adj_list(matrix: List[List[int]]) -> List[List[int]]:
    n = len(matrix)
    adj = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if matrix[i][j] == 1:
                adj[i].append(j)
                adj[j].append(i)
    for i in range(n):
        adj[i].sort()
    return adj


def enumerate_cycles(
    adj: List[List[int]],
    matrix: List[List[int]],
    progress: bool = False,
) -> List[bytes]:
    n = len(adj)
    cycles: List[bytes] = []
    start_time = time.time()
    last_print_time = start_time
    dfs_calls = 0

    def dfs(start: int, current: int, path: List[int], visited: Set[int]):
        nonlocal dfs_calls, last_print_time
        dfs_calls += 1
        if progress:
            now = time.time()
            if now - last_print_time >= 2.0:
                elapsed = now - start_time
                print(
                    f"[progress] cycle-enum dfs={dfs_calls}, cycles={len(cycles)}, elapsed={elapsed:.1f}s",
                    flush=True,
                )
                last_print_time = now
        for neighbor in adj[current]:
            if neighbor == start and len(path) >= 4:
                # Lemma 1 cycle definition: m >= 4 and non-clique.
                # Each cycle appears twice (clockwise/counter-clockwise) in this DFS.
                # Keep only one orientation to avoid canonicalization and set overhead.
                if path[1] > path[-1]:
                    continue
                if is_clique(path, matrix):
                    continue
                cycles.append(bytes(path))
            elif neighbor > start and neighbor not in visited:
                visited.add(neighbor)
                dfs(start, neighbor, path + [neighbor], visited)
                visited.remove(neighbor)

    for start in range(n):
        for neighbor in adj[start]:
            if neighbor > start:
                dfs(start, neighbor, [start, neighbor], {start, neighbor})
    return cycles


def is_clique(vertices: Sequence[int], matrix: List[List[int]]) -> bool:
    for i in range(len(vertices)):
        for j in range(i + 1, len(vertices)):
            if matrix[vertices[i]][vertices[j]] == 0:
                return False
    return True


def edges_in_cycle(cycle: Sequence[int]) -> List[Tuple[int, int]]:
    m = len(cycle)
    edges = []
    for i in range(m):
        u = cycle[i]
        v = cycle[(i + 1) % m]
        if u < v:
            edges.append((u, v))
        else:
            edges.append((v, u))
    return edges


@dataclass
class GraphState:
    matrix: List[List[int]]
    adj: List[List[int]]
    orient: List[List[int]]

    @classmethod
    def create(cls, matrix: List[List[int]]):
        n = len(matrix)
        orient = [[0] * n for _ in range(n)]
        return cls(matrix=matrix, adj=build_adj_list(matrix), orient=orient)

    def clone(self) -> "GraphState":
        n = len(self.matrix)
        new_orient = [row[:] for row in self.orient]
        return GraphState(matrix=self.matrix, adj=self.adj, orient=new_orient)

    def is_oriented(self, u: int, v: int) -> bool:
        return self.orient[u][v] != 0

    def set_orient(self, u: int, v: int, direction: int):
        if u == v:
            raise ValueError("Cannot orient self-loop")
        if direction == 0:
            raise ValueError("Direction must be +1 or -1")
        if self.orient[u][v] != 0 and self.orient[u][v] != direction:
            raise ValueError("Conflicting orientation")
        self.orient[u][v] = direction
        self.orient[v][u] = -direction

    def oriented_edges(self) -> List[Tuple[int, int]]:
        n = len(self.matrix)
        edges = []
        for u in range(n):
            for v in range(n):
                if self.orient[u][v] == 1:
                    edges.append((u, v))
        return edges

    def directed_neighbors(self, u: int) -> List[int]:
        return [v for v in self.adj[u] if self.orient[u][v] == 1]


@dataclass
class AlgorithmContext:
    cycles: List[bytes]
    edge_cycle_count: Dict[Tuple[int, int], int]
    edge_list: List[Tuple[int, int]]


def compute_edge_cycle_counts(cycles: List[bytes]) -> Dict[Tuple[int, int], int]:
    counts: Dict[Tuple[int, int], int] = {}
    for cycle in cycles:
        for e in edges_in_cycle(cycle):
            counts[e] = counts.get(e, 0) + 1
    return counts


def build_edge_list(matrix: List[List[int]]) -> List[Tuple[int, int]]:
    n = len(matrix)
    edges = []
    for u in range(n):
        for v in range(u + 1, n):
            if matrix[u][v] == 1:
                edges.append((u, v))
    return edges


def state_key(state: GraphState, edge_list: List[Tuple[int, int]]) -> Tuple[int, ...]:
    key = []
    for u, v in edge_list:
        key.append(state.orient[u][v])
    return tuple(key)


def find_directed_cycle(state: GraphState) -> Optional[List[int]]:
    n = len(state.matrix)
    color = [0] * n  # 0 unvisited, 1 visiting, 2 done
    parent = [-1] * n

    def dfs(u: int) -> Optional[List[int]]:
        color[u] = 1
        for v in state.directed_neighbors(u):
            if color[v] == 1:
                cycle = [v, u]
                cur = u
                while parent[cur] != -1 and parent[cur] != v:
                    cur = parent[cur]
                    cycle.append(cur)
                cycle.reverse()
                return cycle
            if color[v] == 0:
                parent[v] = u
                found = dfs(v)
                if found is not None:
                    return found
        color[u] = 2
        return None

    for i in range(n):
        if color[i] == 0:
            found = dfs(i)
            if found is not None:
                return found
    return None


def find_shortcut(state: GraphState) -> Optional[List[int]]:
    n = len(state.matrix)

    def dfs_path(start: int, current: int, target: int, path: List[int], visited: Set[int]) -> Optional[List[int]]:
        for nxt in state.directed_neighbors(current):
            if nxt == target and len(path) >= 2:
                vertices = path + [target]
                if not is_clique(vertices, state.matrix):
                    return vertices
            elif nxt not in visited:
                visited.add(nxt)
                found = dfs_path(start, nxt, target, path + [nxt], visited)
                if found is not None:
                    return found
                visited.remove(nxt)
        return None

    for u in range(n):
        for v in state.adj[u]:
            if state.orient[u][v] == 1:
                found = dfs_path(u, u, v, [u], {u})
                if found is not None:
                    return found
    return None


def apply_triangle_rule(state: GraphState) -> Optional[Tuple[int, int, int]]:
    n = len(state.matrix)
    for a in range(n):
        for b in state.directed_neighbors(a):
            for c in state.directed_neighbors(b):
                if a == c:
                    continue
                if state.matrix[a][c] == 1 and state.orient[a][c] == 0:
                    state.set_orient(a, c, 1)
                    return (a, b, c)
    return None


def apply_lemma5(
    state: GraphState,
    cycles: List[bytes],
    progress_tick: Optional[Callable[[int], None]] = None,
) -> Optional[Tuple[str, List[Tuple[int, int]], Optional[List[int]]]]:
    degrees = [len(nei) for nei in state.adj]
    # Choose candidate only by highest-degree involved vertex.
    # Tie-break deterministically by degree sum then cycle bytes.
    best_score: Optional[Tuple[int, int, bytes]] = None
    best_cycle: Optional[bytes] = None
    best_direction: Optional[int] = None
    best_missing_1: Optional[Tuple[int, int]] = None
    best_missing_2: Optional[Tuple[int, int]] = None

    scanned = 0
    for cycle in cycles:
        scanned += 1
        if progress_tick is not None and scanned % 50000 == 0:
            progress_tick(50000)
        m = len(cycle)
        forward = 0
        backward = 0
        unoriented = 0
        # At most two edges need to be materialized in Lemma 1 trigger branches.
        missing_1: Optional[Tuple[int, int]] = None
        missing_2: Optional[Tuple[int, int]] = None
        for i in range(m):
            u = cycle[i]
            v = cycle[(i + 1) % m]
            direction = state.orient[u][v]
            if direction == 1:
                forward += 1
            elif direction == -1:
                backward += 1
            else:
                unoriented += 1
                if missing_1 is None:
                    missing_1 = (u, v)
                elif missing_2 is None:
                    missing_2 = (u, v)

        if forward == m - 1 and backward == 0 and unoriented == 1:
            return ("error", [], list(cycle))  # error condition
        if backward == m - 1 and forward == 0 and unoriented == 1:
            return ("error", [], list(cycle))  # error condition

        if forward == m - 2 and backward + unoriented == 2 and unoriented > 0:
            touched_vertices = set()
            if missing_1 is not None:
                touched_vertices.add(missing_1[0])
                touched_vertices.add(missing_1[1])
            if missing_2 is not None:
                touched_vertices.add(missing_2[0])
                touched_vertices.add(missing_2[1])
            max_degree = max((degrees[v] for v in touched_vertices), default=-1)
            degree_sum = sum(degrees[v] for v in touched_vertices)
            score = (max_degree, degree_sum, cycle)
            if best_score is None or score > best_score:
                best_score = score
                best_cycle = cycle
                best_direction = -1  # orient backward
                best_missing_1 = missing_1
                best_missing_2 = missing_2
        if backward == m - 2 and forward + unoriented == 2 and unoriented > 0:
            touched_vertices = set()
            if missing_1 is not None:
                touched_vertices.add(missing_1[0])
                touched_vertices.add(missing_1[1])
            if missing_2 is not None:
                touched_vertices.add(missing_2[0])
                touched_vertices.add(missing_2[1])
            max_degree = max((degrees[v] for v in touched_vertices), default=-1)
            degree_sum = sum(degrees[v] for v in touched_vertices)
            score = (max_degree, degree_sum, cycle)
            if best_score is None or score > best_score:
                best_score = score
                best_cycle = cycle
                best_direction = 1  # orient forward
                best_missing_1 = missing_1
                best_missing_2 = missing_2

    if best_cycle is not None and best_direction is not None:
        oriented: List[Tuple[int, int]] = []
        if best_missing_1 is not None:
            u, v = best_missing_1
            state.set_orient(u, v, best_direction)
            oriented.append((u, v) if best_direction == 1 else (v, u))
        if best_missing_2 is not None:
            u, v = best_missing_2
            state.set_orient(u, v, best_direction)
            oriented.append((u, v) if best_direction == 1 else (v, u))

        otype = "OO" if len(oriented) == 2 else "O"
        return (otype, oriented, list(best_cycle))
    return None


def apply_forced_orientations(
    state: GraphState,
    cycles: List[bytes],
    progress_tick: Optional[Callable[[int], None]] = None,
    emit_instruction: Optional[Callable[[str], None]] = None,
) -> Tuple[str, Optional[str], Optional[List[int]]]:
    while True:
        dcycle = find_directed_cycle(state)
        if dcycle is not None:
            return ("contradiction", "cycle", dcycle)
        shortcut = find_shortcut(state)
        if shortcut is not None:
            return ("contradiction", "shortcut", shortcut)
        lemma = apply_lemma5(state, cycles, progress_tick)
        if lemma is not None:
            ltype, oriented, lcycle = lemma
            if ltype == "error":
                return ("contradiction", "error", lcycle)
            if emit_instruction is not None and lcycle is not None:
                cyc = "-".join(str(x + 1) for x in lcycle)
                if ltype == "OO" and len(oriented) == 2:
                    e1 = f"{oriented[0][0] + 1}->{oriented[0][1] + 1}"
                    e2 = f"{oriented[1][0] + 1}->{oriented[1][1] + 1}"
                    emit_instruction(f"OO {e1}, {e2} (C {cyc})")
                elif len(oriented) >= 1:
                    e = oriented[0]
                    emit_instruction(f"O {e[0] + 1}->{e[1] + 1} (C {cyc})")
            continue
        triangle = apply_triangle_rule(state)
        if triangle is not None:
            if emit_instruction is not None:
                a, b, c = triangle
                emit_instruction(f"O {a + 1}->{c + 1} (C {a + 1}-{b + 1}-{c + 1})")
            continue
        break
    return ("ok", None, None)


def edge_key(edge: Tuple[int, int]) -> Tuple[int, int]:
    return edge


def pick_edge_algorithm_1(state: GraphState, ctx: AlgorithmContext) -> Optional[Tuple[int, int]]:
    candidates = []
    n = len(state.matrix)
    for u in range(n):
        for v in state.adj[u]:
            if u < v and state.orient[u][v] == 0:
                count = ctx.edge_cycle_count.get((u, v), 0)
                if count > 0:
                    candidates.append((count, (u, v)))
    if not candidates:
        return None
    max_count = max(c[0] for c in candidates)
    edges = [e for c, e in candidates if c == max_count]
    edges.sort()
    return edges[0]


def cycle_non_oriented_edges(state: GraphState, cycle: Sequence[int]) -> List[Tuple[int, int]]:
    m = len(cycle)
    edges = []
    for i in range(m):
        u = cycle[i]
        v = cycle[(i + 1) % m]
        a, b = (u, v) if u < v else (v, u)
        if state.orient[a][b] == 0:
            edges.append((a, b))
    return edges


def cycle_direction_counts(state: GraphState, cycle: Sequence[int]) -> Tuple[int, int]:
    m = len(cycle)
    forward = 0
    backward = 0
    for i in range(m):
        u = cycle[i]
        v = cycle[(i + 1) % m]
        direction = state.orient[u][v]
        if direction == 1:
            forward += 1
        elif direction == -1:
            backward += 1
    return forward, backward


def pick_edge_algorithm_2(state: GraphState, ctx: AlgorithmContext) -> Optional[Tuple[int, int]]:
    best_cycles = []
    for cycle in ctx.cycles:
        edges = cycle_non_oriented_edges(state, cycle)
        if not edges:
            continue
        best_cycles.append((len(edges), cycle))
    if not best_cycles:
        return None
    min_unoriented = min(c[0] for c in best_cycles)
    cycles = [c for u, c in best_cycles if u == min_unoriented]
    cycles.sort()
    cycle = cycles[0]


    edges = cycle_non_oriented_edges(state, cycle)
    if not edges:
        return None
    edges.sort(key=lambda e: (-ctx.edge_cycle_count.get(e, 0), e))
    return edges[0]


def pick_edge_algorithm_5(state: GraphState, ctx: AlgorithmContext) -> Optional[Tuple[int, int]]:
    best_cycles = []
    for cycle in ctx.cycles:
        edges = cycle_non_oriented_edges(state, cycle)
        if not edges:
            continue
        best_cycles.append((len(edges), cycle))
    if not best_cycles:
        return None
    min_unoriented = min(c[0] for c in best_cycles)
    cycles = [c for u, c in best_cycles if u == min_unoriented]
    cycles.sort()
    cycle = cycles[0]
    edges = cycle_non_oriented_edges(state, cycle)
    if not edges:
        return None

    # Same as algorithm 2, with an extra tie-breaker:
    # if cycle count ties, choose the edge with max degree-sum.
    degrees = [len(nei) for nei in state.adj]
    edges.sort(key=lambda e: (-ctx.edge_cycle_count.get(e, 0), -(degrees[e[0]] + degrees[e[1]]), e))
    return edges[0]


def total_unoriented_cycle_edges(state: GraphState, cycles: List[bytes]) -> int:
    total = 0
    for cycle in cycles:
        total += len(cycle_non_oriented_edges(state, cycle))
    return total


def pick_edge_algorithm_6(
    state: GraphState,
    ctx: AlgorithmContext,
    progress_tick: Optional[Callable[[int], None]] = None,
) -> Optional[Tuple[int, int]]:
    best_cycles = []
    for cycle in ctx.cycles:
        edges = cycle_non_oriented_edges(state, cycle)
        if not edges:
            continue
        best_cycles.append((len(edges), cycle))
    if not best_cycles:
        return None

    min_unoriented = min(c[0] for c in best_cycles)
    cycles = [c for u, c in best_cycles if u == min_unoriented]
    candidate_set: Set[Tuple[int, int]] = set()
    for cycle in cycles:
        for edge in cycle_non_oriented_edges(state, cycle):
            candidate_set.add(edge)
    edges = sorted(candidate_set)
    if not edges:
        return None
    if len(edges) == 1:
        return edges[0]

    degrees = [len(nei) for nei in state.adj]
    scored: List[Tuple[Tuple[int, int, int, int, int, Tuple[int, int]], Tuple[int, int]]] = []

    for edge in edges:
        u, v = edge
        unresolved = 0
        worst_residual = 0
        residual_sum = 0
        for direction in [1, -1]:
            sim = state.clone()
            sim.set_orient(u, v, direction)
            status, _, _ = apply_forced_orientations(sim, ctx.cycles, progress_tick)
            if status == "contradiction":
                continue
            unresolved += 1
            residual = total_unoriented_cycle_edges(sim, ctx.cycles)
            residual_sum += residual
            worst_residual = max(worst_residual, residual)

        # Global one-step lookahead over candidate edges:
        # prefer edges that close more branches immediately, then leave less unresolved work.
        score = (
            unresolved,
            worst_residual,
            residual_sum,
            -ctx.edge_cycle_count.get(edge, 0),
            -(degrees[u] + degrees[v]),
            edge,
        )
        scored.append((score, edge))

    scored.sort(key=lambda x: x[0])
    return scored[0][1]


def pick_edge_algorithm_3(state: GraphState, ctx: AlgorithmContext) -> Optional[Tuple[int, int]]:
    candidates = []
    for cycle in ctx.cycles:
        edges = cycle_non_oriented_edges(state, cycle)
        if not edges:
            continue
        forward, backward = cycle_direction_counts(state, cycle)
        same_dir = max(forward, backward)
        candidates.append((same_dir, len(edges), cycle))
    if not candidates:
        return None
    max_same = max(c[0] for c in candidates)
    filtered = [c for c in candidates if c[0] == max_same]
    min_unoriented = min(c[1] for c in filtered)
    cycles = [c[2] for c in filtered if c[1] == min_unoriented]
    cycles.sort()
    cycle = cycles[0]


    edges = cycle_non_oriented_edges(state, cycle)
    if not edges:
        return None
    edges.sort(key=lambda e: (-ctx.edge_cycle_count.get(e, 0), e))
    return edges[0]


def longest_directed_path_length(state: GraphState) -> int:
    n = len(state.matrix)
    color = [0] * n  # 0 unvisited, 1 visiting, 2 done
    memo = [0] * n

    def dfs(u: int) -> int:
        color[u] = 1
        best = 0
        for v in state.directed_neighbors(u):
            if color[v] == 1:
                # Cycle shouldn't happen here; ignore to keep function total.
                continue
            if color[v] == 0:
                dfs(v)
            best = max(best, 1 + memo[v])
        color[u] = 2
        memo[u] = best
        return best

    for i in range(n):
        if color[i] == 0:
            dfs(i)
    return max(memo) if memo else 0


def pick_edge_algorithm_4(state: GraphState, ctx: AlgorithmContext) -> Optional[Tuple[int, int]]:
    best_cycles = []
    for cycle in ctx.cycles:
        edges = cycle_non_oriented_edges(state, cycle)
        if not edges:
            continue
        best_cycles.append((len(edges), cycle))
    if not best_cycles:
        return None
    min_unoriented = min(c[0] for c in best_cycles)
    cycles = [c for u, c in best_cycles if u == min_unoriented]
    cycles.sort()
    cycle = cycles[0]
    edges = cycle_non_oriented_edges(state, cycle)
    if not edges:
        return None
    if len(edges) == 1:
        return edges[0]

    current_len = longest_directed_path_length(state)
    edge_increase: Dict[Tuple[int, int], int] = {}
    for u, v in edges:
        max_len = current_len
        for direction in [1, -1]:
            prev_uv = state.orient[u][v]
            prev_vu = state.orient[v][u]
            state.set_orient(u, v, direction)
            max_len = max(max_len, longest_directed_path_length(state))
            state.orient[u][v] = prev_uv
            state.orient[v][u] = prev_vu
        edge_increase[(u, v)] = max_len - current_len

    max_increase = max(edge_increase.values())
    if max_increase > 0:
        edges = [e for e in edges if edge_increase[e] == max_increase]
        edges.sort(key=lambda e: (-ctx.edge_cycle_count.get(e, 0), e))
        return edges[0]

    # Fall back to algorithm 3 selection if no increase is possible.
    return pick_edge_algorithm_3(state, ctx)


def pick_branch_edge(
    state: GraphState,
    ctx: AlgorithmContext,
    algorithm: int,
    progress_tick: Optional[Callable[[int], None]] = None,
) -> Optional[Tuple[int, int]]:
    if algorithm == 1:
        return pick_edge_algorithm_1(state, ctx)
    if algorithm == 2:
        return pick_edge_algorithm_2(state, ctx)
    if algorithm == 3:
        return pick_edge_algorithm_3(state, ctx)
    if algorithm == 4:
        return pick_edge_algorithm_4(state, ctx)
    if algorithm == 5:
        return pick_edge_algorithm_5(state, ctx)
    if algorithm == 6:
        return pick_edge_algorithm_6(state, ctx, progress_tick)
    raise ValueError("Algorithm must be 1, 2, 3, 4, 5, or 6")


def decision_to_literal(u: int, v: int, direction: int) -> str:
    if direction == 1:
        a, b = u + 1, v + 1
    else:
        a, b = v + 1, u + 1
    return f"x{a}->x{b}"


def format_cycle_path(vertices: Optional[List[int]]) -> str:
    if not vertices:
        return "?"
    return "-".join(str(v + 1) for v in vertices)


def format_branch_line(line_no: int, instructions: List[str], end_tag: str) -> str:
    body = " ; ".join(instructions) if instructions else "(empty)"
    return f"L{line_no}: {body} ; {end_tag}"


def count_proof_lines(
    state: GraphState,
    ctx: AlgorithmContext,
    algorithm: int,
    is_root: bool,
    memo: Dict[Tuple[int, ...], Tuple[int, bool]],
    progress_tick: Optional[Callable[[int], None]] = None,
    use_root_symmetry: bool = True,
    use_memo: bool = True,
    instructions: Optional[List[str]] = None,
    emit_line: Optional[Callable[[List[str], str], None]] = None,
    copy_counter: Optional[List[int]] = None,
) -> Tuple[int, bool]:
    if progress_tick is not None:
        progress_tick(1)
    if instructions is None:
        instructions = []
    if copy_counter is None:
        copy_counter = [2]

    local_forced_steps: List[str] = []
    status, reason, detail = apply_forced_orientations(
        state,
        ctx.cycles,
        progress_tick,
        local_forced_steps.append,
    )
    if status == "contradiction":
        if emit_line is not None:
            end_tag = "E: " + format_cycle_path(detail)
            if reason == "shortcut":
                end_tag = "S: " + format_cycle_path(detail)
            emit_line(instructions + local_forced_steps, end_tag)
        return (1, False)

    key: Optional[Tuple[int, ...]] = None
    if use_memo and not is_root:
        key = state_key(state, ctx.edge_list)
        cached = memo.get(key)
        if cached is not None:
            return cached

    edge = pick_branch_edge(state, ctx, algorithm, progress_tick)
    if edge is None:
        result = (0, True)  # no cycles left; potential word-representability
        if key is not None:
            memo[key] = result
        return result

    u, v = edge
    if is_root and use_root_symmetry:
        next_state = state.clone()
        next_state.set_orient(u, v, 1)
        return count_proof_lines(
            next_state,
            ctx,
            algorithm,
            False,
            memo,
            progress_tick,
            use_root_symmetry,
            use_memo,
            instructions + [f"{u + 1}->{v + 1}"] + local_forced_steps,
            emit_line,
            copy_counter,
        )

    total = 0
    copy_id = copy_counter[0]
    copy_counter[0] += 1

    for direction in [1, -1]:
        next_state = state.clone()
        next_state.set_orient(u, v, direction)
        if direction == 1:
            oriented = f"{u + 1}->{v + 1}"
            branch_instr = instructions + local_forced_steps + [f"B {oriented} (Copy {copy_id})"]
        else:
            oriented = f"{v + 1}->{u + 1}"
            branch_instr = instructions + local_forced_steps + [f"MC {copy_id}", oriented]
        lines, success = count_proof_lines(
            next_state,
            ctx,
            algorithm,
            False,
            memo,
            progress_tick,
            use_root_symmetry,
            use_memo,
            branch_instr,
            emit_line,
            copy_counter,
        )
        if success:
            result = (0, True)
            if key is not None and use_memo:
                memo[key] = result
            return result
        total += lines
    result = (total, False)
    if key is not None and use_memo:
        memo[key] = result
    return result


def apply_theorem5_constraint(state: GraphState, pivot: int, mode: str):
    if mode not in {"source", "sink"}:
        raise ValueError("Theorem 5 mode must be 'source' or 'sink'")
    for u in state.adj[pivot]:
        if mode == "source":
            state.set_orient(pivot, u, 1)
        else:
            state.set_orient(u, pivot, 1)


def process_graph(
    matrix: List[List[int]],
    algorithm: int,
    progress: bool = False,
    theorem5: str = "off",
    pivot: Optional[int] = None,
    emit_proof_lines: bool = False,
) -> Tuple[int, bool]:
    state = GraphState.create(matrix)
    n = len(matrix)
    if theorem5 != "off":
        if pivot is None:
            raise ValueError("--pivot is required when --theorem5 is not off")
        if pivot < 0 or pivot >= n:
            raise ValueError(f"--pivot {pivot} out of range for n={n}")
    elif pivot is not None:
        raise ValueError("--pivot can only be used with --theorem5 source/sink/both")

    if progress:
        print("Building cycle list for n={n} (Lemma 1 definition)...".format(n=n), flush=True)
    cycles = enumerate_cycles(
        state.adj,
        matrix,
        progress=progress,
    )
    if progress:
        print(f"Cycle list built: {len(cycles)} cycles", flush=True)
    edge_cycle_count = compute_edge_cycle_counts(cycles)
    edge_list = build_edge_list(matrix)
    ctx = AlgorithmContext(cycles=cycles, edge_cycle_count=edge_cycle_count, edge_list=edge_list)
    memo: Dict[Tuple[int, ...], Tuple[int, bool]] = {}

    if progress:
        print(f"Graph stats: n={len(matrix)}, edges={len(edge_list)}, cycles={len(cycles)}", flush=True)

    def solve_with_optional_constraint(mode: Optional[str]) -> Tuple[int, bool]:
        local_state = state.clone()
        base_instructions: List[str] = []
        if mode in {"source", "sink"}:
            p = pivot  # type: ignore[assignment]
            base_instructions.append(f"INIT theorem5 {mode}({p + 1})")
            for u in local_state.adj[p]:
                if mode == "source":
                    local_state.set_orient(p, u, 1)
                else:
                    local_state.set_orient(u, p, 1)
        local_memo: Dict[Tuple[int, ...], Tuple[int, bool]] = {}
        start_time = time.time()
        last_print_time = start_time
        calls = 0
        line_counter = 0
        last_emitted_full_inst: Optional[List[str]] = None

        progress_tick: Optional[Callable[[int], None]] = None
        emit_line: Optional[Callable[[List[str], str], None]] = None
        if progress:
            if mode is not None:
                print(f"Applying Theorem 5 constraint: pivot={pivot}, mode={mode}", flush=True)
            else:
                print("Applying Theorem 5 constraint: off", flush=True)

            def tick(step: int = 1):
                nonlocal calls, last_print_time
                calls += step
                now = time.time()
                if now - last_print_time >= 2.0:
                    elapsed = now - start_time
                    print(f"[progress] work units={calls}, elapsed={elapsed:.1f}s", flush=True)
                    last_print_time = now

            progress_tick = tick

        if emit_proof_lines:
            print("Proof lines:", flush=True)

            def emit(inst: List[str], end_tag: str):
                nonlocal line_counter, last_emitted_full_inst
                display_inst = inst
                if line_counter > 0 and last_emitted_full_inst is not None:
                    prefix_len = 0
                    max_prefix = min(len(last_emitted_full_inst), len(inst))
                    while (
                        prefix_len < max_prefix
                        and last_emitted_full_inst[prefix_len] == inst[prefix_len]
                    ):
                        prefix_len += 1
                    display_inst = inst[prefix_len:]
                    if display_inst and display_inst[0].startswith("MC "):
                        pass
                    else:
                        first_mc_idx = next(
                            (i for i, token in enumerate(display_inst) if token.startswith("MC ")),
                            None,
                        )
                        if first_mc_idx is not None:
                            display_inst = display_inst[first_mc_idx:]
                        else:
                            last_mc_token = next(
                                (token for token in reversed(inst) if token.startswith("MC ")),
                                None,
                            )
                            if last_mc_token is not None:
                                if display_inst:
                                    display_inst = [last_mc_token] + display_inst
                                else:
                                    display_inst = [last_mc_token]
                if line_counter > 0 and (not display_inst or not display_inst[0].startswith("MC ")):
                    fallback_mc_token = next(
                        (token for token in reversed(inst) if token.startswith("MC ")),
                        None,
                    )
                    if fallback_mc_token is not None:
                        display_inst = [fallback_mc_token] + display_inst
                line_counter += 1
                print(format_branch_line(line_counter, display_inst, end_tag), flush=True)
                last_emitted_full_inst = inst.copy()

            emit_line = emit

        use_root_symmetry = mode is None
        use_memo = not emit_proof_lines
        return count_proof_lines(
            local_state,
            ctx,
            algorithm,
            True,
            local_memo,
            progress_tick,
            use_root_symmetry,
            use_memo,
            base_instructions,
            emit_line,
        )

    if theorem5 == "off":
        return solve_with_optional_constraint(None)
    if theorem5 == "source":
        return solve_with_optional_constraint("source")
    if theorem5 == "sink":
        return solve_with_optional_constraint("sink")
    if theorem5 == "both":
        lines_source, success_source = solve_with_optional_constraint("source")
        if success_source:
            return (0, True)
        lines_sink, success_sink = solve_with_optional_constraint("sink")
        if success_sink:
            return (0, True)
        return (lines_source + lines_sink, False)
    raise ValueError("--theorem5 must be one of: off, source, sink, both")


def decode_with_fallback(raw: bytes) -> str:
    for encoding in ["utf-8", "gbk", "latin-1"]:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    # latin-1 should always decode, this is a defensive fallback.
    return raw.decode("latin-1", errors="replace")


def resolve_pivot_for_matrix(
    matrix: List[List[int]],
    theorem5: str,
    pivot_arg: Optional[str],
) -> Optional[int]:
    if theorem5 == "off":
        if pivot_arg is not None:
            raise ValueError("--pivot can only be used with --theorem5 source/sink/both")
        return None

    if pivot_arg is None:
        raise ValueError("--pivot is required when --theorem5 is source/sink/both")

    token = pivot_arg.strip().lower()
    if token in {"auto", "auto-max-degree", "max-degree"}:
        degrees = [sum(row) for row in matrix]
        max_degree = max(degrees) if degrees else 0
        candidates = [i for i, d in enumerate(degrees) if d == max_degree]
        return candidates[0] if candidates else 0

    try:
        pivot = int(pivot_arg)
    except ValueError as e:
        raise ValueError("--pivot must be an integer vertex id or 'auto-max-degree'") from e
    return pivot


def process_zip_input(
    zip_path: str,
    algorithm: int,
    theorem5: str,
    pivot_arg: Optional[str],
    progress: bool,
) -> None:
    results = []
    skipped = []
    auto_pivot_mode = (pivot_arg or "").strip().lower() in {"auto", "auto-max-degree", "max-degree"}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in sorted(zf.namelist()):
            if name.endswith("/"):
                continue
            if "/__MACOSX/" in name or name.startswith("__MACOSX/"):
                continue
            if not name.lower().endswith(".txt"):
                continue
            if "/._" in name or name.startswith("._"):
                continue
            raw = zf.read(name)
            content = decode_with_fallback(raw)
            try:
                matrix = read_adjacency_matrix(content)
                pivot = resolve_pivot_for_matrix(matrix, theorem5, pivot_arg)
            except ValueError as e:
                skipped.append((name, str(e)))
                continue
            if progress:
                if theorem5 == "off":
                    print(f"Processing {name}...", flush=True)
                else:
                    print(f"Processing {name}... (pivot={pivot})", flush=True)
            lines, success = process_graph(
                matrix,
                algorithm,
                progress=False,
                theorem5=theorem5,
                pivot=pivot,
            )
            results.append((name, lines, success, pivot))

    if not results:
        print("No valid .txt adjacency matrices found in zip.")
        if skipped:
            print("Skipped files:")
            for name, reason in skipped:
                print(f"- {name}: {reason}")
        return

    print(f"Algorithm {algorithm}")
    print(f"Theorem5: {theorem5}" + (f", pivot={pivot_arg}" if theorem5 != "off" else ""))
    print("Cycles: lemma (fixed)")
    total_lines = 0
    for name, lines, success, used_pivot in results:
        pivot_suffix = f" (pivot={used_pivot})" if theorem5 != "off" and auto_pivot_mode else ""
        if success:
            print(f"{name}: WR (0 lines){pivot_suffix}")
        else:
            print(f"{name}: {lines}{pivot_suffix}")
        total_lines += lines
    avg = total_lines / len(results)
    print(f"Average: {avg:.3f}")
    min_lines = min(lines for _, lines, _, _ in results)
    max_lines = max(lines for _, lines, _, _ in results)
    min_graphs = [name for name, lines, _, _ in results if lines == min_lines]
    max_graphs = [name for name, lines, _, _ in results if lines == max_lines]
    print(f"Min: {min_lines} (graphs: {', '.join(min_graphs)})")
    print(f"Max: {max_lines} (graphs: {', '.join(max_graphs)})")
    if skipped:
        print(f"Skipped invalid files: {len(skipped)}")
        for name, reason in skipped:
            print(f"- {name}: {reason}")


def main():
    parser = argparse.ArgumentParser(description="Compute proof lines for graphs using algorithms from the paper.")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--zip", help="Path to .zip file containing adjacency matrices (.txt)")
    input_group.add_argument("--txt", help="Path to a single graph adjacency matrix (.txt)")
    parser.add_argument("--algorithm", type=int, choices=[1, 2, 3, 4, 5, 6], required=True, help="Algorithm number: 1, 2, 3, 4, 5, or 6")
    parser.add_argument(
        "--theorem5",
        choices=["off", "source", "sink", "both"],
        default="off",
        help="Apply Theorem 5 pivot constraint: off/source/sink/both",
    )
    parser.add_argument(
        "--pivot",
        help="Pivot vertex id for Theorem 5 constraint, or 'auto-max-degree'",
    )
    parser.add_argument("--progress", action="store_true", help="Print progress for each graph")
    args = parser.parse_args()
    if args.theorem5 != "off" and args.pivot is None:
        parser.error("--pivot is required when --theorem5 is source/sink/both")
    if args.theorem5 == "off" and args.pivot is not None:
        parser.error("--pivot can only be used with --theorem5 source/sink/both")

    if args.txt:
        if args.txt.lower().endswith(".zip"):
            if args.progress:
                print(f"Detected zip input from --txt: {args.txt}", flush=True)
            process_zip_input(
                args.txt,
                args.algorithm,
                args.theorem5,
                args.pivot,
                args.progress,
            )
            return
        if args.progress:
            print(f"Processing {args.txt}...", flush=True)
        with open(args.txt, "rb") as f:
            raw = f.read()
        content = decode_with_fallback(raw)
        matrix = read_adjacency_matrix(content)
        try:
            pivot = resolve_pivot_for_matrix(matrix, args.theorem5, args.pivot)
        except ValueError as e:
            parser.error(str(e))
        lines, success = process_graph(
            matrix,
            args.algorithm,
            progress=args.progress,
            theorem5=args.theorem5,
            pivot=pivot,
            emit_proof_lines=True,
        )
        print(f"Algorithm {args.algorithm}")
        print(f"Theorem5: {args.theorem5}" + (f", pivot={args.pivot}" if args.theorem5 != "off" else ""))
        print("Cycles: lemma (fixed)")
        if success:
            print(f"{args.txt}: WR (proof lines: 0)")
        else:
            print(f"{args.txt}: proof lines = {lines}")
        return

    process_zip_input(
        args.zip,
        args.algorithm,
        args.theorem5,
        args.pivot,
        args.progress,
    )


if __name__ == "__main__":
    main()
