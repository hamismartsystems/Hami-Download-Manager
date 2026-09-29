# HDM Activation Server (optional)

This is optional — HDM now runs in FREE_MODE, no activation needed.

If you want to run your own activation server for legacy licenses:
```
node hdm-activate.js
# or inside hamidesigns.shop site:
# app.use('/api/hdm', require('./routes/hdm-activate').router)
```

For FREE EDITION, you don't need this server. `hdm_license.py` has `FREE_MODE=True`.
