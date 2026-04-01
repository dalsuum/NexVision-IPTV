# NexVision VOD Storage: Quick Decision Guide

## At a Glance: Which Storage Should You Use?

### Use Cases Mapped to Recommendations

```
┌─────────────────────────────────────────────────────────────┐
│ YOUR SITUATION                    │ RECOMMENDED             │
├─────────────────────────────────────────────────────────────┤
│ Single hotel, <50 guests          │ ✅ LOCAL DISK          │
│                                   │    Safe, simple, free  │
├─────────────────────────────────────────────────────────────┤
│ 5-20 hotels, on-premise only      │ ✅ NAS                 │
│                                   │    Reliable, fast, HA  │
├─────────────────────────────────────────────────────────────┤
│ 50+ hotels worldwide              │ ✅ CLOUD (S3/Azure)    │
│                                   │    Global, scalable    │
├─────────────────────────────────────────────────────────────┤
│ Need data residency (GDPR/etc)    │ ✅ HYBRID (NAS + S3)   │
│                                   │    On-prem + archive   │
├─────────────────────────────────────────────────────────────┤
│ Want all flexibility              │ ✅ MULTI-BACKEND       │
│                                   │    (storage_backends.py)│
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Comparison Table

| Feature | Local | NAS | S3 | Azure | GCS |
|---------|:----:|:---:|:--:|:-----:|:---:|
| **Setup Time (mins)** | 5 | 30 | 60 | 60 | 60 |
| **Max Concurrent Users** | 100 | 500 | 100k+ | 100k+ | 100k+ |
| **Data Egress Cost** | Free | Free | $0.085/GB | $0.08/GB | $0.02/GB |
| **HA/Redundancy** | ❌ None | RAID-6 | Built-in | Built-in | Built-in |
| **Failover Time** | Hours | Minutes | Auto | Auto | Auto |
| **Latency** | <1ms | <5ms | 100ms | 100ms | 80ms |
| **Suitable For** | Dev | Hotels | Enterprise | Enterprise | Enterprise |
| **Provider Lock-in** | None | Hardware | AWS | Azure | Google |
| **Monthly Cost (10TB)** | $0 | $200 | $1,500 | $1,200 | $900 |


---

## Decision Flowchart

```
START
  ↓
[How many concurrent users?]
  ├─ <100 → [LOCAL or NAS]?
  │         ├─ Single location? → LOCAL ✓
  │         └─ Multiple locations? → NAS ✓
  │
  ├─ 100-1000 → [NAS + Backup]?
  │              ├─ New deployments? → Start with NAS ✓
  │              └─ Existing VHS? → Keep local, add NAS mirror ✓
  │
  └─ >1000 → [CLOUD or HYBRID]?
              ├─ Global distribution? → S3 or GCS ✓
              ├─ Within single region? → Azure or S3 ✓
              └─ Need on-prem compliance? → NAS + S3 Archive ✓
```

---

## Cost Calculator

### Scenario 1: Single Hotel (50 guests, 100 videos)

```
LOCAL DISK STORAGE:
├─ Videos: 100 × 2GB = 200GB
├─ HLS segments: 200GB × 3 (360p+480p+720p) = 600GB  
├─ Thumbnails: 100 × 0.5MB = 50MB
├─ Total: ~850GB (1TB disk needed)
├─ Hardware: 1x 10TB NAS ≈ $500 (one-time)
└─ Monthly cost: ~$0 (power/cooling = $30)
```

### Scenario 2: Medium Chain (10 hotels, 500 videos each = 5,000 videos)

```
NAS + BACKUP:
├─ Primary NAS: 5,000 videos × 2GB × 3 qualities = 30TB
├─ Hardware (QNAP TS-432 with 48TB): $10,000
├─ Backup disk (2TB USB): $100
├─ Network upgrade (10GbE): $2,000
├─ Monthly: Electricity $100, Support $50
└─ Total Year 1: $12,250 CAPEX + $1,800 OPEX = $14,050

