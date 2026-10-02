# Deployment guide (100% free)

This takes the app from this GitHub repository to production using only free services, none of which needs a credit
card. Budget about 30–40 minutes the first time. After that, every `git push` redeploys automatically.

```
 Browser ──HTTPS──▶ Vercel (free)          the user interface       hi-speed-manufacturing.vercel.app
    │
    └────HTTPS──▶ Render (free)            the backend API + ML     hi-speed-backend.onrender.com
                     ├──▶ Neon (free)            database (PostgreSQL, 0.5 GB)
                     └──▶ Backblaze B2 (free)    uploaded workbooks (private bucket, 10 GB, encrypted)
```

| Service | Free allowance | Used for | Card needed |
|---|---|---|---|
| **Vercel** Hobby | Unlimited static hosting | The screens | No |
| **Render** Free web service | 512 MB RAM, 750 h/month | The backend (measured peak: 316 MB) | No |
| **Neon** Free | 0.5 GB PostgreSQL | All records, accounts, settings (your data uses about 13 MB) | No |
| **Backblaze B2** | 10 GB storage | The uploaded Excel workbooks (more than 5 GB) | No |

### Why the backend can't run on Vercel
The backend needs long-running background work (analysing workbooks, ML models), an in-memory cache and gigabytes of
file storage. Vercel only runs short-lived functions with no permanent storage. So Vercel hosts the screens and Render
runs the backend. Because Render's free plan has no permanent disk either, the data lives in Neon (database) and
Backblaze (files). Nothing is lost when the free server sleeps or redeploys.

### What "free" costs you
- **Render Free sleeps after 15 minutes without visits.** The first visit afterwards takes 30–60 seconds while it
  wakes up. The sign-in page shows *"server is waking up"* and retries by itself. To avoid the wait, see step 7
  (optional keep-awake ping).
- Vercel Hobby is meant for non-commercial use. If the business grows, upgrade only that piece (Vercel Pro), or
  follow "Alternative B" below.

---

## Step 1 – Database: Neon (5 minutes)

1. Go to https://neon.tech and **Sign up** (GitHub or Google login is fine).
2. **Create project**:
   - Project name: `hi-speed`
   - Postgres version: default
   - **Region: AWS Asia Pacific (Singapore)**, the same region as the Render server
3. On the project dashboard, click **Connect**, choose *Connection string*, and copy it. It looks like:
   ```
   postgresql://neondb_owner:AbC123...@ep-cool-name-123456.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```
   Keep it somewhere safe. This is your **`DATABASE_URL`**.

## Step 2 – File storage: Backblaze B2 (7 minutes)

1. Go to https://www.backblaze.com/sign-up/cloud-storage and create an account.
2. **B2 Cloud Storage ▸ Buckets ▸ Create a Bucket**:
   - Bucket name: something unique, e.g. `hispeed-ordertrack-files-7x2k` → this is your **`S3_BUCKET`**
   - Files in bucket are: **Private**
   - Default encryption: **Enable**
   - Object lock: disabled
3. On the new bucket's card, copy the **Endpoint**, e.g. `s3.us-east-005.backblazeb2.com`.
   Put `https://` in front → this is your **`S3_ENDPOINT_URL`** (`https://s3.us-east-005.backblazeb2.com`).
4. **Application Keys ▸ Add a New Application Key**:
   - Name: `ordertrack`
   - Allow access to bucket(s): **only the bucket you just made**
   - Type of access: **Read and Write**
   - Click **Create New Key**, then copy both values immediately (they are shown once):
     - `keyID` → **`S3_ACCESS_KEY_ID`**
     - `applicationKey` → **`S3_SECRET_ACCESS_KEY`**

## Step 3 – Backend: Render (10 minutes, mostly waiting)

1. Go to https://render.com and **Sign up with GitHub** using the account that owns the repository (`GS944`).
2. Click **New ▸ Blueprint**, then **Connect** `GS944/Hi-speed-manufacturing`.
   (If it is not listed, click *Configure account* and allow Render to see that repository. Private repositories work.)
3. Render reads `render.yaml` and shows the service **hi-speed-backend** (plan **Free**, region Singapore).
4. It asks for five values. Paste them from steps 1 and 2:

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | Neon connection string |
   | `S3_ENDPOINT_URL` | `https://s3.<region>.backblazeb2.com` |
   | `S3_BUCKET` | your bucket name |
   | `S3_ACCESS_KEY_ID` | Backblaze keyID |
   | `S3_SECRET_ACCESS_KEY` | Backblaze applicationKey |

5. Click **Apply**. The first build takes about 5–8 minutes: it installs packages and pre-trains the ML model.
6. When the service shows **Live**, copy its URL from the top of the page, e.g. `https://hi-speed-backend.onrender.com`.
7. Open `https://hi-speed-backend.onrender.com/api/health`. You should see `"status":"ok","database":true`.
> Everything else (`JWT_SECRET`, `CORS_ORIGINS`, …) was filled in by the blueprint. `CORS_ORIGINS` is already set to
> `https://hi-speed-manufacturing.vercel.app`. If you use another domain, change it there.

## Step 4 – Connect the Vercel frontend (3 minutes)

1. Open https://vercel.com/dashboard and go to **hi-speed-manufacturing ▸ Settings ▸ Environment Variables**.
2. Add a variable:
   - Key: **`VITE_API_URL`**
   - Value: your Render URL, **without** a trailing slash, e.g. `https://hi-speed-backend.onrender.com`
   - Environments: **Production** and **Preview**
3. Click **Save**. Then go to **Deployments**, open the newest one, click **⋯ ▸ Redeploy**, and confirm.
   The address of the backend is built into the screens, so a redeploy is required.

## Step 5 – Create your account and load data

