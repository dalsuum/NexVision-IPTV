# Security Guidelines for NexVision

## ⚠️ Critical: Before Committing to GitHub

### DO NOT Commit These Files:
- ❌ `.env` - Contains database passwords, API keys, secrets
- ❌ `venv/` - Virtual environment (use `pip install -r requirements.txt` instead)
- ❌ `*.db` - Database files with live data
- ❌ `.env.swp` - Editor swap files
- ❌ `local_backups/` - Local backup files
- ❌ Any files with credentials, tokens, or secrets

### Properly Handled by .gitignore:
- ✅ `.env` files are ignored (use `.env.example` as template)
- ✅ `venv/` directory is ignored
- ✅ Database files (`*.db`) are ignored
- ✅ Log files and temporary files are ignored
- ✅ IDE/editor files are ignored

---

## Setup Instructions for Users

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd nexvision
```

### 2. Create Environment Configuration
```bash
# Copy the example file
cp .env.example .env

# Edit with your actual values (use nano or your editor)
nano .env
```

### 3. Configure EPG Service
```bash
cp epg/.env.example epg/.env
nano epg/.env
```

### 4. Install Dependencies
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install requirements
pip install -r requirements.txt
pip install -r requirements_prod.txt  # For production
```

### 5. Database Setup
```bash
# Initialize SQLite database (auto-created on first run)
python app.py

# Or restore from backup
sqlite3 nexvision.db < backup.sql
```

---

## Environment Variables Reference

### Essential (.env.example provided)
- `FLASK_ENV` - Set to 'production' for deployment
- `SECRET_KEY` - Generate new key: `python -c "import secrets; print(secrets.token_hex(32))"`
- `MYSQL_PASSWORD` - Database password (if using MySQL)
- `VOD_API_KEY` - API key for VOD service

### Database Configuration
```env
USE_MYSQL=0                    # 0=SQLite, 1=MySQL
MYSQL_HOST=localhost
MYSQL_USER=nexvision
MYSQL_PASSWORD=your_password   # CHANGE THIS!
```

### Generate Secure Keys
```bash
# Generate Flask SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# Generate VOD API Key
python -c "import secrets; print(secrets.token_hex(16))"
```

---

## Handling Sensitive Data

### If You Accidentally Committed Secrets:
1. **Immediately rotate the credentials**
2. **Clean git history** (if repo is private):
   ```bash
   git filter-branch --tree-filter \
     'git rm --cached .env vod.db -r' \
     --prune-empty -f HEAD
   git push --force-with-lease origin main
   ```
3. **Add to .gitignore** (already done in this repo)
4. **Regenerate all API keys and passwords**

### Best Practices:
- ✅ Use strong, unique passwords for databases
- ✅ Rotate API keys regularly  
- ✅ Use environment variables for all secrets
- ✅ Never hardcode credentials in code
- ✅ Use `.env.example` files as templates only
- ✅ Keep `.env` in `.gitignore` at all times

---

## Production Deployment

### Before Deploying:
1. **Verify `.gitignore` is complete** - Run `git check-ignore .env vod.db venv/`
2. **Never commit `.env` files** - Use production .env deployment separately
3. **Generate new SECRET_KEY** - Don't reuse development keys
4. **Update database credentials** - Use strong, random passwords
5. **Enable HTTPS** - Always use SSL in production
6. **Restrict file permissions**:
   ```bash
   chmod 600 .env          # Read/write for owner only
   chmod 755 venv/         # Standard directory permissions
   chmod 600 *.db          # Restrict database access
   ```

### Production Environment Setup:
```bash
# Use environment variables instead of .env file (better security)
export FLASK_ENV=production
export SECRET_KEY="your-long-random-key"
export MYSQL_PASSWORD="secure-password"

# Or use .env.production with restricted permissions
chmod 600 .env.production
export $(cat .env.production | xargs)
```

---

## Regular Security Audits

