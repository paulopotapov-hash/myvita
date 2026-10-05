"""
Phase 6 — N+1 guard. The number of SQL statements behind a list endpoint must not
grow with the number of rows it returns.
"""

from __future__ import annotations

from sqlalchemy import event

from app.core.rate_limit import limiter
from tests.phase1_world import Actor, World


class _Counter:
    def __init__(self, engine):
        self.engine = engine
        self.count = 0

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute", self._on_execute)

    def _on_execute(self, *args):
        self.count += 1


def _count(world: World, actor: Actor, path: str) -> tuple[int, int]:
    engine = world.session_factory.kw["bind"]
    limiter.reset()
    with _Counter(engine) as counter:
        response = actor.get(path)
    assert response.status_code == 200, response.text
    body = response.json()
    rows = len(body["items"]) if isinstance(body, dict) and "items" in body else len(body)
    return counter.count, rows


def test_list_endpoints_do_not_issue_one_query_per_row(world: World):
    doctor = world.a.doctor
    patient = world.a.patients["a1"]
    pid = patient.patient_id
    paths = [
        (doctor, "/api/v1/appointments?page_size=100"),
        (doctor, "/api/v1/patients?page_size=100"),
        (doctor, f"/api/v1/patients/{pid}/medical-records"),
        (doctor, f"/api/v1/patients/{pid}/medications"),
        (patient, "/api/v1/appointments"),
        (patient, "/api/v1/notifications"),
    ]
    before = {path: _count(world, actor, path) for actor, path in paths}

    for index in range(12):
        limiter.reset()
        assert (
            doctor.post(
                "/api/v1/appointments",
                json={
                    "patient_id": pid,
                    "staff_id": doctor.staff_id,
                    "scheduled_at": f"2032-05-{index + 1:02d}T10:00:00+00:00",
                    "duration_minutes": 30,
                },
            ).status_code
            == 201
        )
        assert doctor.post(f"/api/v1/patients/{pid}/medical-records", json={"title": f"n+1 {index}", "content": "x"}).status_code == 201
        assert (
            doctor.post(
                f"/api/v1/patients/{pid}/medications", json={"name": f"Med{index}", "dosage": "1 mg", "start_date": "2032-01-01"}
            ).status_code
            == 201
        )

    for actor, path in paths:
        queries_before, rows_before = before[path]
        queries_after, rows_after = _count(world, actor, path)
        assert rows_after >= rows_before, path
        assert queries_after <= queries_before + 1, f"{path}: {queries_before} queries for {rows_before} rows -> {queries_after} for {rows_after}"
