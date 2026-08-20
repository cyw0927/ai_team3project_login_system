"""Automatic team-assignment algorithms."""

import math
import random


DEFAULT_POT_CUTOFFS = (20, 50, 80)


def normalize_pot_cutoffs(pot_cutoffs=None):
    """Return validated cumulative A/B/C cutoffs.

    Cutoffs are cumulative percentages: A=0~A, B=A~B, C=B~C, D=C~100.
    """
    cutoffs = pot_cutoffs or DEFAULT_POT_CUTOFFS
    try:
        a_cutoff, b_cutoff, c_cutoff = (int(value) for value in cutoffs)
    except (TypeError, ValueError):
        raise ValueError("포트 구간은 숫자로 입력해야 합니다.")
    if not (1 <= a_cutoff < b_cutoff < c_cutoff < 100):
        raise ValueError("포트 구간은 0 < A < B < C < 100 순서여야 합니다.")
    return a_cutoff, b_cutoff, c_cutoff


def pot_count_preview(total, pot_cutoffs=None):
    """Return the exact A/B/C/D head counts produced by the rank cutoffs."""
    a_pct, b_pct, c_pct = normalize_pot_cutoffs(pot_cutoffs)
    a_cut = math.ceil(total * a_pct / 100) if total else 0
    b_cut = math.ceil(total * b_pct / 100) if total else 0
    c_cut = math.ceil(total * c_pct / 100) if total else 0
    return {
        "A": a_cut,
        "B": max(b_cut - a_cut, 0),
        "C": max(c_cut - b_cut, 0),
        "D": max(total - c_cut, 0),
    }


def snake_seed_assignment(students, team_count, seed_scores):
    ordered = sorted(
        students,
        key=lambda student: (float(seed_scores.get(student.id, 0)), -student.id),
        reverse=True,
    )
    buckets = [[] for _ in range(team_count)]
    for index, student in enumerate(ordered):
        row = index // team_count
        position = index % team_count
        team_index = position if row % 2 == 0 else team_count - 1 - position
        buckets[team_index].append(student)
    return buckets


def pot_seed_assignment(
    students,
    team_count,
    seed_scores,
    previous_team_map=None,
    pot_cutoffs=None,
):
    previous_team_map = previous_team_map or {}
    a_pct, b_pct, c_pct = normalize_pot_cutoffs(pot_cutoffs)
    seeded = [student for student in students if student.id in seed_scores]
    unseeded = [student for student in students if student.id not in seed_scores]
    ordered = sorted(
        seeded,
        key=lambda student: (float(seed_scores.get(student.id, 0)), -student.id),
        reverse=True,
    )
    total = len(ordered)

    grade_map = {student.id: "U" for student in unseeded}
    pots = {"A": [], "B": [], "C": [], "D": []}
    a_cut = math.ceil(total * a_pct / 100) if total else 0
    b_cut = math.ceil(total * b_pct / 100) if total else 0
    c_cut = math.ceil(total * c_pct / 100) if total else 0

    for rank, student in enumerate(ordered, start=1):
        if rank <= a_cut:
            grade = "A"
        elif rank <= b_cut:
            grade = "B"
        elif rank <= c_cut:
            grade = "C"
        else:
            grade = "D"
        grade_map[student.id] = grade
        pots[grade].append(student)

    for grade in pots:
        random.shuffle(pots[grade])
    random.shuffle(unseeded)

    total_students = len(students)
    base_size = total_students // team_count
    extra = total_students % team_count
    capacities = [base_size + (1 if idx < extra else 0) for idx in range(team_count)]
    buckets = [[] for _ in range(team_count)]
    bucket_grade_counts = [{grade: 0 for grade in ("A", "B", "C", "D", "U")} for _ in range(team_count)]
    bucket_previous_teams = [set() for _ in range(team_count)]

    def place(student, grade):
        prev_team = previous_team_map.get(student.id)
        candidates = [idx for idx in range(team_count) if len(buckets[idx]) < capacities[idx]]
        if not candidates:
            candidates = list(range(team_count))
        candidates.sort(
            key=lambda idx: (
                bucket_grade_counts[idx][grade],
                1 if prev_team and prev_team in bucket_previous_teams[idx] else 0,
                len(buckets[idx]),
                random.random(),
            )
        )
        chosen = candidates[0]
        buckets[chosen].append(student)
        bucket_grade_counts[chosen][grade] += 1
        if prev_team:
            bucket_previous_teams[chosen].add(prev_team)

    for grade in ("A", "B", "C", "D"):
        for student in pots[grade]:
            place(student, grade)
    for student in unseeded:
        place(student, "U")

    return buckets, grade_map, {
        "A": len(pots["A"]),
        "B": len(pots["B"]),
        "C": len(pots["C"]),
        "D": len(pots["D"]),
        "U": len(unseeded),
    }


def balanced_random_assignment(students, team_count, previous_team_map=None):
    previous_team_map = previous_team_map or {}
    students = list(students)
    random.shuffle(students)
    buckets = [[] for _ in range(team_count)]
    previous_sets = [set() for _ in range(team_count)]
    for student in students:
        candidate_order = sorted(range(team_count), key=lambda i: (len(buckets[i]), random.random()))
        chosen = None
        prev_team = previous_team_map.get(student.id)
        for idx in candidate_order:
            if prev_team and prev_team in previous_sets[idx]:
                continue
            chosen = idx
            break
        if chosen is None:
            chosen = candidate_order[0]
        buckets[chosen].append(student)
        if prev_team:
            previous_sets[chosen].add(prev_team)
    return buckets
