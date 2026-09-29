# Uploading the HDM page to hamidesigns.shop

From your PC (SSH key in the workspace: `ssh-hamidesigns/hamidesigns_ed25519_v2`):

```bash
scp -i hamidesigns_ed25519_v2 -P 22022 site/hdm.html root@hamidesigns.shop:/tmp/hdm.html

ssh -i hamidesigns_ed25519_v2 -P 22022 root@hamidesigns.shop
mkdir -p /opt/hamidesigns/public/hdm
cp /tmp/hdm.html /opt/hamidesigns/public/hdm/index.html
pm2 restart hamidesigns
```

Live: https://hamidesigns.shop/hdm/

Files referenced by the page (upload when ready — new filename for every version):
- `https://hamidesigns.shop/uploads/HDM-1.0.0-Setup.exe`
- `https://hamidesigns.shop/uploads/hdm-chrome-extension.zip`
- `https://hamidesigns.shop/uploads/hdm-logo.png` (optional; page hides it if missing)
