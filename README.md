# Restaurant Management System

A Flask-based restaurant management platform for menu browsing, QR/table ordering, staff order handling, admin operations, loyalty rewards, service requests, and real-time order updates.

## Features

- Customer registration and login.
- Menu browsing by category with item details and stock status.
- Cart and order placement workflow.
- QR/table-oriented ordering support.
- Waiter dashboard for order and service-request handling.
- Admin dashboard for menu, users, services, orders, rewards, campaigns, and analytics.
- Loyalty points, reward redemption, and promotional campaign management.
- File uploads for menu and profile images.
- Real-time updates with Flask-SocketIO.

## Tech Stack

- Python, Flask, Flask-SQLAlchemy, Flask-Login, Flask-Migrate
- Jinja2 templates, Bootstrap-style frontend assets
- SQLite by default, configurable through environment variables
- Flask-SocketIO for real-time behavior

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py
```

On Windows PowerShell:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

Open `http://localhost:5000`.

## Configuration

Important environment variables:

- `SECRET_KEY` - Flask secret key.
- `DATABASE_URL` or `DEV_DATABASE_URL` - database connection string.
- `REDIS_URL` - optional Redis connection for realtime/caching support.
- `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD` - optional mail settings.
- `WHATSAPP_BOT_NUMBER`, `WHATSAPP_API_URL` - optional WhatsApp integration settings.

The default development database is SQLite under the Flask instance folder.

## Database

The application creates database tables on startup. If using migrations:

```bash
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

## Documentation

See `SPECIFICATION.md` for the full system specification, data model overview, and role-based feature breakdown.

## Repository Hygiene

Virtual environments, caches, local databases, and uploaded runtime files should not be committed. Recreate dependencies with `pip install -r requirements.txt`.
