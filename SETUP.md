# Mukando — Local Development Setup Guide

Complete step-by-step instructions for running the Mukando stokvel management
system locally with **PayNow Zimbabwe payment integration in test mode**.

---

## 1. Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.8 + | https://python.org |
| pip | latest | bundled with Python |
| git | any | https://git-scm.com |
| ngrok (optional) | any | https://ngrok.com — only needed for PayNow webhook testing |

---

## 2. Clone / Extract the Project

If you received this as a zip file, extract it:

```bash
unzip mukando_output.zip -d mukando
cd mukando
```

Or if using git:

```bash
git clone <repo-url> mukando
cd mukando
```

---

## 3. Create a Python Virtual Environment

```bash
# Create the venv
python -m venv venv

# Activate it
# macOS / Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt.

---

## 4. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs Django, Django REST Framework, the **PayNow Python SDK**
(`paynow==1.0.8`), and all other dependencies.

---

## 5. Configure Environment Variables

The project ships with a ready-to-use `.env` file that contains
**PayNow's official test credentials** (no real money is charged):

```
PAYNOW_INTEGRATION_ID  = 13
PAYNOW_INTEGRATION_KEY = 7b60a7fc-3a7c-4187-a2e4-3c4d47de38d7
PAYNOW_TEST_MODE       = True
```

If the `.env` file is not present, copy the example:

```bash
cp .env.example .env
```

The `.env` file is read automatically via `os.environ.get()` in `settings.py`.
No additional setup is needed for local development.

---

## 6. Load Environment Variables

Django reads from environment variables — tell your shell to load `.env`:

```bash
# macOS / Linux (bash/zsh):
export $(grep -v '^#' .env | xargs)

# Windows PowerShell:
Get-Content .env | Where-Object { $_ -notmatch '^#' -and $_ -ne '' } |
  ForEach-Object { $k, $v = $_ -split '=', 2; [System.Environment]::SetEnvironmentVariable($k, $v) }
```

Alternatively, install `python-dotenv` and add it to `manage.py`
or use `python-decouple` (already in requirements) by replacing
`os.environ.get(...)` calls with `config(...)` from `decouple`.

---

## 7. Run Database Migrations

```bash
python manage.py migrate
```

This creates `db.sqlite3` with all tables including `paynow_transactions`.

---

## 8. Create a Superuser (Admin Account)

```bash
python manage.py createsuperuser
```

Follow the prompts. You'll use these credentials to log in.

---

## 9. (Optional) Seed Demo Data

```bash
python manage.py seed_demo_data
```

This creates sample groups, members and contributions so you can test
PayNow immediately without clicking through the whole UI.

---

## 10. Start the Development Server

```bash
python manage.py runserver
```

Open your browser: **http://127.0.0.1:8000**

---

## 11. Test the PayNow Payment Flow

### Step A — Log in and find an unpaid contribution

1. Go to http://127.0.0.1:8000/login/
2. Log in with your superuser credentials.
3. Navigate to a group → find a member with an **Unpaid** contribution.
4. Click **Pay with PayNow** next to any unpaid contribution.

### Step B — Payment initiation page (`/pay/<contribution-id>/`)

The page shows:
- Contribution amount and due date
- Accepted payment methods (EcoCash, OneMoney, ZIPIT, Visa/MC)
- A yellow **"Test Mode Active"** banner confirming no real money moves
- A green **"Proceed to PayNow"** button

Click the button. This calls `initiate_payment()` in `paynow_service.py`,
creates a `PayNowTransaction` record with `status='sent'`, and redirects
you to PayNow's hosted checkout page.

### Step C — Complete payment on PayNow sandbox

On the PayNow page, choose any payment method and use test values:
- **EcoCash test phone**: `0771111111`
- **Card test number**: `4111 1111 1111 1111` / any future expiry / CVV `123`
- **OTP/PIN**: use `1234` or whatever the sandbox accepts

After completing payment, PayNow will:
1. Redirect your browser to `/paynow/return/?status=paid&reference=MKD-XXXXXXXX`
2. POST a server-side webhook to `/paynow/result/`

### Step D — Return page (`/paynow/return/`)

The return page polls `/paynow/status/<contribution-id>/` every 4 seconds.
Once payment is confirmed it shows ✅ **"Payment Successful!"** and
the contribution status in your database changes to `paid`.

---

## 12. Testing the Webhook Locally (ngrok)

PayNow needs a **publicly reachable** URL to POST the result notification.
During local development use ngrok to expose your local server:

```bash
# Install ngrok: https://ngrok.com/download
# Then in a second terminal:
ngrok http 8000
```

Copy the `https://xxxx.ngrok.io` URL. The views automatically build
absolute URLs using `request.build_absolute_uri()`, so as long as Django
receives requests through ngrok the webhook URL will be correct.

