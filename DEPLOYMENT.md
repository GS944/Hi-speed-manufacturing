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
  wakes up. The sign-in page shows *"server is waking up"* and retries by itself. Step 7 (UptimeRobot) keeps it awake.
- **The free server has a small processor.** Everyday pages answer in well under a second, but analysing an uploaded
  workbook takes about a minute. Completion-date forecasts may appear a little after the rest of the dashboard while
  the model re-trains in the background.
- Vercel Hobby is meant for non-commercial use. If the business grows, upgrade only that piece (Vercel Pro), or
  follow "Alternative B" below.

---

## Step 1 – Database: Neon (5 minutes)

There are two routes to the same free Neon database. If neon.tech tells you to *use the Neon integration in Vercel*
(your Neon account is managed by Vercel), use route B.

### Route A – directly on neon.tech
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

### Route B – through Vercel (Neon integration)
1. On https://vercel.com, open **Storage** (top menu), click **Create Database**, choose **Neon**, and click **Continue**.
2. Accept the terms, then choose **Region: Singapore**, **Plan: Free**, **Database name: `hi-speed`**.
3. **Custom prefix:** leave empty. **Create database branch for deployment:** none/off (the website never uses the
   database). **Environments:** Production only.
4. Open the new database, go to the **.env.local** tab, click **Show secret**, and copy the value after
   `DATABASE_URL=` (without quotes). This is your **`DATABASE_URL`**.

Either the pooled (`-pooler`) or the direct connection string works.

## Step 2 – File storage: Backblaze B2 (7 minutes)

1. Go to https://www.backblaze.com/sign-up/cloud-storage and create an account.
2. **B2 Cloud Storage ▸ Buckets ▸ Create a Bucket**:
   - Bucket name: something unique, e.g. `hispeed-ordertrack-files-7x2k` → this is your **`S3_BUCKET`**
   - Files in bucket are: **Private**
   - Default encryption: **Enable**
   - Object lock: disabled
3. On the new bucket's card, copy the **Endpoint**, e.g. `s3.us-east-005.backblazeb2.com`. This is your
   **`S3_ENDPOINT_URL`**. It works with or without `https://` in front, and the storage region is detected from it.
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
   | `S3_ENDPOINT_URL` | `s3.<region>.backblazeb2.com` (with or without `https://`) |
   | `S3_BUCKET` | your bucket name |
   | `S3_ACCESS_KEY_ID` | Backblaze keyID |
   | `S3_SECRET_ACCESS_KEY` | Backblaze applicationKey |

5. Click **Apply**. The first build takes about 5–8 minutes: it installs packages and pre-trains the ML model.
6. When the service shows **Live**, copy its URL from the top of the page, e.g. `https://hi-speed-backend.onrender.com`.
7. Open `https://hi-speed-backend.onrender.com/api/health`. You should see `"status":"ok","database":true`.
8. **Deploy only tested code:** open **hi-speed-backend ▸ Settings ▸ Build & Deploy ▸ Auto-Deploy** and choose
   **After CI Checks Pass**. Render then waits for the repository's automatic tests (GitHub ▸ Actions ▸ CI) to
   succeed before deploying a push, so a broken change never reaches the live site.

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
Every push runs the automatic checks (**GitHub ▸ Actions ▸ CI**: backend lint and 14 tests, website type-check and
build, about 2 minutes). Vercel redeploys the website, and Render redeploys the backend once the checks pass (step 3.8).
Your data in Neon and Backblaze is untouched. If a check fails, open it in GitHub Actions to see why; nothing is
deployed to Render until it is fixed.

To run the same checks on your own computer first: `python run.py --test` (backend) and `npm --prefix frontend run build`.

## Step 7 (recommended) – Keep it awake with UptimeRobot
Render Free sleeps after 15 minutes without traffic. A free uptime monitor keeps it awake and emails you if it ever
goes down:
1. https://uptimerobot.com ▸ **Register for FREE** ▸ confirm your email.
2. **+ New monitor** ▸ type **HTTP / website monitoring**.
3. URL: `https://<your-backend>.onrender.com/api/health`, interval: **5 minutes** (the free minimum), notify by
   **E-mail** ▸ **Create monitor**. It shows **Up** within a few minutes. (UptimeRobot checks with `HEAD` requests;
   the health endpoint supports both `GET` and `HEAD`.)

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

**The repository can be public**: it contains only code, with no data, passwords or keys. Keep it that way: never
commit workbooks or `.env` files (`.gitignore` blocks them), and keep all secrets in Render / Vercel settings.

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
| Render log: *Cannot reach the S3 bucket* | Wrong endpoint, bucket name or keys | Re-check the four `S3_…` values |
| Render did not deploy a push | The automatic checks failed (step 3.8) | GitHub ▸ Actions ▸ CI shows the failing test or build step |
| UptimeRobot reports *405 Method Not Allowed* | An old backend version without `HEAD` support | Redeploy the latest code (Render ▸ Manual Deploy ▸ Deploy latest commit) |
| Render log: database connection error | `DATABASE_URL` wrong, or the Neon project was deleted | Copy the connection string again from Neon ▸ Connect |
| *"New sign-ups are turned off"* | Sign-ups were switched off | An existing user adds the account under Settings ▸ Users, or switches sign-ups back on |
| Account locked | 5 wrong passwords | Wait for the lock to expire, or another user clicks **Unlock** under Settings ▸ Users |
| Everyone forgot their password | — | In Neon ▸ SQL Editor run `DELETE FROM users;` (data is kept). The next visitor can create a new account on the Create account page |
| First page after a pause is slow | Free server waking up | Set up step 7 (UptimeRobot) |

---

## Alternatives

**A. Your own computer or office server (free, data stays on site):** `python run.py` (see README). Share it on the
office network at `http://<pc-ip>:8000`.

**B. Oracle Cloud "Always Free" VM (much faster: 4 ARM cores / 24 GB; free, but needs card verification and some
server setup):** ready-made files are in `deploy/oracle/` (Docker Compose + Caddy for automatic HTTPS):
1. Create an Ubuntu 24.04 **VM.Standard.A1.Flex** instance (Always Free), open TCP **80** and **443** in its subnet's
   security list, and point a free **DuckDNS** name at its public IP.
2. On the server:
   ```sh
   curl -fsSL https://raw.githubusercontent.com/GS944/Hi-speed-manufacturing/main/deploy/oracle/setup.sh -o setup.sh
   sudo bash setup.sh                                   # installs Docker, opens the firewall, creates the settings file
   sudo nano /opt/ordertrack/deploy/oracle/.env         # DOMAIN + the same values as on Render
   sudo bash setup.sh                                   # builds, starts and gets the HTTPS certificate
   ```
3. Set Vercel's `VITE_API_URL` to `https://<your-name>.duckdns.org` and redeploy. Update later with
   `sudo bash /opt/ordertrack/deploy/oracle/update.sh`.

Oracle may stop Always Free servers that stay idle for 7 days; the data is safe in Neon/Backblaze, so you can just
start the server again (or upgrade the account to Pay-As-You-Go, which stays free within Always Free limits).

**C. Paid but simplest:** Render Starter plus a 10 GB disk (about $9.50 per month), or keep Neon/Backblaze and just
switch the Render plan to Starter for a full processor ($7 per month).

> Hugging Face Spaces was considered too, but since July 2026 Docker Spaces require a paid PRO plan.
