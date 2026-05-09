# Mukando — Deployment Checklist

Before going live, run through every item below.

## 1. Environment variables
- [ ] `SECRET_KEY` is set to a long random value (never the dev placeholder)
- [ ] `DEBUG=False`
- [ ] `ALLOWED_HOSTS` is set to your actual domain(s)
- [ ] `PAYNOW_INTEGRATION_ID` and `PAYNOW_INTEGRATION_KEY` are your **live** keys
- [ ] `PAYNOW_TEST_MODE=False`
- [ ] `.env` is listed in `.gitignore` — confirm it is NOT in your repo

## 2. Database
- [ ] Run `python manage.py migrate` after every deployment
- [ ] Back up `db.sqlite3` regularly (or switch to PostgreSQL for multi-server setups)

## 3. Static files
- [ ] Run `python manage.py collectstatic --noinput`

## 4. Security headers
- [ ] `settings.py` enables HSTS, SSL redirect, and secure cookies when `DEBUG=False`

## 5. Tests
- [ ] Run `pytest` — all tests pass

## 6. PayNow webhook
- [ ] The `/paynow/result/` URL is registered as the result URL in your PayNow portal
- [ ] Consider IP-allowlisting PayNow's server IPs at your reverse-proxy (nginx/Caddy)

## 7. Rate limiting
- [ ] DRF throttle rates are set appropriately for your expected traffic
- [ ] AI chat endpoint is limited to 20 requests/day per user
