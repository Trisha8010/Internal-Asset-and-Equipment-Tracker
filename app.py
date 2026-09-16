from flask import Flask, render_template, request, redirect, flash
from datetime import datetime, timedelta
# Security tools removed
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from extensions import db
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import User, Employee, Asset, AssetAssignment, Maintenance, Vendor, AssetRequest, AuditLog, SystemSetting
from apscheduler.schedulers.background import BackgroundScheduler
from functools import wraps
import qrcode
import io
import base64
import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads/assets'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///asset_tracker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

# Ensure upload directory exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db.init_app(app)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')

mail = Mail(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# -------------------------------
# HELPER: Notification Engine
# -------------------------------
def get_notifications():
    if not current_user.is_authenticated:
        return []
    
    alerts = []
    today = datetime.today().date()
    next_30 = today + timedelta(days=30)
    
    # 1. Warranty Alerts
    expiring = Asset.query.filter(Asset.warranty_expiry >= today, Asset.warranty_expiry <= next_30).all()
    for a in expiring:
        alerts.append({'type': 'Warranty', 'msg': f'{a.asset_name} warranty expires soon', 'date': a.warranty_expiry})
        
    # 2. Maintenance Alerts
    maint = Maintenance.query.filter_by(status='In Progress').all()
    for m in maint:
        alerts.append({'type': 'Maintenance', 'msg': f'Intervention in progress: {m.asset.asset_name}', 'date': m.maintenance_date})
        
    return alerts

@app.context_processor
def inject_global_data():
    setting = SystemSetting.query.filter_by(key='company_name').first()
    company_name = setting.value if setting else "AssetSys Pro"
    company_logo = setting.company_logo if setting else None
    return {
        'today': datetime.today().date(),
        'calc_value': calculate_current_value,
        'notifications': get_notifications(),
        'company_name': company_name,
        'company_logo_file': company_logo
    }

@app.before_request
def check_setup():
    # List of endpoints that don't require company name to be set
    allowed_endpoints = ['setup_company', 'static']
    
    # Check if company_name is set
    setting = SystemSetting.query.filter_by(key='company_name').first()
    
    if not setting and request.endpoint not in allowed_endpoints:
        return redirect('/setup_company')

@app.route('/setup_company', methods=['GET', 'POST'])
def setup_company():
    # If already set, don't allow re-entry through this route
    if SystemSetting.query.filter_by(key='company_name').first():
        return redirect('/')

    if request.method == "POST":
        company_name = request.form.get('company_name')
        
        # Handle Logo Upload
        logo_filename = None
        if 'company_logo' in request.files:
            file = request.files['company_logo']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"logo_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                logo_filename = filename

        if company_name:
            new_setting = SystemSetting(key='company_name', value=company_name, company_logo=logo_filename)
            db.session.add(new_setting)
            db.session.commit()
            flash(f"Welcome to {company_name}! Workspace configured.")
            return redirect('/')
    
    return render_template("setup_company.html")

# -------------------------------
# HELPER: Audit Logging
# -------------------------------
def log_action(action, target_type=None, target_id=None, details=None):
    if current_user.is_authenticated:
        new_log = AuditLog(
            user_id=current_user.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details
        )
        db.session.add(new_log)
        db.session.commit()

# -------------------------------
# HELPER: Depreciation Calculator
# -------------------------------
def calculate_current_value(asset):
    if not asset.purchase_cost or not asset.purchase_date:
        return 0.0
    
    years_passed = (datetime.today().date() - asset.purchase_date).days / 365.25
    # Straight-line depreciation: Value = Cost - (Cost * Rate * Years)
    # Rate is assumed to be annual percentage (e.g., 0.2 for 20%)
    depreciation_amount = asset.purchase_cost * (asset.depreciation_rate / 100) * years_passed
    current_value = max(0, asset.purchase_cost - depreciation_amount)
    return round(current_value, 2)

# -------------------------------
# RBAC DECORATORS
# -------------------------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'Admin':
            flash("Access denied: Admin permissions required.")
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

def manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['Admin', 'Manager']:
            flash("Access denied: Manager permissions required.")
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function


# HOME PAGE
@app.route('/')
@login_required
def index():
    today = datetime.today().date()
    upcoming = today + timedelta(days=30)

    # 1. Get counts
    total_assets = Asset.query.count()
    available_assets = Asset.query.filter_by(status="Available").count()
    assigned_assets = Asset.query.filter_by(status="Assigned").count()
    expiring_assets = Asset.query.filter(
    Asset.warranty_expiry >= today,
    Asset.warranty_expiry <= upcoming
).count()

    
    # 2. Check if assets exist
    has_assets = total_assets > 0

    # 3. Fetch data for graphs if assets exist
    if has_assets:
        # Example: Group assets by type for the bar chart
        from sqlalchemy import func
        results = db.session.query(
            Asset.asset_type, 
            func.count(Asset.id)
        ).group_by(Asset.asset_type).all()
        
        # Format for Chart.js
        types = [result[0] for result in results]
        type_counts = [result[1] for result in results]
    else:
        types = []
        type_counts = []

    return render_template(
        "index.html",
        total_assets=total_assets,
        available_assets=available_assets,
        assigned_assets=assigned_assets,
        expiring_assets=expiring_assets,
        has_assets=has_assets,
        types=types,
        type_counts=type_counts,
        today=today
    )
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
# -------------------------------
# SMART ALERT FUNCTION
# -------------------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']

        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash("Username already exists!")
            return redirect('/signup')

        hashed_password = generate_password_hash(password)

        # First user becomes Admin automatically
        role = "Admin" if User.query.count() == 0 else "Employee"

        new_user = User(username=username, password=hashed_password, role=role)
        db.session.add(new_user)
        db.session.commit()

        log_action("User Signup", "User", new_user.id, f"Registered as {role}")

        flash("Account created successfully! Please login.")
        return redirect('/login')

    return render_template("signup.html")
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Logged in successfully!")
            return redirect('/')

        flash("Invalid username or password!")
        return redirect('/login')

    return render_template("login.html")
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out successfully!")
    return redirect('/login')
@app.route('/profile')
@login_required
def profile():
    return render_template("profile.html", user=current_user)

@app.route('/my_assets')
@login_required
def my_assets():
    # Find the employee record linked to this user
    employee = Employee.query.filter_by(user_id=current_user.id).first()
    
    # Fallback: find by email if not explicitly linked
    if not employee:
        # Assuming username could be email or we could add email to User model
        # For now, let's just show an empty list or a message if not linked
        assignments = []
    else:
        assignments = AssetAssignment.query.filter_by(employee_id=employee.id, return_date=None).all()
        
    return render_template("my_assets.html", assignments=assignments, employee=employee)

def check_and_send_alerts():
    with app.app_context():

        today = datetime.today().date()
        next_30_days = today + timedelta(days=30)

        # 1️⃣ Expiring within 30 days
        expiring = Asset.query.filter(
            Asset.warranty_expiry >= today,
            Asset.warranty_expiry <= next_30_days
        ).all()

        # 2️⃣ Already expired
        expired = Asset.query.filter(
            Asset.warranty_expiry < today
        ).all()

        # 3️⃣ Overdue assignments (assigned more than 30 days, not returned)
        overdue_assignments = AssetAssignment.query.filter(
            AssetAssignment.return_date == None,
            AssetAssignment.assigned_date < today - timedelta(days=30)
        ).all()

        # 4️⃣ Assets under maintenance
        maintenance_assets = Asset.query.filter_by(status="Under Maintenance").all()

        # If nothing to report → exit
        if not (expiring or expired or overdue_assignments or maintenance_assets):
            print("No alerts to send today.")
            return

        # -------------------------------
        # BUILD EMAIL BODY
        # -------------------------------
        body = "🚨 SMART ALERT REPORT\n\n"

        if expiring:
            body += "⚠ EXPIRING WITHIN 30 DAYS:\n"
            for asset in expiring:
                body += f"- {asset.asset_name} (Expires: {asset.warranty_expiry})\n"
            body += "\n"

        if expired:
            body += "❌ EXPIRED WARRANTIES:\n"
            for asset in expired:
                body += f"- {asset.asset_name} (Expired: {asset.warranty_expiry})\n"
            body += "\n"

        if overdue_assignments:
            body += "🔁 OVERDUE ASSIGNMENTS:\n"
            for assignment in overdue_assignments:
                body += f"- {assignment.asset.asset_name} assigned to {assignment.employee.name} on {assignment.assigned_date}\n"
            body += "\n"

        if maintenance_assets:
            body += "🔧 UNDER MAINTENANCE:\n"
            for asset in maintenance_assets:
                body += f"- {asset.asset_name}\n"
            body += "\n"

        # -------------------------------
        # SEND EMAIL
        # -------------------------------
        try:
            msg = Message(
                subject="Asset Tracker Smart Alerts 🚨",
                recipients=["admin@example.com"],  # 👈 UPDATE THIS TO YOUR REAL EMAIL
                body=body
            )

            mail.send(msg)
            print("Smart alert email sent successfully.")

        except Exception as e:
            print("Error sending alert email:", e)


# ADD EMPLOYEE
@app.route('/add_employee', methods=['GET', 'POST'])
def add_employee():
    if request.method == "POST":
        employee_code = request.form['employee_code']
        name = request.form['name']
        department = request.form['department']
        email = request.form['email']

        # Check duplicate employee code
        if Employee.query.filter_by(employee_code=employee_code).first():
            flash("Employee code already exists!")
            return redirect('/add_employee')

        # Check duplicate email
        if Employee.query.filter_by(email=email).first():
            flash("Email already exists!")
            return redirect('/add_employee')

        new_employee = Employee(
            employee_code=employee_code,
            name=name,
            department=department,
            email=email
        )

        db.session.add(new_employee)
        db.session.commit()

        flash("Employee added successfully!")
        return redirect('/')

    return render_template("add_employee.html")

@app.route('/add_asset', methods=['GET', 'POST'])
@login_required
@manager_required
def add_asset():
    vendors = Vendor.query.all()
    if request.method == "POST":
        vendor_id = request.form.get('vendor_id')
        status = request.form.get('status')
        asset_name = request.form.get('name')
        asset_type = request.form.get('type')
        category = request.form.get('category')
        serial_number = request.form.get('serial_number')
        purchase_cost_str = request.form.get('purchase_cost')
        purchase_cost = float(purchase_cost_str) if purchase_cost_str else 0.0
        depreciation_rate_str = request.form.get('depreciation_rate')
        depreciation_rate = float(depreciation_rate_str) if depreciation_rate_str else 0.0
        purchase_date = request.form.get('purchase_date')
        warranty = request.form.get('warranty')
        location = request.form.get('location')
        
        # Handle Image Upload
        image_filename = None
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Add timestamp to filename to avoid collisions
                filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_filename = filename

        purchase_date_obj = datetime.strptime(purchase_date, "%Y-%m-%d").date()
        warranty_obj = datetime.strptime(warranty, "%Y-%m-%d").date()

        new_asset = Asset(
            asset_name=asset_name,
            asset_type=asset_type,
            category=category,
            serial_number=serial_number,
            purchase_date=purchase_date_obj,
            purchase_cost=purchase_cost,
            depreciation_rate=depreciation_rate,
            warranty_expiry=warranty_obj,
            location=location,
            vendor_id=vendor_id if vendor_id else None,
            status=status,
            image_filename=image_filename
        )

        db.session.add(new_asset)
        db.session.commit()

        log_action("Added Asset", "Asset", new_asset.id, f"Asset: {asset_name}")
        flash("Asset added successfully!")
        return redirect('/')

    return render_template("add_asset.html", vendors=vendors)

# VENDORS
@app.route('/vendors', methods=['GET', 'POST'])
@login_required
@manager_required
def vendors():
    if request.method == "POST":
        name = request.form['name']
        contact = request.form['contact']
        new_vendor = Vendor(name=name, contact_details=contact)
        db.session.add(new_vendor)
        db.session.commit()
        flash("Vendor added successfully!")
        return redirect('/vendors')
    
    all_vendors = Vendor.query.all()
    return render_template("vendors.html", vendors=all_vendors)

# VIEW ASSETS
@app.route('/view_assets')
@login_required
def view_assets():
    assets = Asset.query.all() 
    return render_template("view_assets.html", assets=assets)

# SCAN QR
@app.route('/scan_qr')
@login_required
def scan_qr():
    return render_template("scan_qr.html")

# ASSET DETAILS & QR
@app.route('/asset/<int:id>')
@login_required
def asset_details(id):
    asset = Asset.query.get_or_404(id)
    
    # Generate QR Code with a direct link
    base_url = request.host_url.rstrip('/')
    asset_url = f"{base_url}/asset/{asset.id}"
    qr_data = asset_url # The QR code now contains the direct URL
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buf = io.BytesIO()
    img.save(buf)
    qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    
    return render_template("asset_details.html", asset=asset, qr_code=qr_b64)

import csv
from flask import send_file

# -------------------------------
# BULK DATA OPERATIONS
# -------------------------------
@app.route('/export_assets')
@login_required
@manager_required
def export_assets():
    assets = Asset.query.all()
    
    # Create a string buffer
    si = io.StringIO()
    cw = csv.writer(si)
    
    # Header row
    cw.writerow(['ID', 'Name', 'Type', 'Category', 'Serial', 'Cost', 'Current Value', 'Location', 'Status'])
    
    for a in assets:
        curr_val = calculate_current_value(a)
        cw.writerow([
            a.id, a.asset_name, a.asset_type, a.category, a.serial_number, 
            a.purchase_cost, curr_val, a.location, a.status
        ])
    
    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)
    
    log_action("Exported Assets", "System", None, f"Exported {len(assets)} records")
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'assets_export_{datetime.now().strftime("%Y%m%d")}.csv'
    )

