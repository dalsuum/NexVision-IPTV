# NexVision IPTV — Multicloud Deployment Guide

**Version**: 8.21  
**Stack**: Flask + Gunicorn (gevent) + Nginx + MySQL + Redis  
**Supports**: 500+ concurrent HLS streams via Nginx X-Accel-Redirect

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites & Common Preparation](#2-prerequisites--common-preparation)
3. [Standalone (Bare-Metal / Self-Hosted VM)](#3-standalone-bare-metal--self-hosted-vm)
4. [DigitalOcean](#4-digitalocean)
5. [Amazon Web Services (AWS)](#5-amazon-web-services-aws)
6. [Microsoft Azure](#6-microsoft-azure)
7. [Google Cloud Platform (GCP)](#7-google-cloud-platform-gcp)
8. [Post-Deployment Hardening (All Platforms)](#8-post-deployment-hardening-all-platforms)
9. [Health Checks & Monitoring](#9-health-checks--monitoring)
10. [Disaster Recovery & Backups](#10-disaster-recovery--backups)
11. [Scaling Cheat-Sheet](#11-scaling-cheat-sheet)

---

## 1. Architecture Overview

```
Internet
    │
    ▼
[Load Balancer / Firewall]  ← platform-specific
    │
    ▼
[Nginx]  ─── static files / HLS (X-Accel-Redirect, no Python in hot path)
    │
    ▼  (unix socket)
[Gunicorn + gevent]  ← Flask application (app/wsgi.py)
    │              │
    ▼              ▼
[MySQL 8]      [Redis 7]   ← session cache / Flask-Caching
    │
    ▼  (optional)
[Object Storage]  ← S3 / Azure Blob / GCS / DO Spaces  (VOD files)
```

### Port map

| Service   | Listen            | Exposed |
|-----------|-------------------|---------|
| Nginx     | 0.0.0.0:80 / 443  | Yes     |
| Gunicorn  | unix socket       | No      |
| MySQL     | 127.0.0.1:3306    | No      |
| Redis     | 127.0.0.1:6379    | No      |

---

## 2. Prerequisites & Common Preparation

These steps are identical regardless of cloud provider.

### 2.1 OS & packages

```bash
# Ubuntu 22.04 LTS / 24.04 LTS (recommended)
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y \
    python3.11 python3.11-venv python3.11-dev \
    nginx mysql-server redis-server \
    ffmpeg \                         # VOD transcoding
    git curl certbot python3-certbot-nginx \
    build-essential libssl-dev libffi-dev \
    logrotate fail2ban ufw
```

### 2.2 System user

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin nexvision
sudo mkdir -p /opt/nexvision /run/nexvision
sudo chown nexvision:nexvision /opt/nexvision /run/nexvision
```

### 2.3 Clone & virtualenv

```bash
sudo -u nexvision git clone https://github.com/YOUR_ORG/nexvision.git /opt/nexvision
cd /opt/nexvision
sudo -u nexvision python3.11 -m venv venv
sudo -u nexvision venv/bin/pip install --upgrade pip
sudo -u nexvision venv/bin/pip install -r requirements_prod.txt
```

### 2.4 Environment file

```bash
sudo -u nexvision tee /opt/nexvision/.env <<'EOF'
SECRET_KEY=<generate: python3 -c "import secrets; print(secrets.token_hex(32))">
VOD_API_KEY=<generate: python3 -c "import secrets; print(secrets.token_hex(32))">
NEXVISION_URL=https://your.domain.com
NEXVISION_TOKEN=<your-internal-token>

DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=nexvision
DB_USER=nexvision
DB_PASSWORD=<strong-random-password>

REDIS_URL=redis://127.0.0.1:6379/0
EOF

sudo chmod 600 /opt/nexvision/.env
sudo chown nexvision:nexvision /opt/nexvision/.env
```

### 2.5 MySQL setup

```bash
sudo mysql -u root <<'SQL'
CREATE DATABASE nexvision CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'nexvision'@'localhost' IDENTIFIED BY '<DB_PASSWORD>';
GRANT ALL PRIVILEGES ON nexvision.* TO 'nexvision'@'localhost';
FLUSH PRIVILEGES;
SQL
```

### 2.6 Redis hardening

```bash
sudo tee -a /etc/redis/redis.conf <<'EOF'
bind 127.0.0.1
requirepass <redis-strong-password>
maxmemory 512mb
maxmemory-policy allkeys-lru
EOF
sudo systemctl restart redis-server
```

Add `REDIS_URL=redis://:password@127.0.0.1:6379/0` to `.env` if you set a password.

### 2.7 tmpfiles.d (socket persistence across reboots)

```bash
sudo tee /etc/tmpfiles.d/nexvision.conf <<'EOF'
d /run/nexvision 0755 nexvision nexvision -
EOF
sudo systemd-tmpfiles --create
```

### 2.8 Systemd service

```bash
sudo tee /etc/systemd/system/nexvision.service <<'EOF'
[Unit]
Description=NexVision IPTV (Gunicorn + gevent)
After=network.target mysql.service redis.service

[Service]
User=nexvision
Group=nexvision
WorkingDirectory=/opt/nexvision
EnvironmentFile=/opt/nexvision/.env
ExecStart=/opt/nexvision/venv/bin/gunicorn -c /opt/nexvision/app/gunicorn.conf.py app.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now nexvision
```

### 2.9 Nginx

```bash
sudo cp /opt/nexvision/nginx/nexvision.conf /etc/nginx/sites-available/nexvision
sudo ln -s /etc/nginx/sites-available/nexvision /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl enable --now nginx
```

---

## 3. Standalone (Bare-Metal / Self-Hosted VM)

**Best for**: hotel on-premise, ISP headend, private datacenter.

### 3.1 Recommended hardware

| Load             | CPU      | RAM   | Storage       | NIC        |
|------------------|----------|-------|---------------|------------|
| ≤ 50 streams     | 4 cores  | 8 GB  | 500 GB SSD    | 1 Gbps     |
| 50–200 streams   | 8 cores  | 16 GB | 1 TB SSD      | 1 Gbps     |
| 200–500 streams  | 16 cores | 32 GB | 2 TB NVMe     | 10 Gbps    |
| 500+ streams     | 32 cores | 64 GB | RAID-10 NVMe  | 10 Gbps    |

### 3.2 UFW firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 3.3 SSL with Let's Encrypt (requires public domain)

```bash
sudo certbot --nginx -d your.domain.com --agree-tos -m admin@your.domain.com
sudo systemctl enable certbot.timer
```

For **LAN-only / hotel deployments** without a public domain, use a self-signed cert:

```bash
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:4096 \
  -keyout /etc/ssl/private/nexvision.key \
  -out /etc/ssl/certs/nexvision.crt \
  -subj "/CN=nexvision-iptv"

# Then in nginx config replace the certbot lines with:
# ssl_certificate     /etc/ssl/certs/nexvision.crt;
# ssl_certificate_key /etc/ssl/private/nexvision.key;
```

### 3.4 VOD storage

All VOD files stay local under `/opt/nexvision/vod/`. For multi-TB libraries mount
a dedicated block device:

```bash
sudo mkfs.ext4 /dev/sdb
sudo mount /dev/sdb /opt/nexvision/vod
echo '/dev/sdb /opt/nexvision/vod ext4 defaults,noatime 0 2' | sudo tee -a /etc/fstab
sudo chown -R nexvision:nexvision /opt/nexvision/vod
```

---

## 4. DigitalOcean

**Best for**: cost-effective VPS, Managed DB, Spaces object storage.

### 4.1 Droplet sizing

| Use-case         | Droplet          | Monthly cost (approx.) |
|------------------|------------------|------------------------|
| Dev / staging    | Basic 2 vCPU/4GB | ~$24                   |
| Production       | CPU-Opt 4 vCPU/8GB | ~$84                 |
| High traffic     | CPU-Opt 8 vCPU/16GB | ~$168               |

### 4.2 Infrastructure setup via `doctl`

```bash
# Install doctl: https://docs.digitalocean.com/reference/doctl/how-to/install/
doctl auth init

# Create Droplet (Ubuntu 24.04, CPU-Optimized, NYC3)
doctl compute droplet create nexvision-prod \
  --region nyc3 \
  --size c-4-intel \
  --image ubuntu-24-04-x64 \
  --ssh-keys $(doctl compute ssh-key list --format ID --no-header) \
  --enable-monitoring \
  --tag-names nexvision,production

# Create Managed MySQL 8 cluster
doctl databases create nexvision-db \
  --engine mysql \
  --version 8 \
  --region nyc3 \
  --size db-s-2vcpu-4gb \
  --num-nodes 1

# Create Spaces bucket for VOD
doctl spaces create nexvision-vod --region nyc3

# Create VPC-peered Redis
doctl databases create nexvision-redis \
  --engine redis \
  --version 7 \
  --region nyc3 \
  --size db-s-1vcpu-1gb \
  --num-nodes 1
```

### 4.3 Firewall (Cloud Firewall, not UFW)

```bash
doctl compute firewall create \
  --name nexvision-fw \
  --inbound-rules "protocol:tcp,ports:22,address:YOUR_MGMT_IP protocol:tcp,ports:80,address:0.0.0.0/0,::0/0 protocol:tcp,ports:443,address:0.0.0.0/0,::0/0" \
  --outbound-rules "protocol:tcp,ports:all,address:0.0.0.0/0 protocol:udp,ports:all,address:0.0.0.0/0"
```

### 4.4 Spaces (S3-compatible) for VOD

```bash
pip install boto3

# .env additions
cat >> /opt/nexvision/.env <<'EOF'
VOD_STORAGE_BACKEND=spaces
SPACES_KEY=<DO_Spaces_access_key>
SPACES_SECRET=<DO_Spaces_secret>
SPACES_BUCKET=nexvision-vod
SPACES_REGION=nyc3
SPACES_ENDPOINT=https://nyc3.digitaloceanspaces.com
EOF
```

### 4.5 Connect to Managed MySQL

```bash
# Get connection string from control panel or:
doctl databases connection nexvision-db --format Host,Port,User,Password

# Update .env
DB_HOST=<managed-db-host>
DB_PORT=25060
DB_NAME=nexvision
DB_USER=doadmin
DB_PASSWORD=<managed-password>
DB_SSL=true   # Managed DB enforces SSL
```

### 4.6 DigitalOcean best practices

- Enable **Backups** on the Droplet (weekly snapshots, +20% cost).
- Enable **Monitoring** alerts for CPU > 80% and disk > 80%.
- Use a **Reserved IP** so you can re-point to a new Droplet without DNS changes.
- Enable **VPC** — keep DB and Redis inside private network only.
- Use **Managed DB** instead of self-hosted MySQL for automatic failover.

---

## 5. Amazon Web Services (AWS)

**Best for**: enterprise scale, global CDN (CloudFront), SLA requirements.

### 5.1 Recommended architecture

```
Route 53 (DNS)
     │
     ▼
CloudFront (CDN) ─── S3 (VOD files, static assets)
     │
     ▼
Application Load Balancer (ALB)
     │
     ▼
Auto Scaling Group
  └── EC2 instances (t3.large / c6i.xlarge)
           │
           ▼ (private subnet)
      RDS MySQL 8 (Multi-AZ)   +   ElastiCache Redis
```

### 5.2 EC2 instance sizing

| Load            | Instance     | vCPU | RAM   |
|-----------------|--------------|------|-------|
| Dev             | t3.medium    | 2    | 4 GB  |
| Production      | c6i.xlarge   | 4    | 8 GB  |
| High traffic    | c6i.2xlarge  | 8    | 16 GB |

### 5.3 Terraform skeleton

```hcl
# main.tf — NexVision on AWS (minimal)
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" { region = "us-east-1" }

# ── VPC ──────────────────────────────────────────────────────────────────────
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name            = "nexvision-vpc"
  cidr            = "10.10.0.0/16"
  azs             = ["us-east-1a", "us-east-1b"]
  public_subnets  = ["10.10.1.0/24", "10.10.2.0/24"]
  private_subnets = ["10.10.11.0/24", "10.10.12.0/24"]
  enable_nat_gateway = true
}

# ── Security Groups ───────────────────────────────────────────────────────────
resource "aws_security_group" "app" {
  name   = "nexvision-app"
  vpc_id = module.vpc.vpc_id

  ingress { from_port = 80;   to_port = 80;   protocol = "tcp"; cidr_blocks = ["0.0.0.0/0"] }
  ingress { from_port = 443;  to_port = 443;  protocol = "tcp"; cidr_blocks = ["0.0.0.0/0"] }
  ingress { from_port = 22;   to_port = 22;   protocol = "tcp"; cidr_blocks = ["YOUR_MGMT_CIDR/32"] }
  egress  { from_port = 0;    to_port = 0;    protocol = "-1";  cidr_blocks = ["0.0.0.0/0"] }
}

resource "aws_security_group" "db" {
  name   = "nexvision-db"
  vpc_id = module.vpc.vpc_id
  ingress {
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
}

# ── RDS MySQL 8 ───────────────────────────────────────────────────────────────
resource "aws_db_instance" "mysql" {
  identifier        = "nexvision-mysql"
  engine            = "mysql"
  engine_version    = "8.0"
  instance_class    = "db.t3.medium"
  allocated_storage = 100
  storage_type      = "gp3"
  db_name           = "nexvision"
  username          = "nexvision"
  password          = var.db_password
  multi_az          = true
  storage_encrypted = true
  skip_final_snapshot = false
  final_snapshot_identifier = "nexvision-final"
  vpc_security_group_ids = [aws_security_group.db.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name
}

# ── ElastiCache Redis ─────────────────────────────────────────────────────────
resource "aws_elasticache_cluster" "redis" {
  cluster_id        = "nexvision-redis"
  engine            = "redis"
  node_type         = "cache.t3.micro"
  num_cache_nodes   = 1
  engine_version    = "7.0"
  subnet_group_name = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.db.id]
}

# ── S3 bucket for VOD ─────────────────────────────────────────────────────────
resource "aws_s3_bucket" "vod" {
  bucket = "nexvision-vod-${random_id.suffix.hex}"
}

resource "aws_s3_bucket_public_access_block" "vod" {
  bucket                  = aws_s3_bucket.vod.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── EC2 Launch Template ───────────────────────────────────────────────────────
resource "aws_launch_template" "app" {
  name_prefix   = "nexvision-"
  image_id      = data.aws_ami.ubuntu.id
  instance_type = "c6i.xlarge"
  key_name      = var.key_pair_name

  network_interfaces {
    security_groups = [aws_security_group.app.id]
    subnet_id       = module.vpc.public_subnets[0]
  }

  user_data = base64encode(file("userdata.sh"))

  tag_specifications {
    resource_type = "instance"
    tags = { Name = "nexvision-app", Environment = "production" }
  }
}
```

### 5.4 AWS-specific `.env` additions

```bash
# S3 VOD storage
VOD_STORAGE_BACKEND=s3
AWS_ACCESS_KEY_ID=<IAM-key>          # prefer IAM Role on EC2, not static keys
AWS_SECRET_ACCESS_KEY=<IAM-secret>
AWS_REGION=us-east-1
S3_BUCKET=nexvision-vod-xxxx

# RDS connection
DB_HOST=nexvision-mysql.xxxx.us-east-1.rds.amazonaws.com
DB_PORT=3306
DB_SSL=true

# ElastiCache Redis
REDIS_URL=redis://nexvision-redis.xxxx.cfg.use1.cache.amazonaws.com:6379/0
```

### 5.5 IAM Role (EC2 → S3, no static keys)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::nexvision-vod-*",
        "arn:aws:s3:::nexvision-vod-*/*"
      ]
    }
  ]
}
```

Attach this policy to an IAM Role, then attach the Role to the EC2 instance. Do **not** put `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in `.env` when running on EC2.

### 5.6 CloudFront for HLS delivery

```hcl
resource "aws_cloudfront_distribution" "hls" {
  enabled = true

  origin {
    domain_name = aws_s3_bucket.vod.bucket_regional_domain_name
    origin_id   = "vod-s3"
    s3_origin_config { origin_access_identity = aws_cloudfront_origin_access_identity.oai.cloudfront_access_identity_path }
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "vod-s3"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = 86400
    max_ttl     = 31536000
  }

  restrictions { geo_restriction { restriction_type = "none" } }
  viewer_certificate { cloudfront_default_certificate = true }
}
```

### 5.7 AWS best practices

- Use **IAM Roles** on EC2 — never store static AWS keys on the instance.
- Enable **RDS Multi-AZ** and **automated backups** (7-day retention minimum).
- Use **Systems Manager Parameter Store** or **Secrets Manager** for secrets instead of `.env`.
- Enable **VPC Flow Logs** for network audit trail.
- Use **CloudWatch** agent on EC2 for disk/memory metrics (not included by default).
- Tag all resources: `Environment=production`, `Project=nexvision`, `Owner=team`.

---

## 6. Microsoft Azure

**Best for**: Microsoft-heavy enterprise, Azure Active Directory integration.

### 6.1 Recommended architecture

```
Azure DNS
    │
    ▼
Azure Front Door (CDN + WAF)
    │
    ▼
Azure Load Balancer
    │
    ▼
Virtual Machine Scale Set (VMSS)
  └── Ubuntu VMs (Standard_F4s_v2)
          │
          ▼ (private subnet / VNet)
    Azure Database for MySQL Flexible Server  +  Azure Cache for Redis
          │
    Azure Blob Storage (VOD)
```

### 6.2 Quickstart with Azure CLI

```bash
# Login and set subscription
az login
az account set --subscription "YOUR_SUBSCRIPTION_ID"

# Variables
RG="nexvision-rg"
LOCATION="eastus"
VNET="nexvision-vnet"

# Resource group
az group create --name $RG --location $LOCATION

# VNet + subnets
az network vnet create --name $VNET -g $RG \
  --address-prefix 10.20.0.0/16 \
  --subnet-name app-subnet --subnet-prefix 10.20.1.0/24

az network vnet subnet create --name db-subnet -g $RG \
  --vnet-name $VNET --address-prefix 10.20.11.0/24

# NSG
az network nsg create --name nexvision-nsg -g $RG --location $LOCATION
az network nsg rule create --name AllowHTTP  --nsg-name nexvision-nsg -g $RG \
  --priority 100 --direction Inbound --access Allow \
  --protocol Tcp --destination-port-range 80
az network nsg rule create --name AllowHTTPS --nsg-name nexvision-nsg -g $RG \
  --priority 110 --direction Inbound --access Allow \
  --protocol Tcp --destination-port-range 443
az network nsg rule create --name AllowSSH   --nsg-name nexvision-nsg -g $RG \
  --priority 120 --direction Inbound --access Allow \
  --protocol Tcp --destination-port-range 22 \
  --source-address-prefix "YOUR_MGMT_IP/32"

# VM (Standard_F4s_v2 = 4 vCPU, 8 GB RAM)
az vm create --name nexvision-vm -g $RG \
  --image Ubuntu2404 \
  --size Standard_F4s_v2 \
  --admin-username nexvision-admin \
  --ssh-key-values ~/.ssh/id_rsa.pub \
  --vnet-name $VNET --subnet app-subnet \
  --nsg nexvision-nsg \
  --public-ip-sku Standard

# Azure Database for MySQL Flexible Server
az mysql flexible-server create \
  --name nexvision-mysql -g $RG --location $LOCATION \
  --admin-user nexvision --admin-password "$(openssl rand -base64 24)" \
  --sku-name Standard_D2ds_v4 \
  --tier GeneralPurpose \
  --version 8.0 \
  --storage-size 128 \
  --vnet $VNET --subnet db-subnet \
  --private-dns-zone nexvision.private.mysql.database.azure.com

# Azure Cache for Redis
az redis create --name nexvision-redis -g $RG \
  --location $LOCATION \
  --sku Basic --vm-size C1

# Azure Blob Storage for VOD
az storage account create --name nexvisionvod -g $RG \
  --location $LOCATION --sku Standard_LRS --https-only true \
  --min-tls-version TLS1_2

az storage container create --name vod \
  --account-name nexvisionvod --public-access off
```

### 6.3 Azure-specific `.env` additions

```bash
pip install azure-storage-blob azure-identity

# .env additions
VOD_STORAGE_BACKEND=azure
AZURE_STORAGE_ACCOUNT=nexvisionvod
AZURE_STORAGE_CONTAINER=vod
# Use Managed Identity instead of connection string in production:
AZURE_USE_MANAGED_IDENTITY=true
# Fallback (dev only):
# AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...

DB_HOST=nexvision-mysql.mysql.database.azure.com
DB_PORT=3306
DB_SSL=true

REDIS_URL=rediss://:PRIMARY_KEY@nexvision-redis.redis.cache.windows.net:6380/0
```

### 6.4 Managed Identity for Blob Storage (no credentials in code)

```bash
# Assign Storage Blob Data Contributor to the VM's system-assigned identity
VM_PRINCIPAL=$(az vm show --name nexvision-vm -g nexvision-rg \
  --query "identity.principalId" -o tsv)

STORAGE_ID=$(az storage account show --name nexvisionvod -g nexvision-rg \
  --query id -o tsv)

az role assignment create \
  --assignee $VM_PRINCIPAL \
  --role "Storage Blob Data Contributor" \
  --scope $STORAGE_ID
```

Then in Python:
```python
from azure.identity import ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient

credential = ManagedIdentityCredential()
client = BlobServiceClient(
    account_url="https://nexvisionvod.blob.core.windows.net",
    credential=credential
)
```

### 6.5 Azure best practices

- Use **Managed Identity** — eliminates storage account keys from `.env`.
- Enable **Microsoft Defender for Cloud** (free tier) on the subscription.
- Enable **Azure Backup** for VMs and MySQL Flexible Server.
- Use **Azure Key Vault** for SECRET_KEY and VOD_API_KEY storage.
- Enable **diagnostic settings** on all resources → Log Analytics Workspace.
- Use **Azure Front Door** Premium for built-in WAF rules (OWASP 3.2).
- Tag resources: `environment=production`, `project=nexvision`.

---

## 7. Google Cloud Platform (GCP)

**Best for**: global load balancing, Cloud CDN, BigQuery analytics.

### 7.1 Recommended architecture

```
Cloud DNS
    │
    ▼
Cloud Load Balancing (HTTPS)  ──  Cloud CDN
    │
    ▼
Managed Instance Group (MIG)
  └── Compute Engine VMs (n2-standard-4)
          │
          ▼ (private VPC)
    Cloud SQL for MySQL 8  +  Memorystore for Redis
          │
    Cloud Storage (VOD)
```

### 7.2 Quickstart with `gcloud`

```bash
gcloud auth login
PROJECT_ID="nexvision-prod"
REGION="us-central1"
ZONE="us-central1-a"

gcloud projects create $PROJECT_ID --name="NexVision IPTV"
gcloud config set project $PROJECT_ID

# Enable APIs
gcloud services enable \
  compute.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com

# VPC
gcloud compute networks create nexvision-vpc --subnet-mode=custom
gcloud compute networks subnets create app-subnet \
  --network=nexvision-vpc --region=$REGION --range=10.30.1.0/24
gcloud compute networks subnets create db-subnet \
  --network=nexvision-vpc --region=$REGION --range=10.30.11.0/24

# Firewall rules
gcloud compute firewall-rules create nexvision-allow-http \
  --network=nexvision-vpc --allow=tcp:80,tcp:443 \
  --source-ranges=0.0.0.0/0 --target-tags=nexvision-app

gcloud compute firewall-rules create nexvision-allow-ssh \
  --network=nexvision-vpc --allow=tcp:22 \
  --source-ranges="YOUR_MGMT_IP/32" --target-tags=nexvision-app

# Compute Engine VM (n2-standard-4 = 4 vCPU, 16 GB)
gcloud compute instances create nexvision-vm \
  --zone=$ZONE \
  --machine-type=n2-standard-4 \
  --image-family=ubuntu-2404-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=50GB \
  --boot-disk-type=pd-ssd \
  --network=nexvision-vpc \
  --subnet=app-subnet \
  --tags=nexvision-app \
  --service-account=nexvision-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --scopes=cloud-platform

# Cloud SQL MySQL 8
gcloud sql instances create nexvision-mysql \
  --database-version=MYSQL_8_0 \
  --tier=db-n1-standard-2 \
  --region=$REGION \
  --network=nexvision-vpc \
  --no-assign-ip \
  --availability-type=REGIONAL \
  --backup-start-time=03:00 \
  --storage-type=SSD \
  --storage-size=100GB

gcloud sql databases create nexvision --instance=nexvision-mysql
gcloud sql users create nexvision --instance=nexvision-mysql \
  --password="$(openssl rand -base64 24)"

# Memorystore Redis
gcloud redis instances create nexvision-redis \
  --size=1 \
  --region=$REGION \
  --redis-version=redis_7_0 \
  --network=projects/${PROJECT_ID}/global/networks/nexvision-vpc \
  --tier=STANDARD_HA

# Cloud Storage bucket for VOD
gsutil mb -p $PROJECT_ID -l $REGION -b on gs://nexvision-vod-${PROJECT_ID}
gsutil uniformbucketlevelaccess set on gs://nexvision-vod-${PROJECT_ID}
```

### 7.3 Service Account for GCS (no credentials on VM)

```bash
# Create SA
gcloud iam service-accounts create nexvision-sa \
  --display-name="NexVision App SA"

# Grant Storage Object Admin
gsutil iam ch \
  serviceAccount:nexvision-sa@${PROJECT_ID}.iam.gserviceaccount.com:roles/storage.objectAdmin \
  gs://nexvision-vod-${PROJECT_ID}

# Grant Cloud SQL Client
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:nexvision-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"
```

Attach the SA to the VM (`--service-account` flag above). The SDK picks up ADC automatically — no keys needed.

### 7.4 Secret Manager for `.env` secrets

```bash
pip install google-cloud-secret-manager

# Store SECRET_KEY
echo -n "your-secret-key" | gcloud secrets create nexvision-secret-key \
  --data-file=- --replication-policy=automatic

# Grant access to SA
gcloud secrets add-iam-policy-binding nexvision-secret-key \
  --member="serviceAccount:nexvision-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### 7.5 GCP-specific `.env` additions

```bash
pip install google-cloud-storage

VOD_STORAGE_BACKEND=gcs
GCS_BUCKET=nexvision-vod-nexvision-prod
GCS_PROJECT=nexvision-prod
# No credentials needed — uses Workload Identity / ADC

DB_HOST=/cloudsql/nexvision-prod:us-central1:nexvision-mysql   # Cloud SQL Auth proxy
DB_PORT=3306
DB_SSL=false   # proxy handles TLS

REDIS_URL=redis://10.30.xx.xx:6379/0   # Memorystore private IP
```

### 7.6 Cloud SQL Auth Proxy (recommended over direct IP)

```bash
# Download proxy
curl -o /usr/local/bin/cloud-sql-proxy \
  https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.6.0/cloud-sql-proxy.linux.amd64
chmod +x /usr/local/bin/cloud-sql-proxy

# Systemd unit for proxy
sudo tee /etc/systemd/system/cloud-sql-proxy.service <<'EOF'
[Unit]
Description=Cloud SQL Auth Proxy
After=network.target

[Service]
User=nexvision
ExecStart=/usr/local/bin/cloud-sql-proxy \
  --private-ip nexvision-prod:us-central1:nexvision-mysql
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now cloud-sql-proxy
```

### 7.7 GCP best practices

- Use **Workload Identity / Application Default Credentials** — no service account key files.
- Enable **Cloud Armor** (WAF) on the HTTPS Load Balancer.
- Use **Secret Manager** for all secrets; read them at startup, not at deploy time.
- Enable **Cloud Logging** and **Cloud Monitoring** agents on VMs.
- Use **Managed Instance Groups** with health checks for auto-healing.
- Enable **VPC Service Controls** to restrict data exfiltration.
- Set **organization policy** `constraints/compute.requireOsLogin` for SSH audit trails.

---

## 8. Post-Deployment Hardening (All Platforms)

### 8.1 HTTPS / TLS

```nginx
# /etc/nginx/sites-available/nexvision  — SSL block
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name your.domain.com;

    ssl_certificate     /etc/letsencrypt/live/your.domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your.domain.com/privkey.pem;

    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers on;
    ssl_session_timeout 1d;
    ssl_session_cache   shared:SSL:50m;
    ssl_stapling        on;
    ssl_stapling_verify on;
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
}

# Redirect HTTP → HTTPS
server {
    listen 80;
    return 301 https://$host$request_uri;
}
```

### 8.2 Security headers

```nginx
# Add inside server {} block
add_header X-Content-Type-Options    "nosniff"         always;
add_header X-Frame-Options           "SAMEORIGIN"      always;
add_header X-XSS-Protection          "1; mode=block"   always;
add_header Referrer-Policy           "strict-origin"   always;
add_header Permissions-Policy        "geolocation=(), camera=()" always;
add_header Content-Security-Policy   "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:;" always;
```

### 8.3 Fail2ban

```bash
sudo tee /etc/fail2ban/jail.d/nexvision.conf <<'EOF'
[nginx-http-auth]
enabled = true
port    = http,https
logpath = /var/log/nginx/nexvision_access.log
maxretry = 5
bantime  = 3600

[nginx-limit-req]
enabled = true
port    = http,https
logpath = /var/log/nginx/nexvision_error.log
maxretry = 10
bantime  = 600
EOF

sudo systemctl restart fail2ban
```

### 8.4 Rate limiting in Nginx

```nginx
# Add to http {} block in nginx.conf
limit_req_zone $binary_remote_addr zone=api:10m rate=30r/m;
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

# In server {} block
location /api/ {
    limit_req zone=api burst=10 nodelay;
    limit_req_status 429;
    proxy_pass http://nexvision_app;
}

location /login {
    limit_req zone=login burst=3 nodelay;
    limit_req_status 429;
    proxy_pass http://nexvision_app;
}
```

### 8.5 Automated certificate renewal

```bash
# Certbot timer (installed by default)
sudo systemctl status certbot.timer

# Manual test
sudo certbot renew --dry-run
```

---

## 9. Health Checks & Monitoring

### 9.1 Application health endpoint

```bash
# Verify the API is responding
curl -sf http://localhost/api/settings | python3 -m json.tool
```

### 9.2 Systemd health check script

```bash
sudo tee /usr/local/bin/nexvision-health <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

check() { systemctl is-active --quiet "$1" && echo "  [OK] $1" || { echo "  [FAIL] $1"; FAILED=1; }; }
FAILED=0
check nexvision
check nginx
check mysql
check redis-server

HTTP=$(curl -so /dev/null -w "%{http_code}" http://localhost/api/settings)
[ "$HTTP" = "200" ] && echo "  [OK] HTTP /api/settings" || { echo "  [FAIL] HTTP $HTTP"; FAILED=1; }

[ $FAILED -eq 0 ] && echo "Status: HEALTHY" || { echo "Status: DEGRADED"; exit 1; }
EOF
chmod +x /usr/local/bin/nexvision-health
```

### 9.3 Cron monitoring (all platforms)

```bash
# Every 5 minutes — alert on failure
sudo tee /etc/cron.d/nexvision-health <<'EOF'
*/5 * * * * root /usr/local/bin/nexvision-health || \
  mail -s "NexVision DEGRADED on $(hostname)" admin@your.domain.com < /dev/null
EOF
```

### 9.4 Log locations

| Log                  | Path                                      |
|----------------------|-------------------------------------------|
| Application (stdout) | `journalctl -u nexvision -f`              |
| Nginx access         | `/var/log/nginx/nexvision_access.log`     |
| Nginx error          | `/var/log/nginx/nexvision_error.log`      |
| MySQL                | `/var/log/mysql/error.log`                |
| Redis                | `/var/log/redis/redis-server.log`         |

---

## 10. Disaster Recovery & Backups

### 10.1 MySQL dump (all platforms)

```bash
sudo tee /usr/local/bin/nexvision-backup <<'EOF'
#!/usr/bin/env bash
DEST=/var/backups/nexvision
mkdir -p $DEST
DATE=$(date +%Y%m%d_%H%M%S)

# Database
mysqldump -u nexvision -p"$DB_PASSWORD" nexvision \
  --single-transaction --routines --triggers \
  | gzip > $DEST/db_${DATE}.sql.gz

# Application (uploads, config)
tar -czf $DEST/app_${DATE}.tar.gz \
  /opt/nexvision/uploads \
  /opt/nexvision/.env

# Rotate: keep 14 days
find $DEST -mtime +14 -delete

echo "Backup complete: $DEST"
EOF
chmod +x /usr/local/bin/nexvision-backup

# Cron: daily at 02:00
echo "0 2 * * * root /usr/local/bin/nexvision-backup" | sudo tee /etc/cron.d/nexvision-backup
```

### 10.2 Off-site backup to object storage

```bash
# Add to nexvision-backup after local dump:
# AWS S3
aws s3 sync /var/backups/nexvision s3://nexvision-backups/$(hostname)/

# DigitalOcean Spaces
s3cmd sync /var/backups/nexvision s3://nexvision-backups/$(hostname)/

# GCS
gsutil -m rsync /var/backups/nexvision gs://nexvision-backups/$(hostname)/

# Azure Blob
az storage blob upload-batch \
  --destination nexvision-backups \
  --source /var/backups/nexvision \
  --account-name nexvisionbackups
```

### 10.3 Recovery procedure

```bash
# 1. Provision new VM with this guide's prerequisites
# 2. Restore application code (git clone)
# 3. Restore .env from backup / secret manager
# 4. Restore database
gunzip < /var/backups/nexvision/db_YYYYMMDD_HHMMSS.sql.gz | mysql -u nexvision -p nexvision
# 5. Restore uploads
tar -xzf /var/backups/nexvision/app_YYYYMMDD_HHMMSS.tar.gz -C /
# 6. Start services
sudo systemctl start nexvision nginx
# 7. Run health check
/usr/local/bin/nexvision-health
```

---

## 11. Scaling Cheat-Sheet

| Bottleneck           | Solution                                                      |
|----------------------|---------------------------------------------------------------|
| CPU (Gunicorn)       | Increase `workers` in `gunicorn.conf.py` (formula: 2×CPU+1)  |
| Concurrent streams   | Add more gevent workers; Nginx handles the file serving       |
| Database I/O         | Upgrade RDS/CloudSQL tier; enable read replicas               |
| Cache miss rate      | Increase Redis memory; tune `CACHE_DEFAULT_TIMEOUT`           |
| VOD transcoding      | Offload `ffmpeg` to a dedicated worker VM / Batch service     |
| Static asset latency | Put CloudFront / Cloud CDN / Azure Front Door in front        |
| Global reach         | Multi-region deployment with GeoDNS (Route 53 / Traffic Mgr) |

### Gunicorn worker tuning

```python
# app/gunicorn.conf.py  — key settings
import multiprocessing

workers     = multiprocessing.cpu_count() * 2 + 1
worker_class = "gevent"
worker_connections = 1000   # per worker, gevent handles concurrency
timeout      = 120
keepalive    = 5
```

---

## Quick Reference: Platform Comparison

| Feature              | Standalone     | DigitalOcean      | AWS                  | Azure                | GCP                  |
|----------------------|----------------|-------------------|----------------------|----------------------|----------------------|
| Managed MySQL        | Self-host       | DO Managed DB     | RDS Multi-AZ         | Flexible Server      | Cloud SQL HA         |
| Managed Redis        | Self-host       | DO Managed Redis  | ElastiCache          | Azure Cache          | Memorystore HA       |
| Object Storage       | Local disk      | Spaces (S3 compat)| S3 + CloudFront      | Blob + Front Door    | GCS + Cloud CDN      |
| Secret management    | `.env` (600)   | `.env` (600)      | Secrets Manager      | Key Vault            | Secret Manager       |
| Auto-scaling         | Manual          | Manual / DOKS     | ASG + ALB            | VMSS + App GW        | MIG + GLB            |
| WAF                  | fail2ban/nginx  | Cloud Firewall    | AWS WAF + Shield     | Defender + Armor     | Cloud Armor          |
| Monthly cost (small) | $50–200 hw     | ~$50–120          | ~$120–300            | ~$100–250            | ~$100–250            |
| Best for             | Hotel/on-prem  | Startups, simplicity | Enterprise, global | MS-heavy orgs     | Analytics, global LB |
