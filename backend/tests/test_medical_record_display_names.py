"""Open item 11: medical records carry the author's display name, so neither the
staff view nor the patient view has to show a raw internal staff id."""

from tests.phase1_world import World


def test_records_and_revisions_carry_author_and_editor_names_for_staff_and_patient(world: World):
    doctor, nurse, patient = world.a.doctor, world.a.nurse, world.a.patients["a1"]
    doctor_name = doctor.load_identity()["full_name"]
    nurse_name = nurse.load_identity()["full_name"]
    record_id = patient.res["record"]

    for actor in (doctor, patient):
        listing = actor.get(f"/api/v1/patients/{patient.patient_id}/medical-records")
        assert listing.status_code == 200, listing.text
        seeded = next(item for item in listing.json() if item["id"] == record_id)
        assert seeded["author_name"] == doctor_name
        detail = actor.get(f"/api/v1/medical-records/{record_id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["author_name"] == doctor_name

    current = doctor.get(f"/api/v1/medical-records/{record_id}").json()
    edited = nurse.patch(
        f"/api/v1/medical-records/{record_id}",
        json={"title": current["title"], "content": "Revisto pela enfermagem", "expected_version": current["version"]},
    )
    assert edited.status_code == 200, edited.text
    # The record keeps its original author; the revision trail names each editor.
    assert edited.json()["author_name"] == doctor_name
    revisions = patient.get(f"/api/v1/medical-records/{record_id}/revisions")
    assert revisions.status_code == 200, revisions.text
    assert revisions.json(), revisions.text
    assert {row["editor_name"] for row in revisions.json()} <= {doctor_name, nurse_name}
    assert all(row["editor_name"] for row in revisions.json())
