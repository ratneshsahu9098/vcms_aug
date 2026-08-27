# Vehicle Compliance Management System (VCMS)

A Flask-based web application for managing and tracking vehicle compliance documents. Monitor expiry dates for PUC, Fitness, Permit, Tax, and Insurance certificates with automated status tracking, reminders, and reporting.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Production Notes](#production-notes)

---

## Features

### Dashboard
- Total vehicle count with active/expired breakdown
- Document-level statistics (valid, expiring, expired)
- Expiring today / 7-day / 30-day summary cards
- Recent activity feeds (newly added and recently updated vehicles)

### Vehicle Management
- Full CRUD operations (Create, Read, Update, Delete)
- Duplicate detection on vehicle number and chassis number
- Automatic serial number sequencing (`SN001`, `SN002`, ...)
- Bulk delete all vehicles
- Print-ready vehicle detail pages (single and batch)

### Document Compliance Tracking
Five tracked document types with color-coded status:

| Status | Color | Condition |
|--------|-------|-----------|
| Valid | Green | More than 30 days until expiry |
| Expiring Soon (30d) | Yellow | 1-30 days until expiry |
| Expiring Soon (7d) | Orange | 1-7 days until expiry |
| Expires Today | Orange | Expires on current date |
| Expired | Red | Past expiry date |
| N/A | Gray | No expiry date set |

Overall vehicle status is derived from the worst-case document status.

### Search & Filtering
- **Search**: Partial match across vehicle number, chassis number, engine number, owner name, mobile number, and policy number
- **Filter by status**: expired, valid, today, 7 days, 15 days, 30 days
- **Filter by type**: vehicle type, owner, district

### Import / Export
- **Import formats**: Excel (`.xlsx`, `.xls`), CSV (`.csv`), JSON (`.json`)
- **Column mapping**: Automatically maps common header names to internal fields
- **Validation**: Skips duplicates, reports errors with row numbers
- **Export scopes**: All vehicles, expired only, due in 7/30 days, custom date range, owner-vehicle list
- **Export formats**: Excel, CSV, JSON
- **Column selection**: Choose which fields to include in the export

### Reports
- Per-document due reports (PUC, Fitness, Tax, Permit, Insurance)
- Owner-wise vehicle grouping
- Vehicle type-wise grouping
- Monthly renewals (current month)
- Yearly renewals (current year)

### Communication
- **WhatsApp reminders**: Pre-filled messages via `wa.me` links with full vehicle compliance details
- **Click-to-call**: `tel:` links on mobile numbers

### QR Code Generation
- Generates QR codes containing structured vehicle compliance data
- Includes vehicle details, document statuses, and a report ID
- Downloadable as PNG images

### Backup & Restore
- One-click timestamped SQLite database backups
- Restore from any previous backup
- Download backup files

### UI/UX
- Dark mode interface (charcoal/dark-gray palette)
- Responsive sidebar navigation (collapsible on mobile)
- Bootstrap 5 + Font Awesome icons
- Auto-dismissing flash messages
- Back navigation button

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Flask 3.0.3 |
| Database | SQLite via Flask-SQLAlchemy 3.1.1 |
| Frontend | Bootstrap 5.3.3, Font Awesome 6.5.1 |
| Data Processing | pandas 2.2.2, openpyxl 3.1.5 |
| QR Generation | qrcode 7.4.2, Pillow 10.4.0 |
| Auth | Werkzeug 3.0.3 (password hashing) |

---

## Project Structure

```
vcms/
├── app.py              # Flask app factory, routes, and auth logic
├── models.py           # SQLAlchemy models (Vehicle, TaxDetail)
├── config.py           # Configuration class
├── utils.py            # Helpers: date parsing, import/export, backups, QR
├── seed_data.py        # Sample data loader for demo/testing
├── requirements.txt    # Python dependencies
├── vehicles.db         # SQLite database (auto-created)
├── templates/          # Jinja2 HTML templates
│   ├── layout.html         # Base layout with sidebar navigation
│   ├── login.html          # Login page
│   ├── dashboard.html      # Main dashboard
│   ├── vehicle_list.html   # Vehicle list with search/filter
│   ├── add_vehicle.html    # Add vehicle form
│   ├── edit_vehicle.html   # Edit vehicle form
│   ├── view_vehicle.html   # Vehicle detail view
│   ├── print_vehicle.html  # Single vehicle print view
│   ├── print_vehicles.html # Batch print view
│   ├── import_excel.html   # Import page
│   ├── export_excel.html   # Export configuration page
│   ├── reports.html        # Reports page
│   ├── backup.html         # Backup management
│   ├── settings.html       # Settings page
│   ├── vehicle_tax.html    # Tax details list
│   └── tax_form.html       # Tax add/edit form
├── static/
│   ├── css/style.css   # Custom dark theme styles
│   └── js/script.js    # Sidebar toggle and flash auto-dismiss
├── uploads/            # User file uploads
├── exports/            # Generated export files
└── backups/            # Database backup files
```

---

## Setup & Installation

### Prerequisites
- Python 3.9+

### Install

```bash
cd vcms_aug-main
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run

```bash
python app.py
```

Visit **http://localhost:5000**. The database (`vehicles.db`) is created automatically on first run.

### Load Sample Data (Optional)

```bash
python seed_data.py
```

This inserts 5 demo vehicles with varied expiry statuses for testing.

---

## Configuration

Environment variables override defaults in `config.py`:

| Variable | Purpose | Default |
|----------|---------|---------|
| `VCMS_SECRET_KEY` | Flask session secret key | `dev-secret-key-change-in-production` |
| `VCMS_DATABASE_URI` | SQLAlchemy database URI | `sqlite:///vehicles.db` |
| `VCMS_LOGIN_REQUIRED` | Require login for all pages | `true` |
| `VCMS_ADMIN_USER` | Admin login username | `admin` |
| `VCMS_ADMIN_PASSWORD` | Admin login password | `admin123` |

Example (Linux/macOS):

```bash
export VCMS_SECRET_KEY="your-strong-secret-key"
export VCMS_ADMIN_USER="admin"
export VCMS_ADMIN_PASSWORD="strong-password-here"
export VCMS_LOGIN_REQUIRED="true"
```

---

## Usage

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | `/` | Overview of all vehicle compliance stats |
| Vehicle List | `/vehicles` | Search, filter, and manage all vehicles |
| Add Vehicle | `/vehicles/add` | Add a new vehicle record |
| Import | `/import` | Bulk import from Excel/CSV/JSON |
| Export | `/export` | Configure and download vehicle data |
| Reports | `/reports` | Generate compliance reports |
| Backup | `/backup` | Create, restore, or download backups |
| Settings | `/settings` | View current configuration |
| Vehicle Tax | `/vehicles/<id>/tax` | View tax payment history |

### Default Login

- **Username**: `admin`
- **Password**: `admin123`

Change these via environment variables or directly in `config.py`.

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/vehicle/<id>` | GET | Returns vehicle data as JSON |

---

## Production Notes

This application uses simple session-based single-user authentication. For production or multi-user deployments, consider:

- **Flask-Login** with hashed passwords stored in the database
- **Flask-WTF** for CSRF protection on all forms
- **PostgreSQL** or **MySQL** instead of SQLite for concurrent access
- **Gunicorn** or **uWSGI** as a production WSGI server
- **Nginx** as a reverse proxy with HTTPS
- Move `SECRET_KEY` and credentials to a `.env` file or secrets manager
- Add rate limiting and input sanitization for public-facing deployments