S3 + CLOUDFRONT (Alternative):
├─ Storage: 30TB × $0.023/GB = $690/month
├─ Data transfer: 2TB/day × 30 × $0.085/GB = $5,100/month
├─ CloudFront: 60TB/month × $0.085/GB = $5,100/month
└─ Total: ~$10,890/month = $130,680/year
```

**Verdict:** NAS wins for <10,000 concurrent viewers; Cloud wins above.

---

### Scenario 3: Broadcast Network (100 hotels, 1M videos)

```
HYBRID ARCHITECTURE:
├─ Hot Storage (NAS + File Servers): 100TB
│  ├─ 2x QNAP TS-932PX (48TB each) = $20,000
│  └─ Monthly: $300
│
├─ Warm Storage (S3 Standard):
│  ├─ 100TB × $0.023/GB = $2,300/month
│  └─ Transfer to CloudFront: $4,250/month
│
├─ Cold Archive (S3 Glacier):
│  ├─ 900TB × $0.004/GB (archive tier) = $3,600/month
│  └─ Retrieval: 2TB/month × $0.02 = $40/month
│
└─ Total:
   ├─ Year 1: $20,000 CAPEX + $137,000 OPEX = $157,000
   ├─ Year 2+: $125,000/year OPEX
   └─ Supports: 100k+ concurrent viewers globally
```

---

## Implementation Roadmap

### Phase 1: Current State (Today)
```
✓ Local disk storage (/opt/nexvision/vod_data/)
✓ Works for: Single server deployment (~100 users)
✓ Cost: $0/month
```

### Phase 2: Add HA (Week 1)
```
+---- NAS Mount
|     ├─ Hardware: QNAP TS-432 ($4,000)
|     ├─ Setup: 2 hours
|     ├─ Daily rsync backup to File Server
|     └─ Supports: 500 concurrent users
├─ Cost: $4,000 CAPEX + $50/month
```

### Phase 3: Add Cloud Archive (Month 1)
```
+---- S3 Glacier for videos >90 days old
|     ├─ Cost: $0.004/GB (90% cheaper than Hot)
|     ├─ Automatic via Lambda/Celery
|     └─ Supports: Unlimited long-term storage
├─ Cost: ~$300/month for 100TB
```

### Phase 4: Scale Distribution (Month 3)
```
+---- CloudFront CDN
|     ├─ Origin: S3 or NAS
|     ├─ 200+ edge locations
|     └─ Supports: 100k+ concurrent viewers
├─ Cost: $0.085/GB
```

### Phase 5: Full Redundancy (Month 6)
```
+---- Multi-region replication
|     ├─ Primary: us-east-1
|     ├─ Secondary: eu-west-1
|     └─ Disaster recovery: S3 Cross-Region Replication
├─ Cost: +$200/month
```

---

## Recommended Architectures by Scale

### 🏨 Hotel/Small Business (1-50 rooms)

```
Hotel Network
    ↓ (WiFi/LAN)
NexVision Server (1U rack)
    ├─ Local SSD (boot)
    ├─ 10TB HDD (videos)
    ├─ Nginx (HTTP + caching)
    └─ Flask + FFmpeg
    ↓ (Nightly backup)
USB Drive (in safe)
```

**Cost:** $2,000 hardware + $30/month power
**Setup:** 3 days
**Support:** 1 person part-time

---

### 🌟 Hotel Chain (5-50 hotels)

```
                    Central Server (NAS)
                    ├─ 24TB RAID-6
                    ├─ Nginx reverse proxy
                    └─ Flask API
                          ↑ (iSCSI)
           ┌──────────────┼──────────────┐
        Hotel 1        Hotel 2        Hotel 3
     (cached copy)  (cached copy)  (cached copy)
        8TB           8TB            8TB
```

**Cost:** $15,000 hardware + $200/month
**Setup:** 1 week
**Support:** 1 full-time DevOps

---

### 🌍 Global Broadcast (100+ hotels)

```
Content Center
    ↓ (ingest)
S3 Upload Queue
    ↓ (trigger)
Lambda Farm ──transcode──→ S3 Output
                          ↓
                     CloudFront CDN
                     (200+ edge nodes)
                          ↓
                    ┌─────┴─────┬...
              Hotel 1      Hotel 2
             (direct CDN) (direct CDN)