### Check for Accidentally Committed Secrets:
```bash
# Look for common patterns
git log --all --oneline --all | grep -i password
git log --all --oneline --all | grep -i secret
git log --all --oneline --all | grep -i key

# Use git-secrets tool (optional)
npm install -g git-secrets
git secrets --scan
```

### Audit File Permissions:
```bash
ls -la .env .env.* *.db venv/ 2>/dev/null | grep -v 600
# Fix insecure permissions: chmod 600 .env*
```

---

## CI/CD Security

### GitHub Actions Example (.github/workflows/deploy.yml):
```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      # Never store secrets in code - use GitHub Secrets
      - name: Configure Environment
        env:
          FLASK_SECRET_KEY: ${{ secrets.FLASK_SECRET_KEY }}
          MYSQL_PASSWORD: ${{ secrets.MYSQL_PASSWORD }}
        run: |
          # Secrets are injected as environment variables
          pip install -r requirements_prod.txt
          python app.py
```

### Secrets to Add in GitHub (Settings → Secrets):
- `FLASK_SECRET_KEY`
- `MYSQL_PASSWORD`
- `VOD_API_KEY`
- `DATABASE_URL` (if using cloud database)

---

## Compliance Notes

### OWASP Top 10 Considerations:
- **A2: Broken Authentication** - Use strong secrets, rotate regularly
- **A3: Sensitive Data Exposure** - Never commit secrets, use HTTPS, encrypt database
- **A5: Broken Access Control** - Implement proper authentication/authorization
- **A8: Insecure Deserialization** - Update dependencies: `pip list --outdated`

### Dependency Updates:
```bash
# Check for vulnerable packages
pip install safety
safety check

# Update to latest secure versions
pip install --upgrade -r requirements.txt
```

---

## Support & Questions

For security issues:
1. **Do NOT open public issues** for security vulnerabilities
2. **Contact maintainers privately** or use GitHub's security advisory feature
3. **Report to dalsuum08@gmail.com** (if available)

---

---

## Application Security Architecture (v8.21+)

### Authentication & Authorisation
- JWT tokens validated on every admin/protected endpoint via `@admin_required` / `@token_required` decorators
- Roles: `admin` and `operator` (both can manage content); `viewer` has read-only access
- Room clients authenticate with `X-Room-Token` UUID header — no password required (low-privilege)

### API Key Protection (VOD)
- `@require_api_key` decorator checks `X-API-Key` header or `?api_key=` param against `VOD_API_KEY` env var
- VOD upload and admin routes are additionally protected

### Secrets Management
| Secret | Location | Rotation Command |
|---|---|---|
| `SECRET_KEY` | `.env` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `VOD_API_KEY` | `.env` | `python -c "import secrets; print(secrets.token_hex(16))"` |
| `MYSQL_PASSWORD` | `.env` | Change in MySQL + update `.env` |
| `pms_password` | `settings` table | PMS credential — stored in DB; ensure DB file permissions are 660 |

### File Permissions (Production)
```bash
# Verify correct permissions
ls -la /opt/nexvision/.env            # should be 600
ls -la /opt/nexvision/app/*.py        # should be 640
ls -la /opt/nexvision/nexvision.db    # should be 660 (or 640)
```

### Hardened Routes
- All admin CRUD endpoints (`/api/channels`, `/api/rooms`, `/api/packages`, `/api/ads/all`, etc.) require `admin`/`operator` JWT
- `GET /api/ads` (public ad fetch) is intentionally open — returns only active ads, no write capability
- `GET /api/alarms/active` is intentionally open — returns only active alarm schedules (no sensitive data); write endpoints require Admin JWT
- Public endpoints (TV client, settings read, channel list with room token) require `X-Room-Token` for content filtering
- `message_dismissals` and `message_reads` tables use room-scoped tokens — no cross-room leakage

---

**Last Updated:** 2026-05-01 (v8.21)
**Repository:** NexVision  
**Maintainer:** [dalsuum/nexvision]
