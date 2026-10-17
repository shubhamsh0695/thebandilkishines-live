# Bandilki Shines

## Run locally

From the project folder in PowerShell, start the local web server:

```powershell
py -3 server.py
```

Open <http://127.0.0.1:8000/> in a browser. The storefront markup, styles, scripts, and logo are organized under `user\html`, `user\css`, `user\js`, and `user\assets`; do not open the HTML file directly because forms use the server API.

## Project layout

```text
user/
  html/       Storefront pages and HTML fragments
  css/        Storefront stylesheets
  js/         Storefront scripts
  assets/     Storefront logo and static assets
admin/
  html/       Admin dashboard markup
  css/        Admin stylesheets
  js/         Admin scripts
images/       Shared storefront images
server.py     HTTP server and API
schema.sql    SQLite database schema
```

The first run creates `data\bandilki.sqlite3` from `schema.sql` and seeds the product catalog. The database is local and persistent; it stores customer accounts (passwords are salted and hashed), administrator accounts, carts, orders, contact requests, newsletter subscriptions, reviews, product image paths, and storefront branding settings. Uploaded product images are kept separately in `data\product-images\`; the storefront logo and intro video are kept in `data\site-media\`.

The local server binds only to `127.0.0.1` by default. For a container or reverse-proxy host, set `HOST=0.0.0.0`, `PORT` to the port supplied by the host, and `BANDILKI_DATABASE` to a path on persistent storage.

## Admin dashboard

Create an administrator from the project folder. The setup asks for an email and a password (12 or more characters) without echoing the password or storing it in source code:

```powershell
py -3 server.py --create-admin
```

Start the server with `py -3 server.py`, then open <http://127.0.0.1:8000/admin.html>. Admin markup, styles, and scripts are organized under `admin\html`, `admin\css`, and `admin\js`. Sign in with the administrator account to view registered customers, newsletter subscribers, customer reviews, and orders; update order statuses; search an order by number and checkout phone; and manage the shared product catalog, categories and their storefront icons, logo, banner image, intro video, and footer navigation. The storefront banner, average customer rating, review count, and successfully delivered order count update from saved admin/customer data. The storefront header includes working search, account, bag, and mobile navigation controls. Footer links can be renamed, retargeted, added, or removed; their section headings are editable as well. Explore links can also filter the storefront to a selected category. Banner and logo uploads accept JPEG or PNG up to 5 MB; intro videos accept MP4 or WebM up to 25 MB. The opening screen only appears when an intro video is configured. Customers can send reviews with optional contact details and a JPEG/PNG photo up to 5 MB. Renaming a category also updates its products; deleting a category with products requires choosing another category to move those products into.

Stop the server with Ctrl+C.

## Prepare a container deployment

The `Dockerfile` packages the storefront and API without including the local database. Build and run it locally with Docker Desktop:

```powershell
docker build -t bandilki-shines .
docker run --name bandilki-shines -p 8000:8000 -v bandilki-data:/data bandilki-shines
```

Then create the first admin in that container:

```powershell
docker exec -it bandilki-shines python server.py --create-admin
```

For a public deployment, use a host that can build a Dockerfile, provides HTTPS and a public domain, and supports a **persistent volume**. Mount the volume at `/data`; the app saves its SQLite database at `/data/bandilki.sqlite3`, uploaded product images at `/data/product-images/`, and uploaded branding media at `/data/site-media/`. Configure the host to pass its `PORT` and set `HOST=0.0.0.0`. Without persistent storage, customer accounts, orders, and uploaded media can be lost when the host restarts or redeploys. Many free tiers do not provide persistent disks, so verify the provider's current storage and pricing before deploying customer data.

This folder is not connected to a Git remote or hosting account, so no public URL can be provisioned from here yet. A public URL requires publishing this project to a host-supported Git provider or uploading it to a hosting account and completing that provider's deployment setup. Do not upload `data\bandilki.sqlite3` or put administrator credentials in source control.

This built-in Python server is suitable for local development and small early deployments, not high-traffic production. Orders are saved with a `Received` status; payment processing, email delivery, and automated WhatsApp messaging are not configured.