```

**Cost:** $5,000/month + 2 full-time engineers
**Setup:** 2-3 weeks
**Support:** 24/7 on-call

---

## 🚀 Quick Start Commands

### For LOCAL (no changes needed)
```bash
# Already configured
python3 app.py
```

### For NAS
```bash
# 1. Mount NAS
sudo mount -t nfs 192.168.1.10:/vod /mnt/nas/vod

# 2. Update .env
echo "STORAGE_BACKEND=nas" >> .env
echo "VOD_DATA_DIR=/mnt/nas/vod" >> .env

# 3. Copy data
rsync -avz vod_data/* /mnt/nas/vod/

# 4. Restart
python3 app.py
```

### For S3
```bash
# 1. Create S3 bucket + CloudFront in AWS Console

# 2. Install boto3
pip install boto3

# 3. Configure .env
cat >> .env << EOF
STORAGE_BACKEND=s3
AWS_REGION=us-east-1
AWS_ACCESS_KEY=AKIA...
AWS_SECRET_KEY=...
S3_BUCKET_HLS=nexvision-hls
CLOUDFRONT_URL=https://d123.cloudfront.net
EOF

# 4. Test
curl http://localhost:5000/api/admin/storage/info

# 5. Restart
python3 app.py
```

### For Azure
```bash
# 1. Create Storage Account + CDN in Azure Portal

# 2. Install SDK
pip install azure-storage-blob

# 3. Configure .env
cat >> .env << EOF
STORAGE_BACKEND=azure
AZURE_STORAGE_ACCOUNT=mystgaccount
AZURE_STORAGE_KEY=...
AZURE_CDN_URL=https://mycdn.azureedge.net
EOF

# 4. Test & restart
curl http://localhost:5000/api/admin/storage/info
python3 app.py
```

---

## 💡 Pro Tips

1. **Start Local, Add NAS Later**
   - Local disk costs ~$0/month
   - NAS adds ~$200/month but gives HA
   - Upgrade when you hit 2TB limit

2. **Cloud for Scale, Not Speed**
   - Cloud excellent for 100k+ users
   - But 100ms latency vs <5ms local
   - Use CDN to mitigate

3. **Backup Everything**
   - NAS: Daily rsync to offline disk
   - Cloud: Enable versioning + cross-region replica
   - Test restore: Every 30 days

4. **Monitor Costs**
   - S3 surprises: Data egress (largest cost)
   - Use S3 Glacier for old videos
   - CloudFront caching reduces bandwidth

5. **Plan for Failure**
   - NAS fails: 4-hour RTO with backup
   - S3 fails: <15min RTO (multi-region)
   - Test failover quarterly

---

## 📞 Support Decision Tree

**Problem: Storage filling up**
```
├─ Local disk? → Add external USB drive
├─ NAS? → Add larger drives, expand RAID
└─ Cloud? → Enable Smart Tiering (auto-archive)
```

**Problem: Slow playback**
```
├─ <100 users? → Increase Nginx cache
├─ <1000 users? → Upgrade NAS network to 10GbE
└─ >1000 users? → Enable CDN (CloudFront/Azure CDN)
```

**Problem: Video not found**
```
├─ Local? → Check /vod_data/hls/{id}/
├─ NAS? → Check mount: mount | grep vod
└─ Cloud? → Check S3 bucket permissions
```

**Problem: Cost too high**
```
├─ S3? → Enable Glacier tier for videos >30 days
├─ CloudFront? → Reduce TTL or add CloudFlare
└─ Both? → Use Cloudflare on top of CloudFront (cheaper)
```

---

## References

- **Full Architecture Guide:** [VOD-Storage-Architecture.md](VOD-Storage-Architecture.md)
- **Integration Code:** [storage_backends.py](../storage_backends.py)
- **Deployment Guide:** [STORAGE-INTEGRATION-GUIDE.md](STORAGE-INTEGRATION-GUIDE.md)
- **AWS S3:** https://aws.amazon.com/s3/
- **Azure Blob:** https://azure.microsoft.com/services/storage/blobs/
- **Google Cloud Storage:** https://cloud.google.com/storage
- **QNAP NAS:** https://www.qnap.com/
- **MinIO:** https://min.io/ (S3-compatible)

---

**Ready to implement?** → Start with [STORAGE-INTEGRATION-GUIDE.md](STORAGE-INTEGRATION-GUIDE.md)