> **Tip:** You can also simulate the webhook manually with curl:
>
> ```bash
> curl -X POST http://127.0.0.1:8000/paynow/result/ \
>   -d "reference=MKD-TESTREF1&status=paid&paynowreference=ZWL123456789&hash=<computed>"
> ```
> The hash check will fail on a fake request — which proves the security
> is working correctly.

---

## 13. Key Files Reference

| File | Purpose |
|------|---------|
| `rounds/paynow_service.py` | PayNow SDK wrapper — `initiate_payment()`, `check_payment_status()`, `verify_result_notification()` |
| `rounds/views.py` | Django views: `paynow_pay_view`, `paynow_return_view`, `paynow_result_view`, `paynow_status_view` |
| `rounds/models.py` | `PayNowTransaction` model — stores every payment attempt |
| `rounds/urls.py` | URL routing for all PayNow endpoints |
| `mukando_project/settings.py` | `PAYNOW_INTEGRATION_ID`, `PAYNOW_INTEGRATION_KEY`, `PAYNOW_TEST_MODE` |
| `.env` | Environment variable values (never commit this file) |
| `requirements.txt` | Python dependencies including `paynow==1.0.8` |

---

## 14. PayNow URL Endpoints

| URL | Method | Description |
|-----|--------|-------------|
| `/pay/<contribution-id>/` | GET, POST | Initiation page — starts a payment |
| `/paynow/return/` | GET | Browser redirect after PayNow checkout |
| `/paynow/result/` | POST | Webhook — PayNow notifies payment status |
| `/paynow/status/<contribution-id>/` | GET | AJAX polling endpoint (JSON response) |

---

## 15. Going Live (Production Checklist)

When you're ready to accept real payments:

1. Register at https://www.paynow.co.zw/account/integration/browse
2. Create an integration and copy your **live** Integration ID and Key.
3. Update `.env`:
   ```
   PAYNOW_INTEGRATION_ID=<your-live-id>
   PAYNOW_INTEGRATION_KEY=<your-live-key>
   PAYNOW_TEST_MODE=False
   ```
4. Set `DEBUG=False` and configure a proper `SECRET_KEY`.
5. Deploy behind HTTPS (PayNow requires HTTPS for the result URL).
6. Use a production database (PostgreSQL recommended).

---

## 16. Troubleshooting

**"PayNow credentials not configured"**  
→ Make sure you've exported `.env` variables into your shell (Step 6).

**Payment initiates but no webhook arrives**  
→ PayNow can't reach `localhost`. Set up ngrok (Step 12).

**"HASH_MISMATCH" in logs**  
→ The `PAYNOW_INTEGRATION_KEY` in settings doesn't match what PayNow used
   to sign the notification. Double-check your credentials.

**Migration errors**  
→ Run `python manage.py migrate --run-syncdb` or delete `db.sqlite3` and
   re-run migrations for a clean slate.

**`ModuleNotFoundError: No module named 'paynow'`**  
→ Your virtual environment is not activated, or you haven't run
   `pip install -r requirements.txt`.
