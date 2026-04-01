#!/usr/bin/env python3
"""
NexVision Multi-Storage Integration Setup
Automatically integrates storage backends into app.py
"""

import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime

def setup_multi_storage(app_path='/opt/nexvision/app.py'):
    """
    Setup multi-storage integration in app.py
    """
    
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  NexVision Multi-Storage Integration Setup                  ║")
    print("╚══════════════════════════════════════════════════════════════╝\n")
    
    # Check if files exist
    print("1. Checking required files...")
    
    required_files = [
        'storage_backends.py',
        'vod_storage_admin.py',
    ]
    
    for f in required_files:
        path = Path(f)
        if path.exists():
            print(f"   ✓ {f}")
        else:
            print(f"   ✗ {f} NOT FOUND")
            return False
    
    if not Path(app_path).exists():
        print(f"   ✗ {app_path} NOT FOUND")
        return False
    else:
        print(f"   ✓ {app_path}")
    
    # Backup app.py
    print("\n2. Creating backup...")
    backup_path = f"{app_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        shutil.copy2(app_path, backup_path)
        print(f"   ✓ Backup created: {backup_path}")
    except Exception as e:
        print(f"   ✗ Backup failed: {e}")
        return False
    
    # Read app.py
    print("\n3. Reading app.py...")
    try:
        with open(app_path, 'r') as f:
            app_content = f.read()
        print("   ✓ Read app.py")
    except Exception as e:
        print(f"   ✗ Failed to read app.py: {e}")
        return False
    
    # Check if already integrated
    if 'from storage_backends import' in app_content:
        print("   ! Storage backends already imported (skipping)")
        return True
    
    # Add imports after existing Flask imports
    print("\n4. Adding imports...")
    try:
        # Find insertion point (after from flask import block)
        import_marker = "from flask_cors import CORS"
        
        if import_marker not in app_content:
            print("   ! Could not find CORS import marker")
            print("   ! Adding imports at top of file")
            import_section = """# ─── Multi-Storage Support ────────────────────────────────────────────────────
from storage_backends import get_storage_backend, StorageBackend
from vod_storage_admin import create_storage_admin_routes, STORAGE_ADMIN_HTML, StorageConfig\n"""
            app_content = app_content.replace(
                "from flask_cors import CORS",
                "from flask_cors import CORS\n\n" + import_section
            )
        else:
            app_content = app_content.replace(
                "from flask_cors import CORS",
                """from flask_cors import CORS

# ─── Multi-Storage Support ────────────────────────────────────────────────────
from storage_backends import get_storage_backend, StorageBackend
from vod_storage_admin import create_storage_admin_routes, STORAGE_ADMIN_HTML, StorageConfig"""
            )
        
        print("   ✓ Imports added")
    except Exception as e:
        print(f"   ✗ Failed to add imports: {e}")
        shutil.copy2(backup_path, app_path)  # Restore backup
        return False
    
    # Add storage initialization
    print("\n5. Adding storage initialization...")
    try:
        init_marker = "app = Flask(__name__"
        if init_marker in app_content:
            init_code = """

# ─── Initialize Multi-Storage Backend ──────────────────────────────────────
try:
    vod_storage: StorageBackend = get_storage_backend()
    logger.info(f"VOD Storage initialized: {type(vod_storage).__name__}")
except Exception as e:
    logger.warning(f"Failed to initialize VOD storage: {e}")
    vod_storage = None"""
            
            # Find app creation line and add init after CORS
            cors_marker = "CORS(app)"
            if cors_marker in app_content:
                app_content = app_content.replace(
                    cors_marker,
                    cors_marker + init_code
                )
                print("   ✓ Storage initialization added")
        else:
            print("   ! Could not find app initialization marker")
    except Exception as e:
        print(f"   ✗ Failed to add initialization: {e}")
        shutil.copy2(backup_path, app_path)
        return False
    
    # Add admin routes initialization (find good insertion point)
    print("\n6. Adding admin routes...")
    try:
        # Add at the end of routes, before if __name__
        if_main_marker = "if __name__ == '__main__':"
        
        admin_routes_code = """
# ═════════════════════════════════════════════════════════════════════════════
# STORAGE MANAGEMENT ADMIN ROUTES
# ═════════════════════════════════════════════════════════════════════════════

# Initialize storage admin routes  
try:
    create_storage_admin_routes(app, require_admin=admin_required if 'admin_required' in globals() else None)
    logger.info("Storage admin routes initialized")
except Exception as e:
    logger.warning(f"Failed to initialize storage admin routes: {e}")


@app.route('/admin/storage', methods=['GET'])
def admin_storage_dashboard():
    \"\"\"Serve storage management dashboard\"\"\"
    try:
        # Check admin access (adjust to match your auth)
        if 'admin_required' in globals():
            return admin_required(lambda: STORAGE_ADMIN_HTML)()
        
        admin_html = f\"\"\"
        <!DOCTYPE html>
        <html>
        <head>
            <title>Storage Management - NexVision Admin</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
                .header {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .header h1 {{ margin: 0; color: #333; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📦 VOD Storage Management</h1>
                <p>Configure and monitor multi-backend storage for your VOD system</p>
            </div>
            {STORAGE_ADMIN_HTML}
        </body>
        </html>
        \"\"\"
        return admin_html
    except Exception as e:
        logger.exception("Error serving storage dashboard")
        return f"<h1>Error</h1><p>{e}</p>", 500

"""
        
        if if_main_marker in app_content:
            app_content = app_content.replace(
                if_main_marker,
                admin_routes_code + "\n" + if_main_marker
            )
            print("   ✓ Admin routes added")
        else:
            # Just append before end of file
            app_content = app_content.rstrip() + "\n\n" + admin_routes_code
            print("   ✓ Admin routes appended")
    except Exception as e:
        print(f"   ✗ Failed to add admin routes: {e}")
        shutil.copy2(backup_path, app_path)
        return False
    
    # Write updated app.py
    print("\n7. Writing updated app.py...")
    try:
        with open(app_path, 'w') as f:
            f.write(app_content)
        print("   ✓ Updated app.py")
    except Exception as e:
        print(f"   ✗ Failed to write app.py: {e}")
        shutil.copy2(backup_path, app_path)
        return False
    
    # Create .env template
    print("\n8. Creating .env template...")
    try:
        env_additions = """
# ═════════════════════════════════════════════════════════════════════════════
# VOD STORAGE BACKENDS (NexVision v9.0+)
# ═════════════════════════════════════════════════════════════════════════════

# Options: local, nas, s3, azure, gcs
STORAGE_BACKEND=local

# ─── LOCAL STORAGE (default, no config needed) ─────────────────────────────
# VOD_DATA_DIR=./vod_data

# ─── NAS (Network Attached Storage) ────────────────────────────────────────
# STORAGE_BACKEND=nas
# NAS_MOUNT=/mnt/nas/vod

# ─── AWS S3 + CloudFront ──────────────────────────────────────────────────
# STORAGE_BACKEND=s3
# AWS_REGION=us-east-1
# AWS_ACCESS_KEY=AKIA...
# AWS_SECRET_KEY=...
# S3_BUCKET_UPLOADS=nexvision-uploads
# S3_BUCKET_HLS=nexvision-hls
# CLOUDFRONT_URL=https://d123.cloudfront.net

# ─── AZURE BLOB STORAGE ───────────────────────────────────────────────────
# STORAGE_BACKEND=azure
# AZURE_STORAGE_ACCOUNT=mystorageaccount
# AZURE_STORAGE_KEY=...
# AZURE_CDN_URL=https://mycdn.azureedge.net

# ─── GOOGLE CLOUD STORAGE ────────────────────────────────────────────────
# STORAGE_BACKEND=gcs
# GCP_PROJECT_ID=my-project
# GCS_BUCKET=nexvision-vod
"""
        
        env_path = Path('.env')
        if env_path.exists():
            with open('.env', 'a') as f:
                f.write(env_additions)
            print("   ✓ Added to .env")
        else:
            with open('.env', 'w') as f:
                f.write("# NexVision Configuration\n" + env_additions)
            print("   ✓ Created .env")
    except Exception as e:
        print(f"   ! Warning: Could not update .env: {e}")
    
    print("\n" + "="*60)
    print("✓ Integration Complete!")
    print("="*60 + "\n")
    
    print("Next steps:")
    print("  1. Review changes in app.py")
    print("  2. Configure .env with desired storage backend")
    print("  3. Install backend dependencies:")
    print("     pip install boto3 azure-storage-blob google-cloud-storage")
    print("  4. Restart the application:")
    print("     sudo systemctl restart nexvision")
    print("  5. Access admin dashboard:")
    print("     http://localhost:5000/admin/storage")
    print("  6. Test storage backend:")
    print("     curl -X POST http://localhost:5000/api/admin/storage/test")
    print("\nDocumentation:")
    print("  • Full guide: docs/VOD-Storage-Architecture.md")
    print("  • Integration: docs/APP-INTEGRATION-CODE.md")
    print("  • Quick ref:  docs/STORAGE-QUICK-REFERENCE.md")
    print("\nBackup location: " + backup_path)
    
    return True


if __name__ == '__main__':
    app_path = sys.argv[1] if len(sys.argv) > 1 else '/opt/nexvision/app.py'
    success = setup_multi_storage(app_path)
    sys.exit(0 if success else 1)
