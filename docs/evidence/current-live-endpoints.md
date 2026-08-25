# Current Live Endpoint Evidence

| Tested UTC | Endpoint | HTTP status | Final URL after redirects | Authentication/protection observation |
|---|---|---:|---|---|
| 2026-08-16T22:19:20Z | `https://3001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer` | 200 | `https://3001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer/` | Login surface is public; authenticated routes redirected to login before authentication. |
| 2026-08-16T22:19:20Z | `https://8001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer/api/` | 200 | `https://8001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer/api/` | API root is public. |
| 2026-08-16T22:19:20Z | `https://8001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer/api/health` | 200 | `https://8001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer/api/health` | Public health endpoint. Raw response is stored in `current-live-health-response.json`. |
| 2026-08-16T22:19:21Z | `https://8001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer/api/integrations/google/callback` | 307 | `https://8001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer/api/integrations/google/callback` without redirect following | Missing OAuth parameters produced an error redirect, not a successful OAuth callback. |
| 2026-08-16T22:29:19Z | Same Google callback with redirects followed | 200 final | `https://3001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer/registries?tab=integrations&oauth=error` | One redirect followed; this records callback route reachability only, not an OAuth certification. |

## Raw Callback Headers Without OAuth Parameters

```text
HTTP/2 307
location: https://3001-in8v1wws9289jt9pfzcyj-03350434.us4.manus.computer/registries?tab=integrations&oauth=error
```
