git clone <your-repo>
cd nexvision

# Setup environment
cp .env.example .env
nano .env  # Edit with their own values

cp epg/.env.example epg/.env
nano epg/.env

# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run
python app.py