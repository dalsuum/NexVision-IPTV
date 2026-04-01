"""
NexVision VOD Storage Management Module

Integrates storage_backends.py with Flask admin dashboard.
Provides endpoints for:
- Storage backend selection/configuration
- Health checks and monitoring
- Manual backend switching
- Storage statistics
- Admin UI components
"""

import os
import json
import logging
from typing import Dict, Tuple, Optional
from pathlib import Path
from datetime import datetime
from functools import wraps
from flask import request

logger = logging.getLogger('nexvision-storage')

# ═════════════════════════════════════════════════════════════════════════════
# STORAGE CONFIGURATION & STATE MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

class StorageConfig:
    """Centralized storage configuration management"""
    
    CONFIG_FILE = Path(os.environ.get('VOD_DATA_DIR', './vod_data')) / '.storage_config.json'
    DEFAULT_BACKEND = 'local'
    
    # Supported backends
    BACKENDS = {
        'local': {
            'name': 'Local Filesystem',
            'icon': '💾',
            'description': 'Local disk storage (dev/small deployments)',
            'max_users': 100,
            'cost': '$0/month',
            'latency': '<1ms',
            'requires_config': False
        },
        'nas': {
            'name': 'NAS (Network)',
            'icon': '🔒',
            'description': 'Network Attached Storage (RAID-6 protected)',
            'max_users': 500,
            'cost': '$200/month',
            'latency': '<5ms',
            'requires_config': True,
            'config_keys': ['NAS_MOUNT'],
            'optional_keys': []
        },
        's3': {
            'name': 'AWS S3 + CloudFront',
            'icon': '☁️',
            'description': 'Amazon S3 with CloudFront CDN',
            'max_users': '100k+',
            'cost': '$2,500/month (10TB)',
            'latency': '100ms',
            'requires_config': True,
            'config_keys': ['AWS_REGION', 'AWS_ACCESS_KEY', 'AWS_SECRET_KEY', 'S3_BUCKET_HLS', 'CLOUDFRONT_URL'],
            'optional_keys': ['S3_BUCKET_UPLOADS']
        },
        'azure': {
            'name': 'Azure Blob Storage',
            'icon': '☁️',
            'description': 'Microsoft Azure Blob Storage + CDN',
            'max_users': '100k+',
            'cost': '$1,200/month (10TB)',
            'latency': '100ms',
            'requires_config': True,
            'config_keys': ['AZURE_STORAGE_ACCOUNT', 'AZURE_STORAGE_KEY', 'AZURE_CDN_URL'],
            'optional_keys': []
        },
        'gcs': {
            'name': 'Google Cloud Storage',
            'icon': '☁️',
            'description': 'Google Cloud Storage with CDN',
            'max_users': '100k+',
            'cost': '$900/month (10TB)',
            'latency': '80ms',
            'requires_config': True,
            'config_keys': ['GCP_PROJECT_ID', 'GCS_BUCKET'],
            'optional_keys': []
        }
    }
    
    @classmethod
    def load(cls) -> Dict:
        """Load current storage configuration"""
        if cls.CONFIG_FILE.exists():
            try:
                with open(cls.CONFIG_FILE) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load storage config: {e}")
        
        # Return default
        return {
            'backend': cls.DEFAULT_BACKEND,
            'changed_at': datetime.now().isoformat(),
            'backend_info': cls.BACKENDS.get(cls.DEFAULT_BACKEND, {})
        }
    
    @classmethod
    def save(cls, config: Dict) -> bool:
        """Save storage configuration"""
        try:
            cls.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            config['changed_at'] = datetime.now().isoformat()
            config['backend_info'] = cls.BACKENDS.get(config.get('backend', cls.DEFAULT_BACKEND), {})
            
            with open(cls.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.info(f"Storage config saved: {config.get('backend')}")
            return True
        except Exception as e:
            logger.error(f"Failed to save storage config: {e}")
            return False
    
    @classmethod
    def validate_backend_config(cls, backend: str, env_vars: Dict = None) -> Tuple[bool, str]:
        """Validate backend configuration"""
        if backend not in cls.BACKENDS:
            return False, f"Unknown backend: {backend}"
        
        backend_info = cls.BACKENDS[backend]
        
        if not backend_info.get('requires_config'):
            return True, "No configuration required"
        
        # Check required keys
        env_vars = env_vars or os.environ
        required_keys = backend_info.get('config_keys', [])
        missing = [k for k in required_keys if not env_vars.get(k)]
        
        if missing:
            return False, f"Missing required environment variables: {', '.join(missing)}"
        
        return True, "Configuration valid"


# ═════════════════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS (integrate into Flask app.py)
# ═════════════════════════════════════════════════════════════════════════════

def create_storage_admin_routes(app, require_admin=None):
    """
    Create admin API routes for storage management.
    
    Usage in app.py:
        from vod_storage_admin import create_storage_admin_routes
        create_storage_admin_routes(app, require_admin=require_admin_decorator)
    """
    
    from storage_backends import get_storage_backend
    
    def admin_required(f):
        """Wrapper for admin-only routes (if provided)"""
        if require_admin:
            return require_admin(f)
        return f
    
    # ─── Storage Info & Stats ──────────────────────────────────────────────────
    
    @app.route('/api/admin/storage/info', methods=['GET'])
    @admin_required
    def storage_info():
        """GET /api/admin/storage/info - Get current storage configuration"""
        try:
            config = StorageConfig.load()
            storage = get_storage_backend()
            health = storage.check_health()
            stats = storage.get_storage_stats()
            
            return {
                'success': True,
                'backend': type(storage).__name__,
                'config': config,
                'health': health,
                'stats': stats,
                'timestamp': datetime.now().isoformat()
            }, 200
        except Exception as e:
            logger.exception("Error getting storage info")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }, 500
    
    # ─── List Available Backends ───────────────────────────────────────────────
    
    @app.route('/api/admin/storage/backends', methods=['GET'])
    @admin_required
    def list_storage_backends():
        """GET /api/admin/storage/backends - List all available backends"""
        try:
            current_config = StorageConfig.load()
            current_backend = current_config.get('backend', StorageConfig.DEFAULT_BACKEND)
            
            backends = []
            for backend_key, info in StorageConfig.BACKENDS.items():
                is_current = backend_key == current_backend
                
                backends.append({
                    'id': backend_key,
                    'name': info['name'],
                    'icon': info['icon'],
                    'description': info['description'],
                    'max_users': info['max_users'],
                    'cost': info['cost'],
                    'latency': info['latency'],
                    'requires_config': info['requires_config'],
                    'config_keys': info.get('config_keys', []),
                    'optional_keys': info.get('optional_keys', []),
                    'is_current': is_current,
                    'configured': all(os.getenv(k) for k in info.get('config_keys', [])) if info.get('requires_config') else True
                })
            
            return {
                'success': True,
                'backends': backends,
                'current': current_backend
            }, 200
        except Exception as e:
            logger.exception("Error listing backends")
            return {
                'success': False,
                'error': str(e)
            }, 500
    
    # ─── Switch Storage Backend ────────────────────────────────────────────────
    
    @app.route('/api/admin/storage/switch', methods=['POST'])
    @admin_required
    def switch_storage_backend():
        """
        POST /api/admin/storage/switch
        Body: {"backend": "s3", "options": {...}}
        
        Switch to a different storage backend
        """
        try:
            data = request.json or {}
            new_backend = data.get('backend', '').strip()
            
            if new_backend not in StorageConfig.BACKENDS:
                return {
                    'success': False,
                    'error': f"Unknown backend: {new_backend}"
                }, 400
            
            # Validate configuration
            valid, msg = StorageConfig.validate_backend_config(new_backend)
            if not valid:
                return {
                    'success': False,
                    'error': msg
                }, 400
            
            # Save configuration
            new_config = {
                'backend': new_backend,
                'previous_backend': StorageConfig.load().get('backend'),
                'switched_by': request.remote_addr,
                'reason': data.get('reason', 'Manual admin switch')
            }
            
            if StorageConfig.save(new_config):
                logger.info(f"Storage backend switched to: {new_backend}")
                
                return {
                    'success': True,
                    'message': f"Switched to {StorageConfig.BACKENDS[new_backend]['name']}",
                    'backend': new_backend,
                    'config': StorageConfig.load(),
                    'warning': 'Application restart may be required for changes to take effect'
                }, 200
            else:
                return {
                    'success': False,
                    'error': 'Failed to save configuration'
                }, 500
        
        except Exception as e:
            logger.exception("Error switching storage backend")
            return {
                'success': False,
                'error': str(e)
            }, 500
    
    # ─── Test Storage Connectivity ─────────────────────────────────────────────
    
    @app.route('/api/admin/storage/test', methods=['POST'])
    @admin_required
    def test_storage_backend():
        """
        POST /api/admin/storage/test
        Body: {"backend": "s3"}  (optional, uses current if not specified)
        
        Test storage backend connectivity
        """
        backend_name = StorageConfig.load().get('backend', StorageConfig.DEFAULT_BACKEND)
        try:
            import tempfile
            
            data = request.json or {}
            backend_name = data.get('backend', '').strip() or backend_name
            
            if backend_name not in StorageConfig.BACKENDS:
                return {
                    'success': False,
                    'error': f"Unknown backend: {backend_name}"
                }, 400
            
            # Create test file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tmp:
                tmp.write(b"NexVision storage test")
                tmp_path = tmp.name
            
            try:
                # Get storage backend
                storage = get_storage_backend()
                
                # Test write
                result = storage.save_upload(999999, tmp_path)
                
                # Clean up
                os.unlink(tmp_path)
                
                health = storage.check_health()
                
                return {
                    'success': True,
                    'message': 'Storage backend is accessible',
                    'backend': type(storage).__name__,
                    'health': health
                }, 200
            
            except Exception as e:
                os.unlink(tmp_path)
                raise
        
        except Exception as e:
            logger.exception("Error testing storage backend")
            return {
                'success': False,
                'error': str(e),
                'backend': backend_name
            }, 500
    
    # ─── Get Environment Variables Status ──────────────────────────────────────
    
    @app.route('/api/admin/storage/config-status', methods=['GET'])
    @admin_required
    def get_config_status():
        """GET /api/admin/storage/config-status - Get environment variable status"""
        try:
            current_backend = StorageConfig.load().get('backend', StorageConfig.DEFAULT_BACKEND)
            backend_info = StorageConfig.BACKENDS[current_backend]
            
            config_status = {
                'backend': current_backend,
                'backend_name': backend_info['name'],
                'required_vars': {}
            }
            
            # Check required variables
            if backend_info.get('requires_config'):
                required_keys = backend_info.get('config_keys', [])
                for key in required_keys:
                    value = os.getenv(key, '')
                    # Mask sensitive values
                    masked = '*' * len(value) if value else ''
                    config_status['required_vars'][key] = {
                        'set': bool(value),
                        'masked_value': masked,
                        'needed': not bool(value)
                    }
            
            return {
                'success': True,
                'config': config_status
            }, 200
        
        except Exception as e:
            logger.exception("Error getting config status")
            return {
                'success': False,
                'error': str(e)
            }, 500
    
    # ─── Storage Health Check (for monitoring) ─────────────────────────────────
    
    @app.route('/api/admin/storage/health', methods=['GET'])
    @admin_required
    def storage_health_check():
        """GET /api/admin/storage/health - Detailed storage health check"""
        try:
            storage = get_storage_backend()
            health = storage.check_health()
            stats = storage.get_storage_stats()
            
            # Determine overall health status
            status = 'healthy' if health.get('status') == 'ok' else 'unhealthy'
            
            return {
                'success': True,
                'status': status,
                'backend': type(storage).__name__,
                'health': health,
                'stats': stats,
                'timestamp': datetime.now().isoformat()
            }, 200
        
        except Exception as e:
            logger.exception("Error checking storage health")
            return {
                'success': False,
                'error': str(e),
                'status': 'error'
            }, 500
    
    # ─── Get Storage Monitoring Dashboard Data ─────────────────────────────────
    
    @app.route('/api/admin/storage/dashboard', methods=['GET'])
    @admin_required
    def storage_dashboard_data():
        """GET /api/admin/storage/dashboard - Get data for monitoring dashboard"""
        try:
            storage = get_storage_backend()
            config = StorageConfig.load()
            health = storage.check_health()
            stats = storage.get_storage_stats()
            
            backend_info = StorageConfig.BACKENDS.get(config['backend'], {})
            
            dashboard_data = {
                'current_backend': config['backend'],
                'backend_name': backend_info.get('name'),
                'backend_icon': backend_info.get('icon'),
                'health_status': health.get('status', 'unknown'),
                'max_concurrent_users': backend_info.get('max_users'),
                'estimated_cost': backend_info.get('cost'),
                'latency': backend_info.get('latency'),
                'storage_stats': stats,
                'last_check': datetime.now().isoformat()
            }
            
            return {
                'success': True,
                'data': dashboard_data
            }, 200
        
        except Exception as e:
            logger.exception("Error getting dashboard data")
            return {
                'success': False,
                'error': str(e)
            }, 500
    
    logger.info("Storage admin routes initialized")
    return app


