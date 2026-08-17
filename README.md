# ChurchTools <-> Nextcloud Group Sync

A simple Python script to automatically synchronize ChurchTools groups and roles to Nextcloud when using the **Social Login (OAuth2)** app.

---

## 📌 Background & Motivation

### The Problem with Social Login & Mobile Apps
When setting up ChurchTools login for Nextcloud via OAuth2 (following the [ChurchTools Academy Guide](https://churchtools.academy/de/help/system-einstellungen/oauth-login-systemeinstellungen/oauth-login-via-churchtools-bei-nextcloud)) and the Nextcloud [Social Login App](https://apps.nextcloud.com/apps/sociallogin), there is one practical limitation:
- Group memberships are **only updated when a user logs in via the web browser**.
- Most people in our church use the **Nextcloud Mobile App** or **Desktop Client** with persistent login tokens.
- When someone is added to a new group in ChurchTools (like tech team, worship, small groups), they won't see the corresponding Nextcloud folders because they rarely log in through the browser again.

### Alternative: ChurchTools Nextcloud Integration App
There is an official [ChurchTools Integration App](https://apps.nextcloud.com/apps/churchtools_integration) for Nextcloud as an alternative to Social Login, which also syncs groups. However, I preferred sticking with the well-supported [Social Login App](https://apps.nextcloud.com/apps/sociallogin) and missed a few features in the integration app.

### 💡 The Solution
I built this small sync tool for our church to run in the background (e.g. as a scheduled task in [Dokploy](https://docs.dokploy.com/docs/core/schedule-jobs) or via cron). It reads all users from Nextcloud and ChurchTools, compares the groups, and adds/removes the appropriate Nextcloud groups via the Nextcloud Provisioning API. Maybe it's useful for other churches facing the same issue!

---

## ✨ Features

- **Fast & Async**: Loads users in parallel using `nc-py-api` (`AsyncNextcloud`).
- **Group & Role Claims**:
  - `groups`: `<Prefix><GroupName>` (e.g. `ChurchTools-Leadership`)
  - `roles`: `<Prefix><GroupName>_<RoleName>` (e.g. `ChurchTools-Leadership_Leader`)
- **Auto-Creates Missing Groups**: If a ChurchTools group doesn't exist in Nextcloud yet, it will be created automatically.
- **Safe Prefix Handling**: Only touches groups starting with your prefix (e.g. `ChurchTools-`). Internal groups like `admin` remain untouched.
- **Dry-Run Mode**: Defaults to preview mode (`--dry-run`) so you can check what would change before applying it.
- **Docker & Dokploy Ready**: Simple Docker container that stays idle, ready for scheduled cron tasks.

---

## ⚙️ Configuration & Prefix Explanation

### Understanding `NC_GROUP_PREFIX`
In Nextcloud's [Social Login App](https://apps.nextcloud.com/apps/sociallogin) settings (under *Settings -> Social Login -> Custom OAuth2*), you define an **Internal name** for ChurchTools (e.g. `ChurchTools` or `churchtools`):
- Nextcloud automatically prefixes all groups imported via OAuth with `<Internal-Name>-` (e.g. `ChurchTools-Gemeindeleitung`).
- Set `NC_GROUP_PREFIX` in your `.env` to match this exact prefix (e.g. `NC_GROUP_PREFIX=ChurchTools-`).
- This ensures the sync script matches the exact groups Social Login created, while leaving native Nextcloud groups (like `admin`) safe and untouched.

## 🔒 Permissions & Authentication Requirements

### 1. ChurchTools Permissions (`CT_LOGIN_TOKEN`)
- The user account generating the `CT_LOGIN_TOKEN` must have **administrative permissions** in ChurchTools (specifically permission to view all persons and all groups).
- ChurchTools filters API responses based on the permissions of the authenticated user. If a regular member's token is used, only persons and groups visible to that user will be returned, leading to incomplete synchronization.
- **Tip:** For details on how login tokens work, see the [ChurchTools API Authentication Guide](https://churchtools.academy/de/help/system-einstellungen/api/api-authentifizierung/). You can generate a Login Token in ChurchTools under your user profile settings or via the API.

### 2. Nextcloud Permissions & Sudo Mode (`NC_PASSWORD`)

> [!WARNING]
> **Do not use an App Password / App Token for `NC_PASSWORD`!**

#### Why? "403 Password confirmation is required"
Nextcloud has a security mechanism called **Sudo Mode** (`@PasswordConfirmationRequired`) for sensitive administrative actions, such as adding or removing users from groups.
- Nextcloud **deliberately blocks App Passwords / Tokens** from performing sudo-confirmed Provisioning API calls.
- If you use an App Token, Nextcloud will respond with: `[403] Password confirmation is required`.

#### Recommended Nextcloud Setup:
1. Create a dedicated local user in Nextcloud (e.g. `sync-bot` or `ct-sync`).
2. Add that user to the `admin` group.
3. Use the **actual account password** of this user for `NC_PASSWORD`.
4. *(Optional for self-hosted instances)*: You can disable Sudo Mode in your Nextcloud `config/config.php` by setting `'sudo' => false,`.

---

## 🚀 Setup & Installation

### 1. Clone & Setup Python Environment
```bash
git clone https://github.com/Christen-am-Gueterplatz/churchtools-nextcloud-sync.git
cd churchtools-nextcloud-sync

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure `.env`
Copy [.env.example](file:///.env.example) to `.env`:
```bash
cp .env.example .env
```

Edit your credentials:
```env
# ChurchTools
CT_BASE_URL=https://yourchurch.church.tools
CT_LOGIN_TOKEN=your_churchtools_login_token

# Nextcloud (Use regular admin password, NOT an app token)
NC_BASE_URL=https://cloud.yourchurch.com
NC_USERNAME=nextcloud_admin_user
NC_PASSWORD=nextcloud_admin_actual_password
NC_GROUP_PREFIX=ChurchTools-

# Claim Type: 'groups' (default) or 'roles'
# - groups: e.g. 'ChurchTools-Leadership'
# - roles:  e.g. 'ChurchTools-Leadership_Leader'
NC_GROUPS_CLAIM=groups

# Sync Settings
DRY_RUN=true
REMOVE_EXTRA_GROUPS=true

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=simple
# Optional file logging:
# LOG_FILE=logs/sync.log
```

---

## 💻 Usage

### 1. Preview / Dry-Run (Default)
Simulates what would happen without making any changes in Nextcloud:
```bash
python main.py
# or explicitly:
python main.py --dry-run
```

**Example output:**
```text
============================================================
ChurchTools <-> Nextcloud Group Sync Service
Mode:          DRY-RUN (PREVIEW ONLY)
Group Prefix:  'ChurchTools-'
Claim Type:    'groups'
Remove Extra:  True
============================================================
Retrieved 58 users from Nextcloud. Loading user details...
Finished loading 58 Nextcloud users.
Retrieved 153 persons from ChurchTools. Fetching memberships...
Finished loading ChurchTools memberships for 153 persons.
[DRY-RUN] Jane Doe (ChurchTools-202 <-> CT-ID: 146) -> Missing groups to ADD: ['ChurchTools-Tech Team']
[DRY-RUN] Jane Doe (ChurchTools-202 <-> CT-ID: 146) -> Extra groups to REMOVE: ['ChurchTools-Old Group']
============================================================
SUMMARY:
  Total Nextcloud users:       58
  Matched with ChurchTools:    56
  Unmatched users:             2
  Users with missing groups:   4
  Users with extra groups:     9
  [Dry-Run completed - no changes were applied to Nextcloud]
============================================================
```

### 2. Apply Changes (Active Sync)
```bash
python main.py --sync
```

### 3. Add-Only Mode (Don't Remove Extra Groups)
```bash
python main.py --sync --no-remove-extra
```

### 4. CLI Arguments
```text
usage: main.py [-h] [--sync] [--dry-run] [--remove-extra] [--no-remove-extra]
               [--claim {groups,roles}] [--prefix PREFIX]
               [--log-level {DEBUG,INFO,WARNING,ERROR}]
               [--log-format LOG_FORMAT] [--log-file LOG_FILE]

Options:
  --sync                Apply changes directly to Nextcloud.
  --dry-run             Simulate sync without modifying Nextcloud.
  --remove-extra        Remove prefixed groups if no longer in ChurchTools.
  --no-remove-extra     Keep extra groups (only add missing ones).
  --claim {groups,roles}
                        Claim mode: 'groups' (default) or 'roles'.
  --prefix PREFIX       Nextcloud group prefix (e.g. 'ChurchTools-').
  --log-level LEVEL     Log level: DEBUG, INFO, WARNING, ERROR.
  --log-format FORMAT   Format preset ('simple', 'detailed', 'compact', 'plain') or format string.
  --log-file PATH       Optional path to write a log file.
```

---

## 🐳 Deployment with Docker & Dokploy

The [Dockerfile](file:///Dockerfile) runs the container in idle mode (`tail -f /dev/null`) so that scheduled tasks execute quickly on demand.

### Setting up in Dokploy
1. **Create an Application in Dokploy:**
   - Source: Connect this Git repository.
   - Build Type: **Dockerfile**.
2. **Add Environment Variables:**
   - Put your `.env` values (`CT_BASE_URL`, `CT_LOGIN_TOKEN`, `NC_BASE_URL`, `NC_USERNAME`, `NC_PASSWORD`, etc.) into Dokploy under **Environment**.
3. **Add a Scheduled Job:**
   - Go to your application in Dokploy -> **Schedule / Cron Tasks** (see [Dokploy Schedule Jobs](https://docs.dokploy.com/docs/core/schedule-jobs)).
   - Click **Add Job**:
     - **Command:** `python main.py --sync`
     - **Cron Expression:** `*/5 * * * *` (e.g. every 5 minutes) or `*/30 * * * *` (every 30 minutes).
4. **Deploy**:
   - The container will sit idle and Dokploy will trigger the sync script on your schedule.

---

## 🛠️ Classic Server Deployment (Cron / Systemd)

### Crontab
```cron
*/5 * * * * cd /opt/churchtools-nextcloud-sync && .venv/bin/python main.py --sync
```

### Systemd Timer
1. Service `/etc/systemd/system/ct-nc-sync.service`:
   ```ini
   [Unit]
   Description=ChurchTools to Nextcloud Group Sync
   After=network.target

   [Service]
   Type=oneshot
   User=www-data
   WorkingDirectory=/opt/churchtools-nextcloud-sync
   ExecStart=/opt/churchtools-nextcloud-sync/.venv/bin/python main.py --sync
   ```

2. Timer `/etc/systemd/system/ct-nc-sync.timer`:
   ```ini
   [Unit]
   Description=Run ChurchTools to Nextcloud Group Sync every 5 minutes

   [Timer]
   OnCalendar=*:0/5
   Persistent=true

   [Install]
   WantedBy=timers.target
   ```

3. Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now ct-nc-sync.timer
   ```

---

## 📄 License
MIT License (see [LICENSE](file:///LICENSE)).