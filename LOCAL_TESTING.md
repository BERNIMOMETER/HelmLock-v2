# Offline Local Testing

This mode runs the kiosk without Supabase, Stripe credentials, an Arduino, or
any serial device. Flask remains the web server.

```bash
cp .env.local.example .env.local
docker compose -f docker-compose.local.yml up --build -d
docker compose -f docker-compose.local.yml ps
```

Open `http://localhost:5000` and verify:

```bash
curl http://localhost:5000/healthz
curl http://localhost:5000/api/lockers
```

Local rentals complete immediately and return a PIN. The selected locker is
stored in `./data/helmlock.sqlite3`, so active rentals survive a restart.
The mock NFC UID is `DEMO-NFC-001`. A new mock card is provisioned with the
rental balance automatically for testing.

Stop the local stack with:

```bash
docker compose -f docker-compose.local.yml down
```

The normal `docker-compose.yml` remains the RPi hardware deployment and still
passes through the configured USB serial device.
