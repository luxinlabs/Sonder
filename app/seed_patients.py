"""Seed a handful of demo patients, including your own test number, so calls resolve to a known profile."""

import os

from dotenv import load_dotenv

from app.memory_store import init_db, upsert_patient

load_dotenv()


def main():
    init_db()

    test_number = os.environ.get("TEST_CALL_TO_NUMBER")
    if test_number:
        upsert_patient(
            phone=test_number,
            name="Maria Chen",
            dob="1989-04-12",
            last_visit_reason="knee pain, follow-up recommended in 4-6 weeks",
            medications="ibuprofen 400mg as needed",
            notes="Prefers afternoon appointments.",
        )
        print(f"Seeded returning patient Maria Chen at {test_number}")

    upsert_patient(
        phone="+14155550101",
        name="James Okafor",
        dob="1975-11-02",
        last_visit_reason="annual physical",
        medications="lisinopril 10mg daily",
        notes="",
    )
    upsert_patient(
        phone="+14155550102",
        name="Priya Sharma",
        dob="1996-02-20",
        last_visit_reason="new patient, no prior visits",
        medications="none",
        notes="",
    )
    print("Seed complete.")


if __name__ == "__main__":
    main()
