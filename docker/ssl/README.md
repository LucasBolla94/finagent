# SSL Certificates

This folder is mounted into Nginx as `/etc/nginx/ssl/`.

Nginx expects two files here:
- `fullchain.pem` — your certificate + chain
- `privkey.pem` — your private key

---

## Option A — Let's Encrypt (production, recommended)

Run this **once** on your server to get a real certificate:

```bash
# Install certbot
sudo apt install certbot -y

# Get certificate (HTTP challenge — server must be reachable on port 80)
sudo certbot certonly --standalone \
  --preferred-challenges http \
  -d yourdomain.com \
  -d www.yourdomain.com \
  --agree-tos \
  --email your@email.com

# Copy to docker/ssl/
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ./fullchain.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ./privkey.pem
sudo chmod 644 fullchain.pem privkey.pem
```

Then update `nginx.conf` line:
```nginx
server_name yourdomain.com www.yourdomain.com;
```

### Auto-renewal

Add this cron job to renew automatically every 60 days:

```bash
# Edit crontab
crontab -e

# Add this line:
0 3 * * * certbot renew --quiet && cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem /path/to/finagent/docker/ssl/fullchain.pem && cp /etc/letsencrypt/live/yourdomain.com/privkey.pem /path/to/finagent/docker/ssl/privkey.pem && docker exec finagent_nginx nginx -s reload
```

---

## Option B — Self-signed (testing only, shows browser warning)

Run this to generate a temporary self-signed cert:

```bash
cd docker/ssl/

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout privkey.pem \
  -out fullchain.pem \
  -subj "/C=BR/ST=SP/L=SaoPaulo/O=FinAgent/OU=Dev/CN=localhost"

chmod 644 fullchain.pem privkey.pem
```

This lets you run `docker compose up` and test HTTPS without a domain.
The browser will show a "not secure" warning — that's expected.

---

## Option C — HTTP only (no SSL, fastest for local testing)

If you just want to test locally without any SSL, edit `nginx.conf`
to remove the HTTPS server block and keep only the HTTP block.
Change the redirect to serve content directly instead.

Or simply skip Nginx entirely and connect directly:
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`
