import io
import json
import os
from datetime import date, timedelta, datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    session, send_file, jsonify, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd

from config import Config
from models import db, Vehicle, TaxDetail
from utils import (
    parse_date, allowed_file, normalize_import_dataframe,
    create_backup, list_backups, whatsapp_message, whatsapp_expired_reminder, generate_vehicle_qr
)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    for folder in (app.config["UPLOAD_FOLDER"], app.config["EXPORT_FOLDER"], app.config["BACKUP_FOLDER"]):
        os.makedirs(folder, exist_ok=True)

    with app.app_context():
        db.create_all()
        resequence_sr_nos()

    register_routes(app)
    return app


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if Config.LOGIN_REQUIRED and not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def resequence_sr_nos():
    vehicles = Vehicle.query.order_by(Vehicle.vehicle_number).all()
    for i, v in enumerate(vehicles, 1):
        v.sr_no = f"SN{i:03d}"
    db.session.commit()


EXPORT_COLUMNS = [
    ("vehicle_number", "Vehicle Number"),
    ("chassis_number", "Chassis Number"),
    ("engine_number", "Engine Number"),
    ("owner_name", "Owner Name"),
    ("mobile_number", "Mobile Number"),
    ("vehicle_type", "Vehicle Type"),
    ("district", "District"),
    ("registration_date", "Registration Date"),
    ("puc_expiry", "PUC Expiry"),
    ("fitness_expiry", "Fitness Expiry"),
    ("permit_expiry", "Permit Expiry"),
    ("tax_expiry", "Tax Expiry"),
    ("tax_from", "Tax From"),
    ("tax_mode", "Tax Mode"),
    ("tax_amount", "Tax Amount"),
    ("insurance_expiry", "Insurance Expiry"),
    ("national_permit_expiry", "National Permit Expiry"),
    ("state_permit_expiry", "State Permit Expiry"),
    ("insurance_company", "Insurance Company"),
    ("policy_number", "Policy Number"),
    ("pollution_certificate_number", "Pollution Cert. No."),
    ("remarks", "Remarks"),
    ("created_at", "Created At"),
    ("updated_at", "Updated At"),
]


