# Raspberry Pi 5 Docker Deployment

This deployment builds the Flask service locally on the Raspberry Pi 5 and
passes the Arduino/Mega USB serial device into the container.

## Configure

```bash
git pull
cp .env.example .env
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
nano .env
```

Set `SERIAL_DEVICE` to the detected controller path, usually `/dev/ttyACM0`
or `/dev/ttyUSB0`. Keep `BAUD_RATE=115200`, matching `controller.ino`.
Fill in the Supabase and Stripe test-mode values before starting the service.

## Build and run

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f helmlock
```

The service listens on port 5000. Verify locally and from another LAN device:

```bash
curl http://127.0.0.1:5000/healthz
curl http://<pi-ip>:5000/api/lockers
```

The expected health response is `{"status":"ok"}`. The Compose service uses
one Gunicorn worker because the serial connection is process-local.

## Stripe test mode

Set `BASE_URL` to the URL users can reach. For phone testing from outside the
LAN, use a tunnel such as ngrok. Forward Stripe webhooks to:

```text
http://127.0.0.1:5000/api/stripe-webhook
```

Confirm `STRIPE_WEBHOOK_SECRET` matches the forwarding endpoint.

## Troubleshooting

- Missing device: check the USB cable and run `dmesg | tail -n 30`; update
  `SERIAL_DEVICE` in `.env`, then run `docker compose up -d --force-recreate`.
- Permission denied: add the Pi user to `dialout` with
  `sudo usermod -aG dialout $USER`, log in again, and restart Compose.
- Hardware timeouts: confirm the Arduino is powered, no other process owns the
  port, and the controller is using 115200 baud.
- Stripe does not finalize: verify `BASE_URL`, the webhook secret, and public
  reachability of the webhook endpoint.
- View recent logs with `docker compose logs --tail=200 helmlock`.
