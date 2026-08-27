import os
import shutil
from datetime import datetime, date

import pandas as pd


DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]


def parse_date(value):
    """Parse a date from a string, Excel/pandas value, or date/datetime object."""
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, pd.Timestamp):
        return value.date()
    value = str(value).strip()
    if not value or value.lower() == "nan":
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def allowed_file(filename, allowed_extensions):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


IMPORT_COLUMN_MAP = {
    "vehicle number": "vehicle_number",
    "chassis number": "chassis_number",
    "owner name": "owner_name",
    "phone": "mobile_number",
    "mobile number": "mobile_number",
    "puc": "puc_expiry",
    "fitness": "fitness_expiry",
    "permit": "permit_expiry",
    "tax": "tax_expiry",
    "insurance": "insurance_expiry",
}


def normalize_import_dataframe(df):
    """Rename columns from the Excel import template to internal field names."""
    rename = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in IMPORT_COLUMN_MAP:
            rename[col] = IMPORT_COLUMN_MAP[key]
    return df.rename(columns=rename)


def create_backup(db_path, backup_folder):
    os.makedirs(backup_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    backup_name = f"backup_{timestamp}.db"
    backup_path = os.path.join(backup_folder, backup_name)
    shutil.copy2(db_path, backup_path)
    return backup_name, backup_path


def list_backups(backup_folder):
    if not os.path.isdir(backup_folder):
        return []
    files = [f for f in os.listdir(backup_folder) if f.endswith(".db")]
    files.sort(reverse=True)
    return files


def whatsapp_message(vehicle, document_label, expiry_date):
    lines = [
        f"Vehicle Compliance Details",
        f"{'=' * 30}",
        f"",
        f"Vehicle No: {vehicle.vehicle_number}",
        f"Chassis No: {vehicle.chassis_number}",
        f"Engine No: {vehicle.engine_number or 'N/A'}",
        f"Owner: {vehicle.owner_name}",
        f"Mobile: {vehicle.mobile_number}",
        f"Type: {vehicle.vehicle_type or 'N/A'}",
        f"District: {vehicle.district or 'N/A'}",
        f"Registration: {vehicle.registration_date.strftime('%d-%m-%Y') if vehicle.registration_date else 'N/A'}",
        f"",
        f"--- Document Status ---",
        f"PUC Expiry: {vehicle.puc_expiry.strftime('%d-%m-%Y') if vehicle.puc_expiry else 'Not Set'}",
        f"Fitness Expiry: {vehicle.fitness_expiry.strftime('%d-%m-%Y') if vehicle.fitness_expiry else 'Not Set'}",
        f"Permit Expiry: {vehicle.permit_expiry.strftime('%d-%m-%Y') if vehicle.permit_expiry else 'Not Set'}",
        f"Tax Expiry: {vehicle.tax_expiry.strftime('%d-%m-%Y') if vehicle.tax_expiry else 'Not Set'}",
        f"Tax Mode: {vehicle.tax_mode or 'N/A'}",
        f"Tax Amount: {vehicle.tax_amount or 'N/A'}",
        f"Insurance Expiry: {vehicle.insurance_expiry.strftime('%d-%m-%Y') if vehicle.insurance_expiry else 'Not Set'}",
        f"National Permit: {vehicle.national_permit_expiry.strftime('%d-%m-%Y') if vehicle.national_permit_expiry else 'Not Set'}",
        f"State Permit: {vehicle.state_permit_expiry.strftime('%d-%m-%Y') if vehicle.state_permit_expiry else 'Not Set'}",
        f"",
        f"Insurance Co: {vehicle.insurance_company or 'N/A'}",
        f"Policy No: {vehicle.policy_number or 'N/A'}",
        f"Pollution Cert: {vehicle.pollution_certificate_number or 'N/A'}",
        f"",
    ]
    if document_label and expiry_date:
        lines.append(f"*** {document_label} expires on {expiry_date.strftime('%d %B %Y')} - Please renew! ***")
    if vehicle.remarks:
        lines.append(f"Remarks: {vehicle.remarks}")
    return "\n".join(lines)


def whatsapp_expired_reminder(vehicle):
    """Generate a WhatsApp message with only expired/expiring document details."""
    from datetime import date
    today = date.today()
    statuses = vehicle.document_statuses()

    expired_docs = []
    for label, info in statuses.items():
        expiry = info["expiry"]
        if expiry is None:
            continue
        days_left = (expiry - today).days
        if days_left <= 30:
            expired_docs.append((label, expiry, days_left))

    if not expired_docs:
        return None

    lines = [
        f"VEHICLE EXPIRY ALERT",
        f"{'=' * 30}",
        f"",
        f"Vehicle No : {vehicle.vehicle_number}",
        f"Chassis No : {vehicle.chassis_number}",
        f"Owner      : {vehicle.owner_name}",
        f"Mobile     : {vehicle.mobile_number}",
        f"Type       : {vehicle.vehicle_type or 'N/A'}",
        f"District   : {vehicle.district or 'N/A'}",
        f"",
        f"--- Expired / Expiring Documents ---",
        f"",
    ]

    for label, expiry, days_left in expired_docs:
        date_str = expiry.strftime('%d-%m-%Y')
        if days_left < 0:
            lines.append(f"{label} : Expired on {date_str} ({abs(days_left)} days ago)")
        elif days_left == 0:
            lines.append(f"{label} : Expires today ({date_str})")
        else:
            lines.append(f"{label} : Expires on {date_str} ({days_left} days left)")

    lines.append(f"")
    lines.append(f"Please renew immediately to avoid penalties.")

    return "\n".join(lines)


def generate_vehicle_qr(vehicle):
    """Generate a QR code image with structured offline vehicle data."""
    import qrcode
    from io import BytesIO

    def fmt_date(d):
        return d.strftime("%d-%m-%Y") if d else "Not Set"

    report_id = f"VC-{vehicle.created_at.strftime('%Y%m%d')}-{vehicle.id:04d}" if vehicle.created_at else f"VC-{vehicle.id:04d}"

    qr_text = (
        f"VCMS - VEHICLE COMPLIANCE\n"
        f"{'=' * 32}\n"
        f"\n"
        f"Vehicle No  : {vehicle.vehicle_number}\n"
        f"Vehicle ID  : {vehicle.id}\n"
        f"Report ID   : {report_id}\n"
        f"\n"
        f"Owner       : {vehicle.owner_name}\n"
        f"Mobile      : {vehicle.mobile_number or 'N/A'}\n"
        f"\n"
        f"Type        : {vehicle.vehicle_type or 'N/A'}\n"
        f"District    : {vehicle.district or 'N/A'}\n"
        f"Registration: {fmt_date(vehicle.registration_date)}\n"
        f"\n"
        f"Chassis     : {vehicle.chassis_number}\n"
        f"Engine      : {vehicle.engine_number or 'N/A'}\n"
        f"\n"
        f"{'-' * 32}\n"
        f"DOCUMENT STATUS\n"
        f"{'-' * 32}\n"
        f"\n"
        f"PUC         : {fmt_date(vehicle.puc_expiry)}\n"
        f"Fitness     : {fmt_date(vehicle.fitness_expiry)}\n"
        f"Permit      : {fmt_date(vehicle.permit_expiry)}\n"
        f"Tax         : {fmt_date(vehicle.tax_expiry)}\n"
        f"Tax Mode    : {vehicle.tax_mode or 'N/A'}\n"
        f"Tax Amount  : {'₹%.2f' % vehicle.tax_amount if vehicle.tax_amount else 'N/A'}\n"
        f"Insurance   : {fmt_date(vehicle.insurance_expiry)}\n"
        f"Nat Permit  : {fmt_date(vehicle.national_permit_expiry)}\n"
        f"State Permit: {fmt_date(vehicle.state_permit_expiry)}\n"
        f"\n"
        f"Insurance Co: {vehicle.insurance_company or 'N/A'}\n"
        f"Policy No   : {vehicle.policy_number or 'N/A'}\n"
        f"Pollution   : {vehicle.pollution_certificate_number or 'N/A'}\n"
        f"\n"
    )
    if vehicle.remarks:
        qr_text += f"Remarks     : {vehicle.remarks}\n"
        qr_text += f"\n"
    qr_text += f"Generated by VCMS\n"

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(qr_text)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
