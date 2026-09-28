# VIOP / Hisse hesaplayıcı

TradeLABtr içine gömülen statik Next.js arayüzü.

- `out/` FastAPI tarafından `/calc` altında servis edilir (`?tab=viop|hisse&embed=1`)
- `api-server.mjs` hacim / volatilite / hype sıralaması için `/api/screener` üretir

Yeniden derleme:

```bash
npm install
CALC_BASE_PATH=/calc npm run build
```