# ═════════════════════════════════════════════════════════════════════════════
# ADMIN DASHBOARD HTML
# ═════════════════════════════════════════════════════════════════════════════

STORAGE_ADMIN_HTML = """
<div class="admin-section storage-management">
    <h2>📦 Storage Management</h2>
    
    <div class="storage-container">
        <!-- Current Storage Status -->
        <div class="storage-panel current-storage">
            <h3>Current Storage Backend</h3>
            <div id="current-storage-info" class="storage-info">
                <div class="loading">Loading...</div>
            </div>
            <button onclick="testStorageBackend()" class="btn btn-primary">
                🧪 Test Connectivity
            </button>
        </div>
        
        <!-- Storage Health -->
        <div class="storage-panel health-panel">
            <h3>Storage Health</h3>
            <div id="storage-health" class="health-info">
                <div class="loading">Loading...</div>
            </div>
            <button onclick="refreshStorageStatus()" class="btn btn-secondary">
                🔄 Refresh
            </button>
        </div>
        
        <!-- Storage Statistics -->
        <div class="storage-panel stats-panel">
            <h3>Storage Usage</h3>
            <div id="storage-stats" class="stats-info">
                <div class="loading">Loading...</div>
            </div>
        </div>
    </div>
    
    <!-- Switch Backend Section -->
    <div class="backend-switch-section">
        <h3>Switch Storage Backend</h3>
        <div id="backend-list" class="backend-options">
            <div class="loading">Loading available backends...</div>
        </div>
    </div>
    
    <!-- Configuration Status -->
    <div class="config-status-section">
        <h3>Configuration Status</h3>
        <div id="config-status" class="config-info">
            <div class="loading">Loading...</div>
        </div>
    </div>
    
    <style>
        .storage-management {
            background: var(--bg3, #131320);
            color: var(--white, #f0f0f8);
            border: 1px solid var(--border, rgba(255,255,255,.08));
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }
        
        .storage-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }
        
        .storage-panel {
            background: var(--bg2, #0d0d14);
            padding: 15px;
            border-radius: 6px;
            border: 1px solid var(--border, rgba(255,255,255,.08));
            box-shadow: none;
        }
        
        .storage-panel h3 {
            margin-top: 0;
            color: var(--white, #f0f0f8);
            font-size: 18px;
        }
        
        .storage-info, .health-info, .stats-info, .config-info {
            background: var(--bg4, #1a1a2e);
            color: var(--dimmed, rgba(240,240,248,.7));
            border: 1px solid var(--border, rgba(255,255,255,.08));
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
            font-size: 14px;
            line-height: 1.6;
        }
        
        .loading {
            color: var(--muted, rgba(240,240,248,.45));
            font-style: italic;
        }
        
        .healthy { color: #28a745; font-weight: bold; }
        .warning { color: #ffc107; font-weight: bold; }
        .error { color: #dc3545; font-weight: bold; }
        
        .backend-switch-section, .config-status-section {
            background: var(--bg2, #0d0d14);
            padding: 20px;
            border-radius: 6px;
            border: 1px solid var(--border, rgba(255,255,255,.08));
            margin: 20px 0;
        }
        
        .backend-options {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin: 15px 0;
        }
        
        .backend-card {
            border: 2px solid var(--border2, rgba(255,255,255,.14));
            padding: 15px;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.3s;
            background: var(--bg3, #131320);
        }
        
        .backend-card:hover {
            border-color: var(--gold, #c9a84c);
            background: var(--gold3, rgba(201,168,76,.15));
        }
        
        .backend-card.current {
            border-color: #28a745;
            background: rgba(40,167,69,0.16);
        }
        
        .backend-card.disabled {
            opacity: 0.6;
            cursor: not-allowed;
            background: var(--bg4, #1a1a2e);
        }
        
        .backend-card h4 {
            margin: 0 0 8px 0;
            color: var(--white, #f0f0f8);
        }
        
        .backend-icon {
            font-size: 24px;
            margin-right: 8px;
        }
        
        .backend-details {
            font-size: 12px;
            color: var(--muted, rgba(240,240,248,.45));
            margin: 10px 0;
        }
        
        .backend-actions {
            margin-top: 10px;
        }
        
        .btn {
            padding: 8px 15px;
            margin: 5px 5px 5px 0;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
        }
        
        .btn-primary {
            background: var(--gold, #c9a84c);
            color: #000;
        }
        
        .btn-primary:hover {
            background: var(--gold2, #e8c56a);
        }
        
        .btn-secondary {
            background: #6c757d;
            color: white;
        }
        
        .btn-secondary:hover {
            background: #545b62;
        }
        
        .btn-success {
            background: #28a745;
            color: white;
        }
        
        .btn-success:hover {
            background: #218838;
        }
        
        .btn-warning {
            background: #ffc107;
            color: white;
        }
        
        .btn-warning:hover {
            background: #e0a800;
        }
        
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: bold;
            margin: 2px;
        }
        
        .badge-success {
            background: #d4edda;
            color: #155724;
        }
        
        .badge-warning {
            background: #fff3cd;
            color: #856404;
        }
        
        .badge-danger {
            background: #f8d7da;
            color: #721c24;
        }
        
        .badge-info {
            background: #d1ecf1;
            color: #0c5460;
        }
    </style>
    
    <script>
        // Initialize storage management UI
        document.addEventListener('DOMContentLoaded', function() {
            loadStorageInfo();
            loadStorageBackends();
            loadConfigStatus();
            
            // Refresh every 30 seconds
            setInterval(function() {
                loadStorageInfo();
                refreshStorageStatus();
            }, 30000);
        });
        
        async function loadStorageInfo() {
            try {
                const response = await fetch('/api/admin/storage/info');
                const data = await response.json();
                
                if (data.success) {
                    const health = data.health;
                    const stats = data.stats;
                    const backend = data.backend;
                    
                    let html = `
                        <p><strong>Backend:</strong> ${backend}</p>
                        <p><strong>Status:</strong> <span class="${health.status === 'ok' ? 'healthy' : 'error'}">${health.status}</span></p>
                    `;
                    
                    if (health.error) {
                        html += `<p><strong>Error:</strong> ${health.error}</p>`;
                    }
                    
                    if (stats && Object.keys(stats).length > 0) {
                        html += '<p><strong>Stats:</strong></p><ul>';
                        for (const [key, value] of Object.entries(stats)) {
                            html += `<li>${key}: ${value}</li>`;
                        }
                        html += '</ul>';
                    }
                    
                    document.getElementById('current-storage-info').innerHTML = html;
                } else {
                    document.getElementById('current-storage-info').innerHTML = `<p class="error">${data.error}</p>`;
                }
            } catch (error) {
                document.getElementById('current-storage-info').innerHTML = `<p class="error">Error: ${error.message}</p>`;
            }
        }
        
        window.storageBackends = [];

        async function loadStorageBackends() {
            try {
                const response = await fetch('/api/admin/storage/backends');
                const data = await response.json();
                
                if (data.success) {
                    window.storageBackends = data.backends;
                    let html = '';
                    for (const backend of data.backends) {
                        const isCurrent = backend.is_current;
                        const isConfigured = backend.configured;
                        const cardClass = isCurrent ? 'current' : (isConfigured ? '' : 'disabled');
                        
                        html += `
                            <div class="backend-card ${cardClass}" data-backend-id="${backend.id}">
                                <h4>
                                    <span class="backend-icon">${backend.icon}</span>
                                    ${backend.name}
                                    ${isCurrent ? '<span class="badge badge-success">CURRENT</span>' : ''}
                                    ${!isConfigured ? '<span class="badge badge-warning">NOT CONFIGURED</span>' : ''}
                                </h4>
                                <p>${backend.description}</p>
                                <div class="backend-details">
                                    <p><strong>Users:</strong> ${backend.max_users}</p>
                                    <p><strong>Cost:</strong> ${backend.cost}</p>
                                    <p><strong>Latency:</strong> ${backend.latency}</p>
                                </div>
                                <div class="backend-actions">
                                    <button class="btn btn-secondary" onclick="focusBackend('${backend.id}')">
                                        View Setup
                                    </button>
                                    ${!isCurrent && isConfigured ? `
                                        <button class="btn btn-warning" onclick="switchBackend('${backend.id}')">
                                            Switch to ${backend.name}
                                        </button>
                                    ` : ''}
                                </div>
                            </div>
                        `;
                    }
                    document.getElementById('backend-list').innerHTML = html;
                } else {
                    document.getElementById('backend-list').innerHTML = `<p class="error">${data.error}</p>`;
                }
            } catch (error) {
                document.getElementById('backend-list').innerHTML = `<p class="error">Error: ${error.message}</p>`;
            }
        }
        
        async function loadConfigStatus() {
            try {
                const response = await fetch('/api/admin/storage/config-status');
                const data = await response.json();
                
                if (data.success) {
                    const config = data.config;
                    let html = `
                        <p><strong>Backend:</strong> ${config.backend_name}</p>
                        <p><strong>Required Environment Variables:</strong></p>
                        <ul>
                    `;
                    
                    if (Object.keys(config.required_vars).length === 0) {
                        html += '<li>No additional configuration required</li>';
                    } else {
                        for (const [key, status] of Object.entries(config.required_vars)) {
                            const badgeClass = status.set ? 'badge-success' : 'badge-danger';
                            const badgeText = status.set ? '✓ SET' : '✗ NOT SET';
                            html += `
                                <li>
                                    <code>${key}</code>
                                    <span class="badge ${badgeClass}">${badgeText}</span>
                                </li>
                            `;
                        }
                    }
                    
                    html += '</ul>';
                    document.getElementById('config-status').innerHTML = html;
                } else {
                    document.getElementById('config-status').innerHTML = `<p class="error">${data.error}</p>`;
                }
            } catch (error) {
                document.getElementById('config-status').innerHTML = `<p class="error">Error: ${error.message}</p>`;
            }
        }
        
        async function refreshStorageStatus() {
            try {
                const response = await fetch('/api/admin/storage/health');
                const data = await response.json();
                
                if (data.success) {
                    const statusClass = data.status === 'healthy' ? 'healthy' : (data.status === 'error' ? 'error' : 'warning');
                    let html = `
                        <p><strong>Status:</strong> <span class="${statusClass}">${data.status.toUpperCase()}</span></p>
                        <p><strong>Backend:</strong> ${data.backend}</p>
                        <p><strong>Last Check:</strong> ${new Date(data.timestamp).toLocaleString()}</p>
                    `;
                    
                    if (data.health.details) {
                        html += `<p><strong>Details:</strong> ${data.health.details}</p>`;
                    }
                    
                    document.getElementById('storage-health').innerHTML = html;
                } else {
                    document.getElementById('storage-health').innerHTML = `<p class="error">${data.error}</p>`;
                }
            } catch (error) {
                document.getElementById('storage-health').innerHTML = `<p class="error">Error: ${error.message}</p>`;
            }
        }
        
        async function testStorageBackend() {
            const button = event.target;
            button.disabled = true;
            button.innerText = '🧪 Testing...';
            
            try {
                const response = await fetch('/api/admin/storage/test', { method: 'POST' });
                const data = await response.json();
                
                if (data.success) {
                    alert('✓ Storage backend is accessible!');
                } else {
                    alert('✗ Error: ' + data.error);
                }
            } catch (error) {
                alert('✗ Test failed: ' + error.message);
            } finally {
                button.disabled = false;
                button.innerText = '🧪 Test Connectivity';
            }
        }
        
        async function switchBackend(backendId) {
            const reason = prompt(`Switch to ${backendId}?\\n\\nEnter reason (optional):`);
            if (reason === null) return; // User cancelled
            
            try {
                const response = await fetch('/api/admin/storage/switch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        backend: backendId,
                        reason: reason || 'Manual switch'
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    alert('✓ Switched to ' + data.backend + '\\n\\n' + data.warning);
                    location.reload();
                } else {
                    alert('✗ Error: ' + data.error);
                }
            } catch (error) {
                alert('✗ Switch failed: ' + error.message);
            }
        }

        function focusBackend(backendId) {
            const backends = window.storageBackends || [];
            const backend = backends.find(item => item.id === backendId);
            const cards = document.querySelectorAll('.backend-card');

            cards.forEach(card => {
                card.style.boxShadow = '';
                card.style.borderColor = '';
            });

            const card = document.querySelector(`.backend-card[data-backend-id="${backendId}"]`);
            if (card) {
                card.style.borderColor = '#0066cc';
                card.style.boxShadow = '0 0 0 4px rgba(0, 102, 204, 0.15)';
                card.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }

            if (!backend) {
                return;
            }

            const required = backend.config_keys || [];
            const optional = backend.optional_keys || [];
            const lines = [
                `${backend.icon} ${backend.name}`,
                '',
                required.length ? `Required: ${required.join(', ')}` : 'Required: No additional variables',
                optional.length ? `Optional: ${optional.join(', ')}` : 'Optional: None',
                `Configured: ${backend.configured ? 'Yes' : 'No'}`
            ];

            alert(lines.join('\\n'));
        }
    </script>
</div>
"""

if __name__ == '__main__':
    # Print HTML for admin dashboard
    print(STORAGE_ADMIN_HTML)
