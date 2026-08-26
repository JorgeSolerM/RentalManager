# Public site behind Cloudflare Tunnel

The public ASGI application is served locally and Cloudflare Tunnel is the
only public ingress:

```text
https://hsi-rents.com -> cloudflared -> http://127.0.0.1:8001
```

Configure the process environment before starting Uvicorn:

```text
PUBLIC_SITE_BASE_URL=https://hsi-rents.com
PUBLIC_SITE_ALLOWED_HOSTS=hsi-rents.com,www.hsi-rents.com
PUBLIC_SITE_NAME=HSI Rents
FORWARDED_ALLOW_IPS=127.0.0.1
```

Start the public application with proxy handling restricted to the local
Cloudflare connector:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.public_main:app `
  --host 127.0.0.1 --port 8001 `
  --proxy-headers --forwarded-allow-ips 127.0.0.1
```

Do not use `0.0.0.0`, a wildcard trusted host, or a public firewall/router
port. The administrative application on port 8000 is not included in the
public ASGI application.
