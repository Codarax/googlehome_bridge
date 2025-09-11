# HA → Google Home admin UI

Minimal React + Vite frontend that calls the backend admin endpoints:

- GET /admin/devices
- POST /admin/devices/select

Quick start:

1. cd frontend
2. npm install
3. npm run dev  # development with proxy to backend
4. npm run build # build static files in dist/

Deployment:
- Build and copy `dist/` to your Debian server and serve via Nginx or let Flask serve the files.
