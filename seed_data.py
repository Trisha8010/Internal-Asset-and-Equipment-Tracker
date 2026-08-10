import os
import sys
from datetime import datetime, date, timedelta
from app import app, db
from models import User, Employee, Asset, Vendor, Maintenance, AssetAssignment
from werkzeug.security import generate_password_hash

def seed_data():
    with app.app_context():
        # Clear existing data
        db.drop_all()
        db.create_all()

        print("Seeding database...")

        # 1. Create Admin & Manager Users
        admin_pw = generate_password_hash('admin123')
        manager_pw = generate_password_hash('manager123')
        
        admin = User(username='admin', password=admin_pw, role='Admin')
        manager = User(username='manager', password=manager_pw, role='Manager')
        db.session.add_all([admin, manager])

        # 2. Create Vendors
        apple = Vendor(name="Apple Enterprise", contact_details="enterprise@apple.com")
        dell = Vendor(name="Dell Technologies", contact_details="support@dell.com")
        microsoft = Vendor(name="Microsoft Cloud", contact_details="azure-support@microsoft.com")
        logitech = Vendor(name="Logitech Business", contact_details="b2b@logitech.com")
        db.session.add_all([apple, dell, microsoft, logitech])
        db.session.commit()

        # 3. Create Employees
        emp1 = Employee(employee_code="EMP001", name="Alice Johnson", department="Engineering", email="alice@company.com")
        emp2 = Employee(employee_code="EMP002", name="Bob Smith", department="Marketing", email="bob@company.com")
        emp3 = Employee(employee_code="EMP003", name="Charlie Davis", department="Human Resources", email="charlie@company.com")
        emp4 = Employee(employee_code="EMP004", name="Diana Prince", department="Product", email="diana@company.com")
        db.session.add_all([emp1, emp2, emp3, emp4])
        db.session.commit()

        # 4. Create Assets
        today = date.today()
        
        assets = [
            Asset(asset_name="MacBook Pro 16", asset_type="Hardware", category="Laptops", serial_number="MBP-2024-001", 
                  purchase_date=today - timedelta(days=200), purchase_cost=2499.00, depreciation_rate=20.0, 
                  warranty_expiry=today + timedelta(days=500), location="London HQ", status="Assigned", vendor_id=apple.id),
            
            Asset(asset_name="Dell Precision 5570", asset_type="Hardware", category="Laptops", serial_number="DELL-9921-X1", 
                  purchase_date=today - timedelta(days=400), purchase_cost=1850.00, depreciation_rate=25.0, 
                  warranty_expiry=today - timedelta(days=10), location="London HQ", status="Available", vendor_id=dell.id),
            
            Asset(asset_name="UltraWide Monitor 34", asset_type="Hardware", category="Peripherals", serial_number="MON-882-LG", 
                  purchase_date=today - timedelta(days=100), purchase_cost=650.00, depreciation_rate=15.0, 
                  warranty_expiry=today + timedelta(days=600), location="London HQ", status="Available", vendor_id=dell.id),
            
            Asset(asset_name="Office 365 License", asset_type="Software", category="Productivity", serial_number="MS-365-50-USER", 
                  purchase_date=today - timedelta(days=30), purchase_cost=1200.00, depreciation_rate=0.0, 
                  warranty_expiry=today + timedelta(days=335), location="Cloud", status="Available", vendor_id=microsoft.id),
            
            Asset(asset_name="Adobe Creative Cloud", asset_type="Software", category="Design", serial_number="ADOBE-CC-TEAM", 
                  purchase_date=today - timedelta(days=15), purchase_cost=900.00, depreciation_rate=0.0, 
                  warranty_expiry=today + timedelta(days=350), location="Cloud", status="Assigned", vendor_id=microsoft.id),
            
            Asset(asset_name="Logitech MX Master 3S", asset_type="Hardware", category="Peripherals", serial_number="LOGI-MX-09", 
                  purchase_date=today - timedelta(days=10), purchase_cost=99.00, depreciation_rate=10.0, 
                  warranty_expiry=today + timedelta(days=720), location="Stock Room", status="Available", vendor_id=logitech.id),

            Asset(asset_name="Server Rack X100", asset_type="Hardware", category="Infrastructure", serial_number="SRV-DARK-01", 
                  purchase_date=today - timedelta(days=600), purchase_cost=5400.00, depreciation_rate=10.0, 
                  warranty_expiry=today + timedelta(days=400), location="Data Center", status="Under Maintenance", vendor_id=dell.id),
        ]
        
        db.session.add_all(assets)
        db.session.commit()

        # 5. Assignments
        assign1 = AssetAssignment(employee_id=emp1.id, asset_id=assets[0].id, assigned_date=today - timedelta(days=150))
        assign2 = AssetAssignment(employee_id=emp4.id, asset_id=assets[4].id, assigned_date=today - timedelta(days=5))
        db.session.add_all([assign1, assign2])

        # 6. Maintenance
        maint1 = Maintenance(asset_id=assets[6].id, maintenance_date=today - timedelta(days=2), cost=250.00, 
                             description="Fan replacement and dust cleaning", status="In Progress")
        maint2 = Maintenance(asset_id=assets[1].id, maintenance_date=today - timedelta(days=100), cost=120.00, 
                             description="Screen hinge repair", status="Completed")
        db.session.add_all([maint1, maint2])
        
        db.session.commit()
        print("Database seeded successfully! Admin: admin/admin123 | Manager: manager/manager123")

if __name__ == "__main__":
    seed_data()