1. Open https://hi-speed-manufacturing.vercel.app. You see the **Sign in** page.
2. Click **Create an account** and choose **any username and password you like** (there are no format rules).
   From now on you sign in with these on every visit. They are stored permanently in the Neon database.
3. You are signed in. Go to **Data Sheets** and upload `annexure 2026 - 2027.xls` and the order sheet. Each one is
   analysed in about 30–90 seconds on the free server.
4. Open **Data Sheets ▸ CLASSIC ▸ Column mapping**. Swap **Unit cost** and **Value of goods** (that sheet's headers
   are reversed), then click **Save mapping**.
5. Colleagues can create their own accounts on the **Create an account** page, or you can add them under
   **Settings ▸ Users ▸ Add user**. Everyone can change their own username and password under
   **Settings ▸ Your account**.
6. **Recommended:** once everyone has an account, go to **Settings ▸ Users** and switch **New sign-ups** off. Otherwise
   anyone who finds the address can create an account and see your order data. Existing users can still sign in, and
   you can turn it back on at any time.

## Step 6 – Updating the app later
```sh
git add -A
git commit -m "Describe the change"
git push
```
Vercel and Render both redeploy automatically. Your data in Neon and Backblaze is untouched.

## Step 7 (optional) – Avoid the wake-up delay
Render Free sleeps after 15 minutes without traffic. A free uptime monitor that visits every 10 minutes keeps it awake
during working hours:
1. https://uptimerobot.com → free account → **Add New Monitor** → *HTTP(s)*
2. URL: `https://<your-backend>.onrender.com/api/health`, interval: **10 minutes**
3. You also get an email if the backend ever goes down.

One always-on service fits inside Render's 750 free hours per month.

---

## Security and data protection

| Protection | How |
|---|---|
| Everything requires sign-in | Every API route except health and sign-in checks a signed, expiring token |
| Passwords | Stored only as bcrypt hashes. Any password is allowed; 5 wrong attempts lock the account (1 → 5 → 15 → 60 min); per-IP rate limiting |
| Sessions | Expire after 10 h. Changing a password, or **Sign out everywhere**, instantly invalidates all other sessions |
| Who can get in | Standard sign-up and sign-in. Switch **New sign-ups** off in Settings ▸ Users once your team has accounts; then only listed users can sign in |
| Files | Private Backblaze bucket, encrypted at rest; only reachable through the signed-in API, never a public link |
| Database | Neon encrypts at rest; TLS required (`sslmode=require`) |
| In transit | HTTPS everywhere (Vercel, Render, Neon, Backblaze), HSTS |
| Browser | Strict Content-Security-Policy (no third-party or inline scripts), framing blocked, no-referrer leakage |
| Search engines | `robots.txt` + `noindex` headers: the app never appears in Google |
| Cross-site access | The API only answers your own frontend's domain (CORS) |
| Accountability | Every sign-in, upload, edit, print and account change is in **Settings ▸ Audit log** |
| Source code | No data, secrets or passwords in the repository; `.gitignore` blocks Excel files, databases and `.env` |

**Keep the GitHub repository private.** It holds no data now, but private is still the right default.

### Backups
- **Neon** keeps a restore window (point-in-time restore) on the free plan: Project ▸ Branches ▸ Restore.
- **Backblaze**: in the bucket settings, set *Lifecycle* to "Keep all versions" so deleted or replaced workbooks can be
  recovered.
- **Yourself**: in the app, each workbook can be downloaded (Data Sheets ▸ ⤓) and every table exported to Excel.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Sign-in page: *"Cannot reach the application server"* for over 2 minutes | `VITE_API_URL` missing or wrong, or the backend failed | Open `<backend>/api/health`. If that works, fix `VITE_API_URL` in Vercel and **Redeploy** |
| Browser console: *blocked by CORS policy* | Your site address is not in `CORS_ORIGINS` | Render ▸ Environment: set `CORS_ORIGINS` to the exact address, e.g. `https://hi-speed-manufacturing.vercel.app` |
| Render log: *Cannot reach the S3 bucket* | Wrong endpoint, bucket name or keys | Re-check the four `S3_…` values (endpoint must start with `https://`) |
| Render log: database connection error | `DATABASE_URL` wrong, or the Neon project was deleted | Copy the connection string again from Neon ▸ Connect |
| *"New sign-ups are turned off"* | Sign-ups were switched off | An existing user adds the account under Settings ▸ Users, or switches sign-ups back on |
| Account locked | 5 wrong passwords | Wait for the lock to expire, or another user clicks **Unlock** under Settings ▸ Users |
| Everyone forgot their password | — | In Neon ▸ SQL Editor run `DELETE FROM users;` (data is kept). The next visitor can create a new account on the Create account page |
| First page after a pause is slow | Free server waking up | Normal, or set up step 7 |

---

## Alternatives

**A. Your own computer or office server (free, data stays on site):** `python run.py` (see README). Share it on the
office network at `http://<pc-ip>:8000`.

**B. Oracle Cloud "Always Free" VM (free, always on, 200 GB disk; needs card verification):** create an Ubuntu VM,
install Docker, then:
```sh
git clone https://github.com/GS944/Hi-speed-manufacturing.git && cd Hi-speed-manufacturing
docker build -t ordertrack .
docker run -d --restart unless-stopped -p 8000:8000 -v ordertrack-data:/data \
  -e CORS_ORIGINS=https://your.domain --name ordertrack ordertrack
```
Put Caddy in front for HTTPS (e.g. with a free DuckDNS name). This uses the built-in SQLite and disk storage, so Neon
and Backblaze are not needed.

**C. Paid but simplest:** Render Starter plus a 10 GB disk (about $9.50 per month). Remove the Neon/Backblaze variables
and set `DATA_DIR=/var/data` with a disk mounted there.