@app.route('/import_assets', methods=['POST'])
@login_required
@manager_required
def import_assets():
    if 'file' not in request.files:
        flash("No file part!")
        return redirect('/view_assets')
    
    file = request.files['file']
    if file.filename == '':
        flash("No selected file!")
        return redirect('/view_assets')
    
    if file and file.filename.endswith('.csv'):
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.reader(stream)
        next(csv_input)  # Skip header
        
        count = 0
        for row in csv_input:
            try:
                # Basic mapping: Name[1], Type[2], Category[3], Serial[4], Cost[5]
                new_asset = Asset(
                    asset_name=row[1],
                    asset_type=row[2],
                    category=row[3],
                    serial_number=row[4],
                    purchase_cost=float(row[5]) if row[5] else 0.0,
                    purchase_date=datetime.today().date(),
                    warranty_expiry=datetime.today().date() + timedelta(days=365),
                    status="Available"
                )
                db.session.add(new_asset)
                count += 1
            except Exception as e:
                print(f"Error importing row: {e}")
                continue
        
        db.session.commit()
        log_action("Imported Assets", "System", None, f"Imported {count} records from CSV")
        flash(f"Successfully imported {count} assets!")
    else:
        flash("Invalid file format. Please upload a CSV.")
        
    return redirect('/view_assets')

