# Internal Asset and Equipment Tracker

A Flask web app for tracking internal company assets and equipment — assignments, maintenance history, vendors, warranty alerts, QR-code lookups, and audit logs.

## Features
- Asset inventory management (add/edit/view, QR code generation & scanning)
- Employee assignment tracking (assign/return equipment)
- Maintenance logging per asset
- Vendor management
- Warranty expiry alerts
- Audit logs
- Reports
- Role-based login (Admin / Manager)

## Setup

1. Clone the repo and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in real values:
   ```bash
   cp .env.example .env
   ```
   - `SECRET_KEY` — any random string, used for Flask sessions
   - `MAIL_USERNAME` / `MAIL_PASSWORD` — Gmail account + [app password](https://support.google.com/accounts/answer/185833) used to send warranty/maintenance alert emails
   - `DEFAULT_ADMIN_PASSWORD` — password set for the auto-created `admin` user on first run

3. Load the environment variables (e.g. via `python-dotenv`, or export them in your shell) and run:
   ```bash
   python app.py
   ```

4. (Optional) Seed sample data for local development:
   ```bash
   python seed_data.py
   ```
   This creates demo users `admin` / `admin123` and `manager` / `manager123` — for local dev only, don't use in production.

## Notes
- The SQLite database (`instance/asset_tracker.db`) and uploaded files are gitignored — each environment should generate/manage its own.
- Never commit real credentials — use environment variables as shown above.
