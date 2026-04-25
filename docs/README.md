# NexVision IPTV Platform - Documentation

**System Version**: v8.10 (April 2026)
**Platform**: Ubuntu 22.04 LTS
**Database**: SQLite (4.9MB+)
**Backend**: Flask (8,895+ lines)

## 📋 Documentation Index

### 🏗️ System Architecture ⭐ **NEW**
- **[NEXVISION-ARCHITECTURE.md](NEXVISION-ARCHITECTURE.md)** - Complete system architecture (IPTV + Clients + VOD)
- **[VOD-SERVER-ARCHITECTURE.md](VOD-SERVER-ARCHITECTURE.md)** - Detailed VOD streaming & multi-storage architecture
- **[nexvision-complete-architecture.drawio](nexvision-complete-architecture.drawio)** - 🎨 **Complete System Diagram** (IPTV + VOD + Clients)
- **[nexvision-system-architecture.drawio](nexvision-system-architecture.drawio)** - 🎨 **IPTV System Diagram**
- **[vod-server-architecture.drawio](vod-server-architecture.drawio)** - 🎨 **VOD Server Diagram**

### 🚀 Deployment & Installation
- **[DEPLOYMENT-GUIDE.md](DEPLOYMENT-GUIDE.md)** - Complete deployment guide with multi-storage support
- **[ORACLE-CLOUD-IMPLEMENTATION.md](ORACLE-CLOUD-IMPLEMENTATION.md)** - Oracle Cloud Infrastructure deployment plan
- **[Server-Hardening-Procedure.md](Server-Hardening-Procedure.md)** - Security hardening checklist

### 🏗️ Multi-Storage System
- **[VOD-Storage-Architecture.md](VOD-Storage-Architecture.md)** - Storage architecture overview
- **[STORAGE-INTEGRATION-GUIDE.md](STORAGE-INTEGRATION-GUIDE.md)** - Integration implementation guide
- **[STORAGE-QUICK-REFERENCE.md](STORAGE-QUICK-REFERENCE.md)** - Quick reference for storage operations
- **[APP-INTEGRATION-CODE.md](APP-INTEGRATION-CODE.md)** - Code integration examples

### 🔧 Operations & Administration
- **[SOB-System-Operations-Book.md](SOB-System-Operations-Book.md)** - Complete operations manual

---

## 🎯 Current System Features

### Core Platform
- ✅ **Live TV Channels**: 11,427+ channels with package-based access control
- ✅ **Video on Demand (VOD)**: Multi-storage backend support (Local, NAS, S3, Azure, GCS)
- ✅ **Radio Streaming**: Web radio stations with metadata
- ✅ **Electronic Program Guide (EPG)**: XMLTV/CSV support with auto-sync
- ✅ **Room Management**: 20+ rooms with token-based registration
- ✅ **Package System**: Content packages with bulk assignment (all 11,427 channels)

### User Interfaces
- ✅ **TV Client**: Full-featured HTML5 client (199KB, mobile responsive)
- ✅ **Admin Panel**: Complete management dashboard
- ✅ **Multi-Storage Admin**: Cloud storage management interface

### Security & Infrastructure
- ✅ **Token Authentication**: Room-based access control
- ✅ **X-Accel-Redirect**: High-performance content delivery via Nginx
- ✅ **Package-Based Access**: Granular content permissions
- ✅ **Admin Authentication**: Role-based access control
- ✅ **Security Hardening**: Documented security procedures

### Recent Enhancements (March 2026)
- ✅ **Package "Select All" Feature**: Bulk assignment of all 11,427+ channels
- ✅ **EPG Integration**: Live EPG data on channel cards and TV sidebar
- ✅ **Channel Pagination**: Improved TV client with pagination support
- ✅ **Multi-Storage Backend**: 5 storage backends with unified API
- ✅ **VOD Architecture**: Scalable video delivery system

---

## 🚀 Quick Start

1. **Installation**: Follow [DEPLOYMENT-GUIDE.md](DEPLOYMENT-GUIDE.md)
2. **Security**: Apply [Server-Hardening-Procedure.md](Server-Hardening-Procedure.md)
3. **Operations**: Reference [SOB-System-Operations-Book.md](SOB-System-Operations-Book.md)
4. **Storage Setup**: Configure using [STORAGE-QUICK-REFERENCE.md](STORAGE-QUICK-REFERENCE.md)

---

## 📞 Support Information

**System Classification**: Internal - IT Operations
**Criticality**: High (Guest-facing service)
**Availability Target**: 99.5% uptime
**Peak Load**: 500+ concurrent streaming sessions

For technical issues, refer to the operations manual and troubleshooting sections in individual guides.

---

## 📄 Additional Information

### Project Documentation
- **[EXECUTIVE-SUMMARY.md](EXECUTIVE-SUMMARY.md)** - High-level project overview and key achievements
- **[COMPLETION-REPORT.md](COMPLETION-REPORT.md)** - Project completion status and deliverables
- **[DOCUMENTATION-INDEX.md](DOCUMENTATION-INDEX.md)** - Complete documentation structure and reading guide
- **[EPG-SYNC-FIX.md](EPG-SYNC-FIX.md)** - EPG synchronization technical details

### Implementation Guides
- **[STORAGE-IMPLEMENTATION-README.md](STORAGE-IMPLEMENTATION-README.md)** - Multi-storage implementation walkthrough
- **[Setup Instructions for GitHub Users.md](Setup%20Instructions%20for%20GitHub%20Users.md)** - GitHub repository setup

### Security
- See **[../SECURITY.md](../SECURITY.md)** (in root) for security best practices and environment setup

---

## 📊 Documentation Stats

- **Total Pages**: 12+ guides
- **Architecture Diagrams**: 3 (DrawIO format)
- **Topics Covered**: Architecture, Deployment, Storage, Operations, Security, EPG
- **Total Content**: 50+ MB when including code examples and diagrams