# REPORTS PAGE
@app.route('/reports')
@login_required
@manager_required
def reports():
    # Financial Stats
    total_value = db.session.query(db.func.sum(Asset.purchase_cost)).scalar() or 0
    total_maintenance = db.session.query(db.func.sum(Maintenance.cost)).scalar() or 0
    
    # Assets by category
    from sqlalchemy import func
    cat_results = db.session.query(Asset.category, func.count(Asset.id)).group_by(Asset.category).all()
    categories = [r[0] if r[0] else 'Uncategorized' for r in cat_results]
    cat_counts = [r[1] for r in cat_results]
    
    return render_template("reports.html", 
                         total_value=round(total_value, 2), 
                         total_maintenance=round(total_maintenance, 2),
                         categories=categories,
                         cat_counts=cat_counts)

# ASSIGN ASSET
@app.route('/assign_asset', methods=['GET', 'POST'])
def assign_asset():
    employees = Employee.query.all()
    assets = Asset.query.filter_by(status="Available").all()

    if request.method == "POST":
        employee_id = request.form['employee_id']
        asset_id = request.form['asset_id']
        assigned_date = datetime.strptime(request.form['assigned_date'], "%Y-%m-%d").date()

        assignment = AssetAssignment(
            employee_id=employee_id,
            asset_id=asset_id,
            assigned_date=assigned_date
        )

        asset = Asset.query.get(asset_id)
        asset.status = "Assigned"

        db.session.add(assignment)
        db.session.commit()

        # Feature 5: Real-time Email Alert
        try:
            setting = SystemSetting.query.filter_by(key='company_name').first()
            company_name = setting.value if setting else "AssetSys Pro"
            employee = Employee.query.get(employee_id)
            msg = Message(
                subject=f"Asset Assignment: {asset.asset_name}",
                recipients=[employee.email],
                body=f"Hello {employee.name},\n\nThe following asset has been assigned to you:\n\n"
                     f"Asset: {asset.asset_name}\n"
                     f"Type: {asset.asset_type}\n"
                     f"Date: {assigned_date}\n\n"
                     f"Please ensure proper maintenance and care of the equipment.\n\n"
                     f"Regards,\n{company_name} Management"
            )
            mail.send(msg)
            print(f"Assignment email sent to {employee.email}")
        except Exception as e:
            print(f"Email failed: {e}")

        log_action("Assigned Asset", "Asset", asset_id, f"To Employee ID: {employee_id}")
        flash("Asset assigned successfully!")
        return redirect('/')

    return render_template("assign_asset.html", employees=employees, assets=assets)

