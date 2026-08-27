"""Populate the database with sample vehicles for demo/testing purposes.

Usage:
    python seed_data.py
"""
from datetime import date, timedelta
import random

from app import create_app, resequence_sr_nos
from models import db, Vehicle

app = create_app()

SAMPLE = [
    ("MP20AB1234", "MA3EYD30S00123456", "F8D4123456", "Ramesh Transport Co.", "9876543210", "Truck", "Indore"),
    ("MP09CD5678", "MA1TA2S1S00654321", "K10B7654321", "Sharma Logistics", "9823456712", "Bus", "Bhopal"),
    ("MH12EF4321", "MBJA3CG1S00998877", "D13A1122334", "Patil Fleet Services", "9765432190", "Car", "Pune"),
    ("GJ01GH9988", "MA1UR2S1S00554433", "H1N556677", "Desai Carriers", "9988776655", "Trailer", "Ahmedabad"),
    ("RJ14IJ1122", "MA3ETY1S00223344", "F10D998877", "Singh Roadways", "9911223344", "Tanker", "Jaipur"),
]

VEHICLE_TYPES_EXTRA_DAYS = [-5, 3, 20, 45, 200]


def run():
    with app.app_context():
        if Vehicle.query.count() > 0:
            print("Database already has vehicles. Skipping seed.")
            return

        today = date.today()
        for i, (vnum, chassis, engine, owner, mobile, vtype, district) in enumerate(SAMPLE):
            offset = VEHICLE_TYPES_EXTRA_DAYS[i % len(VEHICLE_TYPES_EXTRA_DAYS)]
            vehicle = Vehicle(
                vehicle_number=vnum,
                chassis_number=chassis,
                engine_number=engine,
                owner_name=owner,
                mobile_number=mobile,
                vehicle_type=vtype,
                district=district,
                registration_date=today - timedelta(days=800),
                puc_expiry=today + timedelta(days=offset),
                fitness_expiry=today + timedelta(days=offset + 10),
                permit_expiry=today + timedelta(days=offset + 60),
                tax_from=today - timedelta(days=90),
                tax_expiry=today + timedelta(days=offset + 90),
                tax_mode="Quarterly (Q)",
                tax_amount=5000 + i * 500,
                insurance_expiry=today + timedelta(days=offset + 30),
                national_permit_expiry=today + timedelta(days=offset + 120),
                state_permit_expiry=today + timedelta(days=offset + 45),
                insurance_company="National General Insurance",
                policy_number=f"POL{1000 + i}",
                pollution_certificate_number=f"PUC{2000 + i}",
                remarks="Sample seeded record.",
            )
            db.session.add(vehicle)

        db.session.commit()
        resequence_sr_nos()
        print(f"Seeded {len(SAMPLE)} sample vehicles.")


if __name__ == "__main__":
    run()