def register_routes(app):

    # ---- Auth ------------------------------------------------------------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not Config.LOGIN_REQUIRED:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            if username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
                session["logged_in"] = True
                session["username"] = username
                flash("Welcome back!", "success")
                next_url = request.args.get("next") or url_for("dashboard")
                return redirect(next_url)
            flash("Invalid username or password.", "error")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    # ---- Dashboard ---------------------------------------------------------

    @app.route("/")
    @login_required
    def dashboard():
        vehicles = Vehicle.query.all()
        today = date.today()

        total_vehicles = len(vehicles)
        expired_count = 0
        expiring_today = 0
        expiring_7 = 0
        expiring_30 = 0

        doc_card_stats = {label: {"valid": 0, "expiring": 0, "expired": 0} for label in Vehicle.DOCUMENT_FIELDS}

        for v in vehicles:
            statuses = v.document_statuses()
            worst = v.overall_status()
            if worst == "status-red":
                expired_count += 1
            elif worst == "status-orange":
                expiring_7 += 1
            elif worst == "status-yellow":
                expiring_30 += 1

            for label, info in statuses.items():
                if info["class"] == "status-red":
                    doc_card_stats[label]["expired"] += 1
                elif info["class"] in ("status-orange", "status-yellow"):
                    doc_card_stats[label]["expiring"] += 1
                elif info["class"] == "status-green":
                    doc_card_stats[label]["valid"] += 1

            for label, info in statuses.items():
                if info["expiry"] == today:
                    expiring_today += 1
                    break

        recent_added = Vehicle.query.order_by(Vehicle.created_at.desc()).limit(5).all()
        recent_updated = Vehicle.query.order_by(Vehicle.updated_at.desc()).limit(5).all()

        return render_template(
            "dashboard.html",
            total_vehicles=total_vehicles,
            active_vehicles=total_vehicles - expired_count,
            expired_count=expired_count,
            expiring_today=expiring_today,
            expiring_7=expiring_7,
            expiring_30=expiring_30,
            doc_card_stats=doc_card_stats,
            recent_added=recent_added,
            recent_updated=recent_updated,
        )

    # ---- Vehicle list / search / filter ------------------------------------

    @app.route("/vehicles")
    @login_required
    def vehicle_list():
        query = Vehicle.query

        q = request.args.get("q", "").strip()
        if q:
            like = f"%{q}%"
            query = query.filter(
                db.or_(
                    Vehicle.vehicle_number.ilike(like),
                    Vehicle.chassis_number.ilike(like),
                    Vehicle.engine_number.ilike(like),
                    Vehicle.owner_name.ilike(like),
                    Vehicle.mobile_number.ilike(like),
                    Vehicle.policy_number.ilike(like),
                )
            )

        vehicle_type = request.args.get("vehicle_type", "").strip()
        if vehicle_type:
            query = query.filter(Vehicle.vehicle_type == vehicle_type)

        owner_name = request.args.get("owner_name", "").strip()
        if owner_name:
            query = query.filter(Vehicle.owner_name.ilike(f"%{owner_name}%"))

        district = request.args.get("district", "").strip()
        if district:
            query = query.filter(Vehicle.district == district)

        vehicles = query.order_by(Vehicle.vehicle_number).all()

        status_filter = request.args.get("status", "").strip()
        if status_filter:
            filtered = []
            today = date.today()
            for v in vehicles:
                statuses = v.document_statuses()
                match = False
                for info in statuses.values():
                    expiry = info["expiry"]
                    if expiry is None:
                        continue
                    days_left = (expiry - today).days
                    if status_filter == "expired" and days_left < 0:
                        match = True
                    elif status_filter == "valid" and days_left >= 30:
                        match = True
                    elif status_filter == "today" and days_left == 0:
                        match = True
                    elif status_filter == "2days" and 0 <= days_left <= 2:
                        match = True
                    elif status_filter == "7days" and 0 <= days_left <= 7:
                        match = True
                    elif status_filter == "15days" and 0 <= days_left <= 15:
                        match = True
                    elif status_filter == "30days" and 0 <= days_left <= 30:
                        match = True
                if match:
                    filtered.append(v)
            vehicles = filtered

        vehicle_types = [r[0] for r in db.session.query(Vehicle.vehicle_type).distinct() if r[0]]
        districts = [r[0] for r in db.session.query(Vehicle.district).distinct() if r[0]]
        owner_names = [r[0] for r in db.session.query(Vehicle.owner_name).distinct() if r[0]]

        session['filtered_vehicle_ids'] = [v.id for v in vehicles]

        return render_template(
            "vehicle_list.html",
            vehicles=vehicles,
            vehicle_types=vehicle_types,
            districts=districts,
            owner_names=owner_names,
            filters=request.args,
            today=date.today(),
        )

    # ---- Add vehicle --------------------------------------------------------

    @app.route("/vehicles/add", methods=["GET", "POST"])
    @login_required
    def add_vehicle():
        if request.method == "POST":
            errors = validate_vehicle_form(request.form)
            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template("add_vehicle.html", form=request.form)

            sr_no = request.form.get("sr_no", "").strip()
            if not sr_no:
                count = Vehicle.query.count()
                sr_no = f"SN{count + 1:03d}"

            vehicle = Vehicle(
                sr_no=sr_no,
                vehicle_number=request.form["vehicle_number"].strip().upper(),
                chassis_number=request.form["chassis_number"].strip().upper(),
                engine_number=request.form.get("engine_number", "").strip().upper(),
                owner_name=request.form["owner_name"].strip(),
                mobile_number=request.form["mobile_number"].strip(),
                vehicle_type=request.form.get("vehicle_type", "").strip(),
                district=request.form.get("district", "").strip(),
                registration_date=parse_date(request.form.get("registration_date")),
                puc_expiry=parse_date(request.form.get("puc_expiry")),
                fitness_expiry=parse_date(request.form.get("fitness_expiry")),
                permit_expiry=parse_date(request.form.get("permit_expiry")),
                tax_from=parse_date(request.form.get("tax_from")),
                tax_expiry=parse_date(request.form.get("tax_expiry")),
                tax_mode=request.form.get("tax_mode", "").strip(),
                tax_amount=float(request.form.get("tax_amount", 0) or 0),
                insurance_expiry=parse_date(request.form.get("insurance_expiry")),
                national_permit_expiry=parse_date(request.form.get("national_permit_expiry")),
                state_permit_expiry=parse_date(request.form.get("state_permit_expiry")),
                pollution_certificate_number=request.form.get("pollution_certificate_number", "").strip(),
                insurance_company=request.form.get("insurance_company", "").strip(),
                policy_number=request.form.get("policy_number", "").strip(),
                remarks=request.form.get("remarks", "").strip(),
            )
            db.session.add(vehicle)
            db.session.commit()
            flash(f"Vehicle {vehicle.vehicle_number} added successfully.", "success")
            return redirect(url_for("vehicle_list"))

        return render_template("add_vehicle.html", form={})

    # ---- Edit vehicle --------------------------------------------------------

    @app.route("/vehicles/<int:vehicle_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_vehicle(vehicle_id):
        vehicle = Vehicle.query.get_or_404(vehicle_id)

        if request.method == "POST":
            errors = validate_vehicle_form(request.form, editing_id=vehicle_id)
            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template("edit_vehicle.html", vehicle=vehicle, form=request.form)

            vehicle.vehicle_number = request.form["vehicle_number"].strip().upper()
            vehicle.chassis_number = request.form["chassis_number"].strip().upper()
            vehicle.engine_number = request.form.get("engine_number", "").strip().upper()
            vehicle.owner_name = request.form["owner_name"].strip()
            vehicle.mobile_number = request.form["mobile_number"].strip()
            vehicle.vehicle_type = request.form.get("vehicle_type", "").strip()
            vehicle.district = request.form.get("district", "").strip()
            vehicle.registration_date = parse_date(request.form.get("registration_date"))
            vehicle.puc_expiry = parse_date(request.form.get("puc_expiry"))
            vehicle.fitness_expiry = parse_date(request.form.get("fitness_expiry"))
            vehicle.permit_expiry = parse_date(request.form.get("permit_expiry"))
            vehicle.tax_from = parse_date(request.form.get("tax_from"))
            vehicle.tax_expiry = parse_date(request.form.get("tax_expiry"))
            vehicle.tax_mode = request.form.get("tax_mode", "").strip()
            vehicle.tax_amount = float(request.form.get("tax_amount", 0) or 0)
            vehicle.insurance_expiry = parse_date(request.form.get("insurance_expiry"))
            vehicle.national_permit_expiry = parse_date(request.form.get("national_permit_expiry"))
            vehicle.state_permit_expiry = parse_date(request.form.get("state_permit_expiry"))
            vehicle.pollution_certificate_number = request.form.get("pollution_certificate_number", "").strip()
            vehicle.insurance_company = request.form.get("insurance_company", "").strip()
            vehicle.policy_number = request.form.get("policy_number", "").strip()
            vehicle.remarks = request.form.get("remarks", "").strip()
            vehicle.updated_at = datetime.utcnow()

            db.session.commit()
            flash(f"Vehicle {vehicle.vehicle_number} updated successfully.", "success")
            return redirect(url_for("vehicle_list"))

        return render_template("edit_vehicle.html", vehicle=vehicle, form=vehicle.to_dict())

    @app.route("/vehicles/delete-all", methods=["POST"])
    @login_required
    def delete_all_vehicles():
        count = Vehicle.query.count()
        Vehicle.query.delete()
        try:
            db.session.execute(db.text("DELETE FROM sqlite_sequence WHERE name='vehicles'"))
        except Exception:
            pass
        db.session.commit()
        flash(f"All {count} vehicles deleted.", "success")
        return redirect(url_for("vehicle_list"))

    @app.route("/vehicles/<int:vehicle_id>/delete", methods=["POST"])
    @login_required
    def delete_vehicle(vehicle_id):
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        number = vehicle.vehicle_number
        db.session.delete(vehicle)
        db.session.commit()
        resequence_sr_nos()
        flash(f"Vehicle {number} deleted.", "success")
        return redirect(url_for("vehicle_list"))

    @app.route("/vehicles/<int:vehicle_id>")
    @login_required
    def view_vehicle(vehicle_id):
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        filtered_ids = session.get('filtered_vehicle_ids', [])
        if filtered_ids and vehicle_id in filtered_ids:
            idx = filtered_ids.index(vehicle_id)
            prev_id = filtered_ids[idx - 1] if idx > 0 else None
            next_id = filtered_ids[idx + 1] if idx < len(filtered_ids) - 1 else None
            prev_vehicle = Vehicle.query.get(prev_id) if prev_id else None
            next_vehicle = Vehicle.query.get(next_id) if next_id else None
        else:
            prev_vehicle = Vehicle.query.filter(Vehicle.id < vehicle_id).order_by(Vehicle.id.desc()).first()
            next_vehicle = Vehicle.query.filter(Vehicle.id > vehicle_id).order_by(Vehicle.id.asc()).first()
        return render_template("view_vehicle.html", vehicle=vehicle, prev_vehicle=prev_vehicle, next_vehicle=next_vehicle, today=date.today())

    @app.route("/vehicles/<int:vehicle_id>/print")
    @login_required
    def print_vehicle(vehicle_id):
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        statuses = vehicle.document_statuses()
        valid_count = sum(1 for s in statuses.values() if s["class"] == "status-green")
        total = len(statuses)
        overall = vehicle.overall_status()
        if overall == "status-green":
            badge_label, badge_color = "Excellent", "#22c55e"
        elif overall == "status-yellow":
            badge_label, badge_color = "Renewal Due", "#eab308"
        elif overall == "status-orange":
            badge_label, badge_color = "Urgent", "#f97316"
        elif overall == "status-red":
            badge_label, badge_color = "Action Required", "#ef4444"
        else:
            badge_label, badge_color = "No Data", "#6b7280"
        return render_template(
            "print_vehicle.html",
            vehicle=vehicle,
            statuses=statuses,
            valid_count=valid_count,
            total=total,
            badge_label=badge_label,
            badge_color=badge_color,
        )

    @app.route("/vehicles/print")
    @login_required
    def print_vehicles():
        ids_param = request.args.get("ids", "")
        if not ids_param:
            flash("No vehicles selected for printing.", "error")
            return redirect(url_for("vehicle_list"))
        id_list = [int(x) for x in ids_param.split(",") if x.strip().isdigit()]
        if not id_list:
            flash("No valid vehicles selected.", "error")
            return redirect(url_for("vehicle_list"))
        vehicles = Vehicle.query.filter(Vehicle.id.in_(id_list)).order_by(Vehicle.vehicle_number).all()
        vehicle_data = []
        for v in vehicles:
            statuses = v.document_statuses()
            valid_count = sum(1 for s in statuses.values() if s["class"] == "status-green")
            total = len(statuses)
            overall = v.overall_status()
            if overall == "status-green":
                badge_label, badge_color = "Excellent", "#22c55e"
            elif overall == "status-yellow":
                badge_label, badge_color = "Renewal Due", "#eab308"
            elif overall == "status-orange":
                badge_label, badge_color = "Urgent", "#f97316"
            elif overall == "status-red":
                badge_label, badge_color = "Action Required", "#ef4444"
            else:
                badge_label, badge_color = "No Data", "#6b7280"
            vehicle_data.append({
                "vehicle": v,
                "statuses": statuses,
                "valid_count": valid_count,
                "total": total,
                "badge_label": badge_label,
                "badge_color": badge_color,
            })
        return render_template("print_vehicles.html", vehicle_data=vehicle_data)

    @app.route("/vehicles/<int:vehicle_id>/qr")
    @login_required
    def vehicle_qr(vehicle_id):
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        qr_buffer = generate_vehicle_qr(vehicle)
        return send_file(qr_buffer, mimetype="image/png", download_name=f"qr_{vehicle.vehicle_number}.png")

    @app.route("/vehicles/<int:vehicle_id>/qr-dates")
    @login_required
    def vehicle_qr_dates(vehicle_id):
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        statuses = vehicle.document_statuses()
        return render_template("vehicle_qr_dates.html", vehicle=vehicle, statuses=statuses, today=date.today())

    # ---- WhatsApp reminder helper -------------------------------------------

    @app.route("/vehicles/<int:vehicle_id>/whatsapp/<document_label>")
    @login_required
    def whatsapp_reminder(vehicle_id, document_label):
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        if document_label == "all":
            message = whatsapp_message(vehicle, None, None)
        else:
            field = Vehicle.DOCUMENT_FIELDS.get(document_label)
            if not field:
                abort(404)
            expiry = getattr(vehicle, field)
            if not expiry:
                flash("No expiry date set for this document.", "error")
                return redirect(url_for("vehicle_list"))
            message = whatsapp_message(vehicle, document_label, expiry)
        import urllib.parse
        wa_link = f"https://wa.me/{vehicle.mobile_number}?text={urllib.parse.quote(message)}"
        return redirect(wa_link)

    @app.route("/vehicles/<int:vehicle_id>/whatsapp-expired")
    @login_required
    def whatsapp_expired(vehicle_id):
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        message = whatsapp_expired_reminder(vehicle)
        if not message:
            flash("No expired or expiring documents found for this vehicle.", "error")
            return redirect(url_for("vehicle_list"))
        import urllib.parse
        wa_link = f"https://wa.me/{vehicle.mobile_number}?text={urllib.parse.quote(message)}"
        return redirect(wa_link)

    # ---- Excel Import --------------------------------------------------------

    @app.route("/import", methods=["GET", "POST"])
    @login_required
    def import_excel():
        if request.method == "POST":
            file = request.files.get("file")
            if not file or file.filename == "":
                flash("Please choose a file to import.", "error")
                return redirect(url_for("import_excel"))

            if not allowed_file(file.filename, Config.ALLOWED_IMPORT_EXTENSIONS):
                flash("Unsupported file type. Please upload .xlsx, .xls, .csv, or .json", "error")
                return redirect(url_for("import_excel"))

            try:
                if file.filename.lower().endswith(".json"):
                    raw = json.load(file)
                elif file.filename.lower().endswith(".csv"):
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)
            except Exception as exc:
                flash(f"Could not read file: {exc}", "error")
                return redirect(url_for("import_excel"))

            duplicate_action = request.form.get("duplicate_action", "skip")
            imported, updated, skipped, errors = 0, 0, 0, []

            if file.filename.lower().endswith(".json"):
                if not isinstance(raw, list):
                    flash("JSON file must contain an array of vehicle objects.", "error")
                    return redirect(url_for("import_excel"))
                for idx, record in enumerate(raw):
                    vnum = str(record.get("vehicle_number", "")).strip().upper()
                    chassis = str(record.get("chassis_number", "")).strip().upper()
                    if not vnum or not chassis or vnum.lower() == "nan":
                        skipped += 1
                        errors.append(f"Record {idx + 1}: missing vehicle/chassis number")
                        continue
                    existing = Vehicle.query.filter(
                        db.or_(Vehicle.vehicle_number == vnum, Vehicle.chassis_number == chassis)
                    ).first()
                    if existing:
                        if duplicate_action == "update":
                            update_vehicle_from_record(existing, record)
                            updated += 1
                        else:
                            skipped += 1
                            errors.append(f"Record {idx + 1}: duplicate vehicle {vnum}")
                        continue
                    vehicle = Vehicle(
                        vehicle_number=vnum,
                        chassis_number=chassis,
                        engine_number=str(record.get("engine_number", "")).strip().upper(),
                        owner_name=str(record.get("owner_name", "")).strip(),
                        mobile_number=str(record.get("mobile_number", "")).strip(),
                        vehicle_type=str(record.get("vehicle_type", "")).strip(),
                        district=str(record.get("district", "")).strip(),
                        registration_date=parse_date(record.get("registration_date")),
                        puc_expiry=parse_date(record.get("puc_expiry")),
                        fitness_expiry=parse_date(record.get("fitness_expiry")),
                        permit_expiry=parse_date(record.get("permit_expiry")),
                        tax_from=parse_date(record.get("tax_from")),
                        tax_expiry=parse_date(record.get("tax_expiry")),
                        tax_mode=str(record.get("tax_mode", "")).strip(),
                        tax_amount=float(record.get("tax_amount", 0) or 0),
                        insurance_expiry=parse_date(record.get("insurance_expiry")),
                        national_permit_expiry=parse_date(record.get("national_permit_expiry")),
                        state_permit_expiry=parse_date(record.get("state_permit_expiry")),
                        pollution_certificate_number=str(record.get("pollution_certificate_number", "")).strip(),
                        insurance_company=str(record.get("insurance_company", "")).strip(),
                        policy_number=str(record.get("policy_number", "")).strip(),
                        remarks=str(record.get("remarks", "")).strip(),
                    )
                    db.session.add(vehicle)
                    imported += 1
            else:
                df = normalize_import_dataframe(df)
                required_cols = {"vehicle_number", "chassis_number", "owner_name", "mobile_number"}
                missing = required_cols - set(df.columns)
                if missing:
                    flash(f"Missing required columns: {', '.join(missing)}", "error")
                    return redirect(url_for("import_excel"))

                for idx, row in df.iterrows():
                    vnum = str(row.get("vehicle_number", "")).strip().upper()
                    chassis = str(row.get("chassis_number", "")).strip().upper()
                    if not vnum or not chassis or vnum.lower() == "nan":
                        skipped += 1
                        errors.append(f"Row {idx + 2}: missing vehicle/chassis number")
                        continue
                    existing = Vehicle.query.filter(
                        db.or_(Vehicle.vehicle_number == vnum, Vehicle.chassis_number == chassis)
                    ).first()
                    if existing:
                        if duplicate_action == "update":
                            update_vehicle_from_record(existing, row)
                            updated += 1
                        else:
                            skipped += 1
                            errors.append(f"Row {idx + 2}: duplicate vehicle {vnum}")
                        continue

                    vehicle = Vehicle(
                        vehicle_number=vnum,
                        chassis_number=chassis,
                        owner_name=str(row.get("owner_name", "")).strip(),
                        mobile_number=str(row.get("mobile_number", "")).strip(),
                        puc_expiry=parse_date(row.get("puc_expiry")),
                        fitness_expiry=parse_date(row.get("fitness_expiry")),
                        permit_expiry=parse_date(row.get("permit_expiry")),
                        tax_expiry=parse_date(row.get("tax_expiry")),
                        insurance_expiry=parse_date(row.get("insurance_expiry")),
                    )
                    db.session.add(vehicle)
                    imported += 1

            db.session.commit()
            resequence_sr_nos()
            if updated:
                flash(f"Import complete: {imported} added, {updated} updated, {skipped} skipped.", "success" if imported or updated else "error")
            else:
                flash(f"Import complete: {imported} added, {skipped} skipped.", "success" if imported else "error")
            if errors:
                session["import_errors"] = errors[:20]
            return redirect(url_for("import_excel"))

        import_errors = session.pop("import_errors", [])
        return render_template("import_excel.html", import_errors=import_errors)

    # ---- Excel Export --------------------------------------------------------

    @app.route("/export")
    @login_required
    def export_excel():
        owners = [r[0] for r in db.session.query(Vehicle.owner_name).distinct().order_by(Vehicle.owner_name) if r[0]]
        return render_template("export_excel.html", export_columns=EXPORT_COLUMNS, owners=owners)

    @app.route("/export/run")
    @login_required
    def export_run():
        scope = request.args.get("scope", "all")
        file_format = request.args.get("format", "xlsx")
        selected_columns = request.args.getlist("columns")
        owner_filter = request.args.get("owner_name", "").strip()
        today = date.today()

        vehicles = Vehicle.query.all()

        if owner_filter:
            vehicles = [v for v in vehicles if v.owner_name == owner_filter]

        if scope == "owner_vehicle":
            selected_columns = ["owner_name", "vehicle_number"]
        elif scope == "expired":
            vehicles = [v for v in vehicles if v.overall_status() == "status-red"]
        elif scope == "due7":
            vehicles = [v for v in vehicles if any(
                info["expiry"] and 0 <= (info["expiry"] - today).days <= 7
                for info in v.document_statuses().values()
            )]
        elif scope == "due30":
            vehicles = [v for v in vehicles if any(
                info["expiry"] and 0 <= (info["expiry"] - today).days <= 30
                for info in v.document_statuses().values()
            )]
        elif scope == "custom":
            start = parse_date(request.args.get("start"))
            end = parse_date(request.args.get("end"))
            if start and end:
                vehicles = [v for v in vehicles if any(
                    info["expiry"] and start <= info["expiry"] <= end
                    for info in v.document_statuses().values()
                )]

        data = [v.to_dict() for v in vehicles]

        if selected_columns:
            filtered = []
            for row in data:
                ordered = {}
                for col in selected_columns:
                    if col in row:
                        ordered[col] = row[col]
                filtered.append(ordered)
            data = filtered

        buffer = io.BytesIO()
        scope_names = {
            "all": "All_Vehicles", "owner_vehicle": "Owner_Vehicle_List",
            "expired": "Expired", "due7": "Due_in_7_Days", "due30": "Due_in_30_Days",
        }
        label = scope_names.get(scope, scope.capitalize())
        if scope == "custom":
            s = request.args.get("start", "")[:10]
            e = request.args.get("end", "")[:10]
            label = f"Custom_{s}_to_{e}" if s and e else "Custom_Range"
        if owner_filter:
            label = owner_filter.replace(" ", "_") + "_" + label
        compliance_preset = {"vehicle_number", "chassis_number", "puc_expiry", "fitness_expiry", "tax_expiry"}
        if set(selected_columns) == compliance_preset and scope != "owner_vehicle":
            label += "_Compliance_Summary"
        filename = f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if file_format == "json":
            buffer.write(json.dumps(data, indent=2).encode("utf-8"))
            mimetype = "application/json"
            filename += ".json"
        elif file_format == "csv":
            df = pd.DataFrame(data)
            df.to_csv(buffer, index=False)
            mimetype = "text/csv"
            filename += ".csv"
        else:
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                pd.DataFrame(data).to_excel(writer, index=False, sheet_name="Vehicles")
            mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename += ".xlsx"

        buffer.seek(0)
        return send_file(buffer, mimetype=mimetype, as_attachment=True, download_name=filename)

    # ---- Reports --------------------------------------------------------------

    @app.route("/reports")
    @login_required
    def reports():
        report_type = request.args.get("type", "")
        vehicles = Vehicle.query.all()
        today = date.today()
        results = []

        due_field_map = {
            "puc_due": ("puc_expiry", "PUC"),
            "fitness_due": ("fitness_expiry", "Fitness"),
            "tax_due": ("tax_expiry", "Tax"),
            "permit_due": ("permit_expiry", "Permit"),
            "insurance_due": ("insurance_expiry", "Insurance"),
        }

        if report_type in due_field_map:
            field, label = due_field_map[report_type]
            for v in vehicles:
                expiry = getattr(v, field)
                if expiry and expiry <= today + timedelta(days=30):
                    results.append({"vehicle": v, "field": label, "expiry": expiry})
            results.sort(key=lambda r: r["expiry"])

        elif report_type == "owner_wise":
            grouped = {}
            for v in vehicles:
                grouped.setdefault(v.owner_name, []).append(v)
            results = sorted(grouped.items())

        elif report_type == "type_wise":
            grouped = {}
            for v in vehicles:
                grouped.setdefault(v.vehicle_type or "Unspecified", []).append(v)
            results = sorted(grouped.items())

        elif report_type == "monthly_renewals":
            grouped = {}
            for v in vehicles:
                for label, field in Vehicle.DOCUMENT_FIELDS.items():
                    expiry = getattr(v, field)
                    if expiry and expiry.year == today.year and expiry.month == today.month:
                        grouped.setdefault(f"{label}", []).append((v, expiry))
            results = sorted(grouped.items())

        elif report_type == "yearly_renewals":
            grouped = {}
            for v in vehicles:
                for label, field in Vehicle.DOCUMENT_FIELDS.items():
                    expiry = getattr(v, field)
                    if expiry and expiry.year == today.year:
                        grouped.setdefault(f"{label}", []).append((v, expiry))
            results = sorted(grouped.items())

        return render_template("reports.html", report_type=report_type, results=results)

    # ---- Backup / Restore -------------------------------------------------

    @app.route("/backup", methods=["GET", "POST"])
    @login_required
    def backup():
        db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
        if request.method == "POST":
            action = request.form.get("action")
            if action == "create":
                name, _ = create_backup(db_path, app.config["BACKUP_FOLDER"])
                flash(f"Backup created: {name}", "success")
            elif action == "restore":
                backup_name = request.form.get("backup_name")
                backup_path = os.path.join(app.config["BACKUP_FOLDER"], backup_name)
                if os.path.exists(backup_path):
                    db.session.remove()
                    import shutil
                    shutil.copy2(backup_path, db_path)
                    flash(f"Database restored from {backup_name}.", "success")
                else:
                    flash("Backup file not found.", "error")
            return redirect(url_for("backup"))

        backups = list_backups(app.config["BACKUP_FOLDER"])
        return render_template("backup.html", backups=backups)

    @app.route("/backup/download/<name>")
    @login_required
    def download_backup(name):
        path = os.path.join(app.config["BACKUP_FOLDER"], name)
        if not os.path.exists(path):
            abort(404)
        return send_file(path, as_attachment=True, download_name=name)

    # ---- Settings ------------------------------------------------------------

    @app.route("/settings")
    @login_required
    def settings():
        return render_template("settings.html")

    # ---- Tax Details ----------------------------------------------------------

    @app.route("/vehicles/<int:vehicle_id>/tax")
    @login_required
    def vehicle_tax(vehicle_id):
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        taxes = vehicle.tax_details.order_by(TaxDetail.latest_tax_from.desc()).all()
        return render_template("vehicle_tax.html", vehicle=vehicle, taxes=taxes)

    @app.route("/vehicles/<int:vehicle_id>/tax/add", methods=["GET", "POST"])
    @login_required
    def add_tax(vehicle_id):
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        if request.method == "POST":
            tax = TaxDetail(
                vehicle_id=vehicle.id,
                tax_mode=request.form.get("tax_mode", "").strip(),
                latest_tax_from=parse_date(request.form.get("latest_tax_from")),
                latest_tax_upto=parse_date(request.form.get("latest_tax_upto")),
                tax_amount=float(request.form.get("tax_amount", 0) or 0),
                penalty=float(request.form.get("penalty", 0) or 0),
            )
            db.session.add(tax)
            db.session.commit()
            flash("Tax detail added successfully.", "success")
            return redirect(url_for("vehicle_tax", vehicle_id=vehicle.id))
        return render_template("tax_form.html", vehicle=vehicle, tax=None)

    @app.route("/tax/<int:tax_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_tax(tax_id):
        tax = TaxDetail.query.get_or_404(tax_id)
        if request.method == "POST":
            tax.tax_mode = request.form.get("tax_mode", "").strip()
            tax.latest_tax_from = parse_date(request.form.get("latest_tax_from"))
            tax.latest_tax_upto = parse_date(request.form.get("latest_tax_upto"))
            tax.tax_amount = float(request.form.get("tax_amount", 0) or 0)
            tax.penalty = float(request.form.get("penalty", 0) or 0)
            db.session.commit()
            flash("Tax detail updated.", "success")
            return redirect(url_for("vehicle_tax", vehicle_id=tax.vehicle_id))
        return render_template("tax_form.html", vehicle=tax.vehicle, tax=tax)

    @app.route("/tax/<int:tax_id>/delete", methods=["POST"])
    @login_required
    def delete_tax(tax_id):
        tax = TaxDetail.query.get_or_404(tax_id)
        vid = tax.vehicle_id
        db.session.delete(tax)
        db.session.commit()
        flash("Tax detail deleted.", "success")
        return redirect(url_for("vehicle_tax", vehicle_id=vid))

    # ---- API used by dashboard charts / AJAX --------------------------------

    @app.route("/api/vehicle/<int:vehicle_id>")
    @login_required
    def api_vehicle(vehicle_id):
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        return jsonify(vehicle.to_dict())


def update_vehicle_from_record(vehicle, record):
    """Update an existing vehicle from an imported record dict."""
    if "engine_number" in record:
        vehicle.engine_number = str(record.get("engine_number", "") or vehicle.engine_number or "").strip().upper()
    if "owner_name" in record:
        vehicle.owner_name = str(record.get("owner_name", "") or vehicle.owner_name or "").strip()
    if "mobile_number" in record:
        vehicle.mobile_number = str(record.get("mobile_number", "") or vehicle.mobile_number or "").strip()
    if "vehicle_type" in record:
        vehicle.vehicle_type = str(record.get("vehicle_type", "") or vehicle.vehicle_type or "").strip()
    if "district" in record:
        vehicle.district = str(record.get("district", "") or vehicle.district or "").strip()
    if "registration_date" in record:
        parsed = parse_date(record.get("registration_date"))
        if parsed:
            vehicle.registration_date = parsed
    if "puc_expiry" in record:
        parsed = parse_date(record.get("puc_expiry"))
        if parsed:
            vehicle.puc_expiry = parsed
    if "fitness_expiry" in record:
        parsed = parse_date(record.get("fitness_expiry"))
        if parsed:
            vehicle.fitness_expiry = parsed
    if "permit_expiry" in record:
        parsed = parse_date(record.get("permit_expiry"))
        if parsed:
            vehicle.permit_expiry = parsed
    if "tax_from" in record:
        parsed = parse_date(record.get("tax_from"))
        if parsed:
            vehicle.tax_from = parsed
    if "tax_expiry" in record:
        parsed = parse_date(record.get("tax_expiry"))
        if parsed:
            vehicle.tax_expiry = parsed
    if "tax_mode" in record:
        vehicle.tax_mode = str(record.get("tax_mode", "") or vehicle.tax_mode or "").strip()
    if "tax_amount" in record:
        val = record.get("tax_amount")
        if val is not None:
            vehicle.tax_amount = float(val or 0)
    if "insurance_expiry" in record:
        parsed = parse_date(record.get("insurance_expiry"))
        if parsed:
            vehicle.insurance_expiry = parsed
    if "national_permit_expiry" in record:
        parsed = parse_date(record.get("national_permit_expiry"))
        if parsed:
            vehicle.national_permit_expiry = parsed
    if "state_permit_expiry" in record:
        parsed = parse_date(record.get("state_permit_expiry"))
        if parsed:
            vehicle.state_permit_expiry = parsed
    if "pollution_certificate_number" in record:
        vehicle.pollution_certificate_number = str(record.get("pollution_certificate_number", "") or vehicle.pollution_certificate_number or "").strip()
    if "insurance_company" in record:
        vehicle.insurance_company = str(record.get("insurance_company", "") or vehicle.insurance_company or "").strip()
    if "policy_number" in record:
        vehicle.policy_number = str(record.get("policy_number", "") or vehicle.policy_number or "").strip()
    if "remarks" in record:
        vehicle.remarks = str(record.get("remarks", "") or vehicle.remarks or "").strip()
    vehicle.updated_at = datetime.utcnow()


def validate_vehicle_form(form, editing_id=None):
    errors = []
    vehicle_number = form.get("vehicle_number", "").strip()
    chassis_number = form.get("chassis_number", "").strip()
    mobile_number = form.get("mobile_number", "").strip()
    owner_name = form.get("owner_name", "").strip()

    if not vehicle_number:
        errors.append("Vehicle Number is required.")
    if not chassis_number:
        errors.append("Chassis Number is required.")
    if not owner_name:
        errors.append("Owner Name is required.")
    if mobile_number and not mobile_number.replace("+", "").isdigit():
        errors.append("Mobile Number should be numeric.")

    if vehicle_number:
        query = Vehicle.query.filter(Vehicle.vehicle_number == vehicle_number.upper())
        if editing_id:
            query = query.filter(Vehicle.id != editing_id)
        if query.first():
            errors.append(f"Vehicle Number {vehicle_number} already exists.")

    if chassis_number:
        query = Vehicle.query.filter(Vehicle.chassis_number == chassis_number.upper())
        if editing_id:
            query = query.filter(Vehicle.id != editing_id)
        if query.first():
            errors.append(f"Chassis Number {chassis_number} already exists.")

    return errors


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