# VIEW ASSIGNMENTS
@app.route('/view_assignments')
def view_assignments():
    assignments = AssetAssignment.query.filter_by(return_date=None).all()
    return render_template("view_assignments.html", assignments=assignments)

# RETURN ASSET
@app.route('/return_asset', methods=['GET', 'POST'])
def return_asset():
    assignments = AssetAssignment.query.filter_by(return_date=None).all()

    if request.method == "POST":
        assignment_id = request.form['assignment_id']
        return_date = datetime.strptime(request.form['return_date'], "%Y-%m-%d").date()

        assignment = AssetAssignment.query.get(assignment_id)
        assignment.return_date = return_date

        asset = Asset.query.get(assignment.asset_id)
        asset.status = "Available"

        db.session.commit()

        log_action("Returned Asset", "Asset", asset.id, f"From Assignment ID: {assignment_id}")
        flash("Asset returned successfully!")
        return redirect('/')

    return render_template("return_asset.html", assignments=assignments)

# EDIT ASSET
@app.route('/edit_asset/<int:id>', methods=['GET', 'POST'])
def edit_asset(id):
    asset = Asset.query.get_or_404(id)
    
    if request.method == "POST":
        asset.asset_name = request.form['name']
        asset.asset_type = request.form['type']
        asset.purchase_date = datetime.strptime(request.form['purchase_date'], "%Y-%m-%d").date()
        asset.warranty_expiry = datetime.strptime(request.form['warranty'], "%Y-%m-%d").date()
        asset.status = request.form['status']
        
        db.session.commit()
        flash("Asset updated successfully!")
        return redirect('/view_assets')
        
    return render_template("edit_asset.html", asset=asset)

