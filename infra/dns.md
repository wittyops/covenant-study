# DNS — Covenant Study

## Internal (Technitium — split-horizon at 10.10.10.10)

| Zone | Type | Name | Value | Notes |
|------|------|------|-------|-------|
| wittycomp.com | A | study | 10.10.30.246 | Points directly to wn-bible-01 macvlan IP |

## External (Cloudflare)

| Type | Name | Value | Proxied |
|------|------|-------|---------|
| CNAME | study | \<CF tunnel domain\> | ✓ |

## Cloudflare Tunnel Ingress (wn-tunnel-01)

Add to the tunnel's ingress rules in `wn-tunnel-01/config.yaml`:

```yaml
- hostname: study.wittycomp.com
  service: https://10.10.30.5:443
  originRequest:
    originServerName: study.wittycomp.com
    noTLSVerify: false
```

`originServerName` is required when the service is `https://` — it sets the SNI header
so Caddy can route to the correct virtual host.

## Container Network

| Field | Value |
|-------|-------|
| Container | `wn-bible-01` |
| Network | `witty_vlan30` (macvlan) |
| IP | `10.10.30.246` |
| Port | `8000` (uvicorn) |
| Caddy proxy target | `10.10.30.246:8000` |
