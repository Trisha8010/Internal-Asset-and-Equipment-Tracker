from extensions import db
from datetime import datetime
from flask_login import UserMixin

# ==============================
# USER MODEL (RBAC)
# ==============================
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), default="Employee") # Admin, Manager, Employee

# ==============================
# VENDOR MODEL
# ==============================
class Vendor(db.Model):
    __tablename__ = "vendors"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact_details = db.Column(db.String(200))
    assets = db.relationship("Asset", back_populates="vendor")

# ==============================
# EMPLOYEE MODEL
# ==============================
class Employee(db.Model):
    __tablename__ = "employees"
    id = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    assignments = db.relationship("AssetAssignment", back_populates="employee", cascade="all, delete-orphan")
    requests = db.relationship("AssetRequest", back_populates="employee")

# ==============================
# ASSET MODEL (Enhanced)
# ==============================
class Asset(db.Model):
    __tablename__ = "assets"
    id = db.Column(db.Integer, primary_key=True)
    asset_name = db.Column(db.String(100), nullable=False)
    asset_type = db.Column(db.String(100), nullable=False) # Hardware, Software
    category = db.Column(db.String(100)) # Sub-category
    serial_number = db.Column(db.String(100), unique=True, nullable=True)
    purchase_date = db.Column(db.Date, nullable=False)
    purchase_cost = db.Column(db.Float, default=0.0)
    depreciation_rate = db.Column(db.Float, default=0.0) # Annual %
    warranty_expiry = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(100))
    status = db.Column(db.String(50), default="Available") # Available, Assigned, Maintenance, Disposed
    image_filename = db.Column(db.String(255))
    
    # Financial/Lifecycle
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"))
    disposal_date = db.Column(db.Date)
    disposal_method = db.Column(db.String(100))
    is_disposed = db.Column(db.Boolean, default=False)

    vendor = db.relationship("Vendor", back_populates="assets")
    assignments = db.relationship("AssetAssignment", back_populates="asset", cascade="all, delete-orphan")
    maintenances = db.relationship("Maintenance", back_populates="asset", cascade="all, delete-orphan")

# ==============================
# ASSET ASSIGNMENT MODEL
# ==============================
class AssetAssignment(db.Model):
    __tablename__ = "asset_assignments"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id"), nullable=False)
    assigned_date = db.Column(db.Date, nullable=False)
    return_date = db.Column(db.Date)

    employee = db.relationship("Employee", back_populates="assignments")
    asset = db.relationship("Asset", back_populates="assignments")

# ==============================
# MAINTENANCE MODEL
# ==============================
class Maintenance(db.Model):
    __tablename__ = "maintenance"
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    maintenance_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    cost = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(50), default="In Progress")

    asset = db.relationship("Asset", back_populates="maintenances")

# ==============================
# ASSET REQUEST MODEL
# ==============================
class AssetRequest(db.Model):
    __tablename__ = "asset_requests"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    asset_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    request_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default="Pending") # Pending, Approved, Rejected

    employee = db.relationship("Employee", back_populates="requests")

# ==============================
# AUDIT LOG MODEL
# ==============================
class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(50)) # Asset, Employee, etc.
    target_id = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.String(500))

# ==============================
# SYSTEM SETTINGS MODEL
# ==============================
class SystemSetting(db.Model):
    __tablename__ = "system_settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(200))
    company_logo = db.Column(db.String(255)) # Store filename of company logo