# DELETE ASSET
@app.route('/delete_asset/<int:id>')
def delete_asset(id):
    asset = Asset.query.get_or_404(id)
    
    # Check if asset is assigned before deleting
    if asset.status == "Assigned":
        flash("Cannot delete an assigned asset!")
        return redirect('/view_assets')
        
    db.session.delete(asset)
    db.session.commit()
    
    flash("Asset deleted successfully!")
    return redirect('/view_assets')

@app.route('/view_maintenance')
def view_maintenance():
    # Fetch maintenance records joined with asset details
    logs = db.session.query(
        Asset.asset_name, 
        Asset.asset_type, 
        Maintenance.maintenance_date, 
        Maintenance.description
    ).join(Asset).all()
    
    return render_template('view_maintenance.html', logs=logs)

@app.route('/warranty_alerts')
def warranty_alert():
    today = datetime.today().date()
    next_30_days = today + timedelta(days=30)

    # Get assets expiring within next 30 days but not already expired
    expiring_assets = Asset.query.filter(
        Asset.warranty_expiry >= today,
        Asset.warranty_expiry <= next_30_days
    ).all()

    # Format exactly how your HTML expects (tuple format)
    alerts = [
        (asset.asset_name, asset.asset_type, asset.warranty_expiry)
        for asset in expiring_assets
    ]

    return render_template("warranty_alerts.html", alerts=alerts)


