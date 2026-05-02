# Ms Money

**Ms Money** is a simple, no-nonsense business and store management app built for people who just want to run their business — not wrestle with spreadsheets.

Whether you're selling on one platform or juggling multiple stores, Ms Money helps you see exactly where your money is coming from, where it's going, and who you're paying — all in one place. No accounting degree required.

### What you can do with Ms Money

- **Track your stores** — Add all your shops or sales channels and keep them organised in groups
- **Log income & expenses** — Record transactions manually or import them straight from a CSV file
- **Know your vendors** — Keep tabs on third-party costs like shipping, platform fees, and suppliers
- **Connect your bank** — Import bank statements to see your real cash flow
- **See the big picture** — Charts and summaries so you always know how your business is doing

## Installation

### Prerequisites
- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/yourusername/msmoney.git
cd msmoney/src

# 2. Create and activate a virtual environment
uv venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# 3. Install dependencies
uv pip install -r requirements.txt

# 4. Apply migrations
python manage.py migrate

# 5. Create a superuser (optional)
python manage.py createsuperuser

# 6. Run the development server
python manage.py runserver
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.


