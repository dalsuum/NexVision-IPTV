# NexVision IPTV - Oracle Cloud Implementation Plan

**Version**: 1.0  
**Date**: April 25, 2026  
**Target Platform**: Oracle Cloud Infrastructure (OCI)  
**Estimated Timeline**: 2-4 weeks  
**Estimated Cost**: $200-500/month (depending on usage)

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [Prerequisites](#prerequisites)
- [Infrastructure Architecture](#infrastructure-architecture)
- [Implementation Phases](#implementation-phases)
- [Security Configuration](#security-configuration)
- [Monitoring & Maintenance](#monitoring--maintenance)
- [Cost Estimation](#cost-estimation)
- [Risk Assessment](#risk-assessment)
- [Rollback Plan](#rollback-plan)

---

## Executive Summary

This implementation plan outlines the migration of the NexVision IPTV platform from on-premises infrastructure to Oracle Cloud Infrastructure (OCI). The plan focuses on high availability, scalability, and cost optimization while maintaining the hotel-grade performance required for IPTV streaming.

### Key Objectives
- ✅ Zero-downtime migration
- ✅ 99.9% uptime SLA
- ✅ Auto-scaling for peak loads
- ✅ Multi-region disaster recovery
- ✅ Cost optimization for variable usage

### Target Architecture
```
Oracle Cloud Infrastructure
├── Region: us-ashburn-1 (Primary)
├── Availability Domain: AD-1, AD-2, AD-3
├── VCN: 10.0.0.0/16
├── Subnets: Public (Web), Private (App/DB)
└── Services: Compute, MySQL, Object Storage, Load Balancer
```

---

## Prerequisites

### Oracle Cloud Account Setup
- [ ] Create Oracle Cloud account (Free Tier available)
- [ ] Enable Identity and Access Management (IAM)
- [ ] Configure billing alerts
- [ ] Create compartment: `nexvision-iptv-prod`

### Domain & DNS
- [ ] Register domain (e.g., `iptv.hotelcloud.com`)
- [ ] Configure DNS records in Oracle DNS or external provider
- [ ] SSL certificate from Oracle Cloud Certificate Management

### Local Development Environment
- [ ] OCI CLI installed and configured
- [ ] Terraform (optional, for infrastructure as code)
- [ ] Docker and Docker Compose for testing
- [ ] Git repository access

### Application Readiness
- [ ] Code tested on Ubuntu 22.04 (OCI default)
- [ ] Environment variables documented
- [ ] Database migration scripts prepared
- [ ] Backup of current production data

---

## Infrastructure Architecture

### Network Design
```
Virtual Cloud Network (VCN)
├── CIDR: 10.0.0.0/16
├── Public Subnet (Web Tier): 10.0.1.0/24
│   ├── Internet Gateway
│   ├── Load Balancer
│   └── Bastion Host
├── Private Subnet (App Tier): 10.0.2.0/24
│   ├── Application Servers
│   └── Redis Cache
└── Private Subnet (DB Tier): 10.0.3.0/24
    ├── MySQL Database
    └── Object Storage (Private)
```

### Compute Resources
| Component | Instance Type | Count | OS | Purpose |
|-----------|---------------|-------|----|---------|
| **Web Servers** | VM.Standard.E4.Flex (2 OCPU, 16GB RAM) | 2-4 | Ubuntu 22.04 | Nginx + Gunicorn |
| **Database** | MySQL.HeatWave.VM.Standard.E4 | 1 | Oracle Linux | MySQL 8.0 |
| **Redis Cache** | VM.Standard.E4.Flex (1 OCPU, 8GB RAM) | 1 | Ubuntu 22.04 | Redis 7.0 |
| **Bastion Host** | VM.Standard.E3.Flex (1 OCPU, 4GB RAM) | 1 | Ubuntu 22.04 | SSH access |

### Storage Architecture
| Storage Type | OCI Service | Use Case | Capacity |
|--------------|-------------|----------|----------|
| **Block Storage** | OCI Block Volumes | VM boot volumes | 100GB each |
| **Object Storage** | OCI Object Storage | VOD files, backups | Unlimited |
| **File Storage** | OCI File Storage | Shared config, logs | 1TB |
| **Database Storage** | MySQL Storage | Application data | 100GB |

### Load Balancing
- **Load Balancer Type**: Network Load Balancer (Layer 4)
- **Backend Sets**: Web servers (port 80/443)
- **Health Checks**: HTTP /health endpoint
- **SSL Termination**: Yes (Oracle-managed certificates)

---

## Implementation Phases

### Phase 1: Infrastructure Provisioning (Week 1)

#### Day 1-2: Core Infrastructure
```bash
# 1. Create VCN and subnets
oci network vcn create --compartment-id $COMPARTMENT_ID \
  --cidr-block 10.0.0.0/16 --display-name nexvision-vcn

# 2. Create security lists
oci network security-list create --vcn-id $VCN_ID \
  --display-name web-security-list \
  --ingress-security-rules '[{"source": "0.0.0.0/0", "protocol": "6", "tcpOptions": {"destinationPortRange": {"max": 443, "min": 443}}}]'

# 3. Create internet gateway
oci network internet-gateway create --vcn-id $VCN_ID \
  --display-name nexvision-igw

# 4. Create route tables
oci network route-table create --vcn-id $VCN_ID \
  --route-rules '[{"cidrBlock": "0.0.0.0/0", "networkEntityId": "$IGW_ID"}]'
```

#### Day 3-4: Compute Resources
```bash
# Create compute instances
oci compute instance create --compartment-id $COMPARTMENT_ID \
  --shape VM.Standard.E4.Flex \
  --shape-config '{"ocpus": 2, "memoryInGBs": 16}' \
  --image-id $UBUNTU_IMAGE_ID \
  --subnet-id $WEB_SUBNET_ID \
  --display-name nexvision-web-01
```

#### Day 5-7: Database Setup
```bash
# Create MySQL DB System
oci mysql db-system create --compartment-id $COMPARTMENT_ID \
  --shape-name MySQL.HeatWave.VM.Standard.E4 \
  --mysql-version 8.0.34 \
  --admin-username nexvision \
  --admin-password $DB_PASSWORD \
  --data-storage-size-in-gbs 100 \
  --subnet-id $DB_SUBNET_ID
```

### Phase 2: Application Deployment (Week 2)

#### Application Installation
```bash
# On each web server
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip nginx redis-server ffmpeg -y

# Install Python dependencies
cd /opt/nexvision
python3 -m venv venv
venv/bin/pip install -r requirements_prod.txt

# Configure Gunicorn
cp gunicorn.conf.py /etc/gunicorn.conf.py
cp wsgi.py /opt/nexvision/

# Configure Nginx
cp nginx/nexvision.conf /etc/nginx/sites-available/
ln -s /etc/nginx/sites-available/nexvision.conf /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

#### Database Migration
```bash
# Export from current system
mysqldump -u root -p nexvision > nexvision_backup.sql
mysqldump -u root -p nexvision_vod > vod_backup.sql

# Import to OCI MySQL
mysql -h $OCI_MYSQL_HOST -u nexvision -p nexvision < nexvision_backup.sql
mysql -h $OCI_MYSQL_HOST -u nexvision -p nexvision_vod < vod_backup.sql
```

#### Storage Configuration
```bash
# Configure Object Storage for VOD
oci os bucket create --compartment-id $COMPARTMENT_ID \
  --name nexvision-vod-storage

# Update storage_backends.py with OCI credentials
export OCI_ACCESS_KEY_ID=...
export OCI_SECRET_ACCESS_KEY=...
export OCI_BUCKET_NAME=nexvision-vod-storage
```

### Phase 3: Configuration & Testing (Week 3)

#### Environment Configuration
```bash
# .env file for production
cat > .env << EOF
USE_MYSQL=1
MYSQL_HOST=${OCI_MYSQL_HOST}
MYSQL_USER=nexvision
MYSQL_PASSWORD=${DB_PASSWORD}
MYSQL_DB=nexvision
MYSQL_VOD_DB=nexvision_vod

REDIS_URL=redis://localhost:6379/0
USE_X_ACCEL=1
SECRET_KEY=${GENERATED_SECRET}

# OCI Storage
STORAGE_BACKEND=oci
OCI_ACCESS_KEY_ID=${ACCESS_KEY}
OCI_SECRET_ACCESS_KEY=${SECRET_KEY}
OCI_BUCKET_NAME=nexvision-vod-storage
EOF
```

#### Load Balancer Setup
```bash
# Create Load Balancer
oci lb load-balancer create --compartment-id $COMPARTMENT_ID \
  --shape-name 100Mbps \
  --subnet-ids '["$WEB_SUBNET_ID"]' \
  --backend-sets '{"web-backend": {"backends": [{"ipAddress": "10.0.2.10", "port": 80}, {"ipAddress": "10.0.2.11", "port": 80}]}}'
```

#### SSL Configuration
```bash
# Request SSL certificate
oci certificates-management certificate create \
  --compartment-id $COMPARTMENT_ID \
  --certificate-config file://ssl-config.json

# Update Load Balancer with SSL
oci lb ssl-cipher-suite create --load-balancer-id $LB_ID \
  --name custom-ssl --ciphers '["ECDHE-RSA-AES256-GCM-SHA384"]'
```

### Phase 4: Go-Live & Monitoring (Week 4)

#### DNS Update
```bash
# Update DNS to point to Load Balancer IP
# Example: iptv.hotelcloud.com → 129.213.123.45
```

#### Health Checks
```bash
# Application health check
curl -f https://iptv.hotelcloud.com/api/settings

# Database connectivity
python3 -c "import db_mysql; print('DB OK')"

# Storage access
python3 -c "from storage_backends import upload_file; print('Storage OK')"
```

#### Monitoring Setup
```bash
# Enable OCI Monitoring
oci monitoring alarm create --compartment-id $COMPARTMENT_ID \
  --display-name "Web Server CPU High" \
  --metric-compartment-id $COMPARTMENT_ID \
  --namespace oci_computeagent \
  --query-text "CPUUtilization[1m].mean() > 80" \
  --severity CRITICAL
```

---

## Security Configuration

### Network Security
```bash
# Security List Rules
# Web Subnet (Allow)
- HTTP (80) from 0.0.0.0/0
- HTTPS (443) from 0.0.0.0/0
- SSH (22) from bastion host only

# App Subnet (Allow)
- HTTP (8000) from web subnet only
- Redis (6379) from app subnet only

# DB Subnet (Allow)
- MySQL (3306) from app subnet only
```

### Identity & Access Management
- [ ] Create IAM users for administrators
- [ ] Configure API keys for programmatic access
- [ ] Enable multi-factor authentication
- [ ] Set up compartment-level policies

### Data Encryption
- [ ] Enable encryption at rest for Block Storage
- [ ] Configure SSL/TLS for all connections
- [ ] Use OCI Vault for secrets management
- [ ] Encrypt database backups

### Backup Strategy
```bash
# Automated backups
oci mysql backup create --db-system-id $DB_SYSTEM_ID \
  --display-name "daily-backup-$(date +%Y%m%d)"

# Object Storage backups
oci os object bulk-upload --bucket-name nexvision-backups \
  --src-dir /opt/nexvision/backups/
```

---

## Monitoring & Maintenance

### OCI Monitoring Dashboard
- CPU, Memory, Network utilization
- Database connections and performance
- Storage I/O metrics
- Load Balancer request rates

### Application Monitoring
```bash
# Install monitoring agent
sudo apt install oci-unified-monitoring-agent

# Configure custom metrics
# - Active streams count
# - API response times
# - Database query performance
# - Storage upload/download rates
```

### Log Management
```bash
# Centralized logging
oci logging log create --compartment-id $COMPARTMENT_ID \
  --display-name "nexvision-app-logs" \
  --log-type SERVICE

# Log retention: 30 days
```

### Maintenance Windows
- **Weekly**: Security updates (Sunday 02:00 UTC)
- **Monthly**: Database optimization
- **Quarterly**: Full backup verification

---

## Cost Estimation

### Monthly Costs (Estimated)
| Service | Configuration | Cost |
|---------|---------------|------|
| **Compute** | 2x VM.Standard.E4.Flex (2 OCPU) | $100-150 |
| **MySQL** | HeatWave VM.Standard.E4 (100GB) | $150-200 |
| **Load Balancer** | 100Mbps | $20-30 |
| **Object Storage** | 1TB storage + transfer | $25-50 |
| **Block Storage** | 200GB total | $10-15 |
| **Network** | Data transfer | $20-50 |
| **Total** | | **$325-495/month** |

### Cost Optimization
- Use Reserved Instances for predictable workloads
- Implement auto-scaling to reduce compute costs
- Use Object Storage lifecycle policies for old backups
- Monitor and right-size instances based on usage

---

## Risk Assessment

### High Risk
| Risk | Impact | Mitigation |
|------|--------|------------|
| **Data Loss** | Critical | Multi-region backups, automated snapshots |
| **Service Outage** | High | Load balancer, auto-scaling, multi-AZ |
| **Security Breach** | Critical | Network security, encryption, monitoring |

### Medium Risk
| Risk | Impact | Mitigation |
|------|--------|------------|
| **Performance Issues** | Medium | Monitoring, auto-scaling, caching |
| **Cost Overrun** | Medium | Budget alerts, usage monitoring |
| **Configuration Errors** | Medium | Infrastructure as code, testing |

---

## Rollback Plan

### Emergency Rollback (Within 24 hours)
1. **DNS Rollback**: Point domain back to original IP
2. **Database Rollback**: Restore from pre-migration backup
3. **Application Rollback**: Deploy previous version to OCI instances

### Gradual Rollback (1-3 days)
1. **Traffic Shifting**: Gradually reduce OCI traffic using load balancer weights
2. **Data Synchronization**: Ensure data consistency between systems
3. **Full Cutover**: Complete rollback to on-premises

### Success Criteria
- [ ] All application features working
- [ ] Performance meets or exceeds current levels
- [ ] No data loss during migration
- [ ] Cost within budgeted amounts

---

## Implementation Checklist

### Pre-Migration
- [ ] Oracle Cloud account configured
- [ ] Domain and SSL certificates ready
- [ ] Application code tested on Ubuntu 22.04
- [ ] Database migration scripts prepared
- [ ] Backup of current system completed

### Infrastructure
- [ ] VCN and subnets created
- [ ] Security lists configured
- [ ] Compute instances provisioned
- [ ] MySQL database deployed
- [ ] Load balancer configured

### Application
- [ ] Code deployed to instances
- [ ] Environment variables configured
- [ ] Database migrated
- [ ] Storage backends configured
- [ ] SSL certificates installed

### Testing
- [ ] Functional testing completed
- [ ] Performance testing passed
- [ ] Security testing completed
- [ ] Failover testing successful

### Go-Live
- [ ] DNS updated
- [ ] Monitoring enabled
- [ ] Backup schedules active
- [ ] Support team notified

---

## Support & Documentation

### Oracle Cloud Resources
- [OCI Documentation](https://docs.oracle.com/en-us/iaas/)
- [OCI Training](https://learn.oracle.com/)
- [OCI Support](https://support.oracle.com/)

### NexVision Resources
- [Deployment Guide](DEPLOYMENT-GUIDE.md)
- [System Operations Book](SOB-System-Operations-Book.md)
- [Storage Integration Guide](STORAGE-INTEGRATION-GUIDE.md)

### Contact Information
- **Technical Lead**: [Name]
- **Oracle Cloud Support**: [Account Manager]
- **Emergency Contact**: [24/7 Support]

---

*This implementation plan should be reviewed and approved by all stakeholders before proceeding. Regular status updates and risk assessments should be conducted throughout the implementation phases.*</content>
<parameter name="filePath">/opt/nexvision/docs/ORACLE-CLOUD-IMPLEMENTATION.md