@app.route('/add_maintenance', methods=['GET', 'POST'])
def add_maintenance():
    assets = Asset.query.all()

    if request.method == "POST":
        asset_id = request.form['asset_id']
        maintenance_date = datetime.strptime(
            request.form['maintenance_date'], "%Y-%m-%d"
        ).date()
        cost = float(request.form['cost'])
        description = request.form['description']

        # Create maintenance record
        new_maintenance = Maintenance(
            asset_id=asset_id,
            maintenance_date=maintenance_date,
            cost=cost,
            description=description,
            status="In Progress"
        )

        # Change asset status
        asset = Asset.query.get(asset_id)
        asset.status = "Under Maintenance"

        db.session.add(new_maintenance)
        db.session.commit()

        log_action("Maintenance Logged", "Asset", asset_id, f"Cost: {cost}")
        flash("Maintenance record added successfully!")
        return redirect('/view_maintenance')

    return render_template("add_maintenance.html", assets=assets)

@app.route('/audit_logs')
@login_required
@admin_required
def audit_logs():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
    return render_template("audit_logs.html", logs=logs)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    setting = SystemSetting.query.filter_by(key='company_name').first()
    if request.method == "POST":
        new_name = request.form.get('company_name')
        
        # Handle Logo Upload
        if 'company_logo' in request.files:
            file = request.files['company_logo']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"logo_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                if setting:
                    setting.company_logo = filename

        if new_name:
            if not setting:
                setting = SystemSetting(key='company_name', value=new_name)
                db.session.add(setting)
            else:
                setting.value = new_name
            db.session.commit()
            log_action("Updated Settings", "System", None, f"Company Name changed to: {new_name}")
            flash("Settings updated successfully!")
            return redirect('/')
    
    return render_template("settings.html", setting=setting)

scheduler = BackgroundScheduler()
scheduler.add_job(func=check_and_send_alerts, trigger="interval", hours=24)
scheduler.start()
# -------------------------------
# INITIALIZE ADMIN USER
# -------------------------------
def create_admin():
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            default_pw = os.environ.get("DEFAULT_ADMIN_PASSWORD", "changeme123")
            hashed_pw = generate_password_hash(default_pw)
            new_admin = User(username='admin', password=hashed_pw, role='Admin')
            db.session.add(new_admin)
            db.session.commit()
            print("Default Admin user created. Set DEFAULT_ADMIN_PASSWORD env var to control the password.")

with app.app_context():
    db.create_all()

create_admin()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
