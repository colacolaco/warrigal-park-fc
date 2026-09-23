# Deployment and configuration guide

## 1. Deployment model

The application is a single Python process that serves its own HTTP responses and
stores its data in SQLite. There is no application server, no container runtime
requirement, and no third-party package to install. Deployment is therefore:

```
copy the repository  →  set the environment variables  →  start the process
```

Three environments are defined. They differ **only** in environment variables;
the source code is identical, which is the point of externalising configuration.

| Environment | Purpose | Database | Seeding | Debug logging |
| --- | --- | --- | --- | --- |
| `development` | the registrar's laptop | `data/warrigal_park.db` | on | off |
| `test` | automated tests and CI | `data/test.db` (or `:memory:`) | on | off |
| `production` | the club's shared machine | a path outside the repository | **off** | off |

## 2. Configuration reference

| Variable | Default | Notes |
| --- | --- | --- |
| `APP_ENV` | `development` | one of `development`, `test`, `production`; an unknown value stops start-up |
| `APP_HOST` | `127.0.0.1` | `0.0.0.0` to accept connections from other machines |
| `APP_PORT` | `5000` | |
| `APP_DB_PATH` | `data/warrigal_park.db` | relative paths resolve against the project root |
| `DATABASE_URL` | empty | optional; overrides `APP_DB_PATH` when set |
| `APP_SEED` | `true` | load the fictitious sample roster on first start |
| `APP_DEBUG` | `false` | verbose request logging |
| `APP_SECRET_KEY` | a development placeholder | **must** be replaced in production |

### Precedence

A setting is resolved in this order, first match wins:

1. a real environment variable,
2. a value in the `.env` file in the project root,
3. the built-in default in `config.py`.

### Files in `config/`

| File | Version controlled | Use |
| --- | --- | --- |
| `env.example` | **yes** | the template; every setting is documented here with a safe default |
| `env.development` | yes | convenience values for a local machine |
| `env.test` | yes | values used by the test suite and CI |
| `env.production` | yes | production shape, with secrets left as placeholders |

Copy the template to `.env` and edit it:

```bash
cp config/env.example .env
```

`.env` is listed in `.gitignore` and must never be committed.

## 3. Starting the application

### Development

```bash
python run.py
```

```
====================================================================
  Warrigal Park FC - Member Registration & Team Roster System
  env=development host=127.0.0.1 port=5000 db=.../data/warrigal_park.db seed=True debug=False config-source=environment/.env
  Open this address in a browser:  http://127.0.0.1:5000/
  Press Ctrl+C to stop the server.
====================================================================
```

### Production

```bash
APP_ENV=production \
APP_HOST=0.0.0.0 \
APP_PORT=8080 \
APP_DB_PATH=/var/lib/warrigal-park/warrigal_park.db \
APP_SEED=false \
APP_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
python wsgi.py
```

On Windows (PowerShell):

```powershell
$env:APP_ENV="production"
$env:APP_HOST="0.0.0.0"
$env:APP_PORT="8080"
$env:APP_DB_PATH="C:\ProgramData\WarrigalPark\warrigal_park.db"
$env:APP_SEED="false"
python wsgi.py
```

### As a managed service

`deploy/warrigal-park.service` is a systemd unit:

```bash
sudo cp deploy/warrigal-park.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now warrigal-park
sudo systemctl status warrigal-park
```

`deploy/Procfile` covers platform-as-a-service hosts that read one.

### Container

```bash
docker build -f deploy/Dockerfile -t warrigal-park-fc .
docker run --rm -p 8080:8080 \
  -e APP_ENV=production -e APP_HOST=0.0.0.0 -e APP_PORT=8080 \
  -e APP_SEED=false \
  -v warrigal-data:/data \
  warrigal-park-fc
```

## 4. Deployment checklist

- [ ] `APP_ENV=production` and `APP_SEED=false`, so the fictitious sample roster
      is never loaded over real club data.
- [ ] `APP_SECRET_KEY` replaced with a freshly generated value.
- [ ] `APP_DB_PATH` points outside the repository, on a volume that is backed up.
- [ ] The data directory is writable by the account running the process.
- [ ] The health endpoint answers:
      `curl -fsS http://127.0.0.1:8080/api/health`
- [ ] `python -m unittest discover -s tests -t .` passes on the deployed commit.
- [ ] The deployed commit is tagged and the tag is pushed.

## 5. Health check

```bash
curl -s http://127.0.0.1:5000/api/health
```

```json
{
  "status": "ok",
  "environment": "development",
  "database": "warrigal_park.db",
  "schema_version": "1.2.0",
  "members": 15,
  "rules": [
    "Members under 18 require a linked guardian to complete registration ..."
  ]
}
```

The endpoint reports the schema version, so a deployment that has not run its
migration is visible immediately.

## 6. Backup and restore

The whole state is one SQLite file.

```bash
# stop the service first so the file is not being written
sudo systemctl stop warrigal-park
cp /var/lib/warrigal-park/warrigal_park.db \
   /var/backups/warrigal_park-$(date +%F).db
sudo systemctl start warrigal-park
```

Restore by stopping the service, replacing the file, and starting it again. The
schema migration runs automatically on start-up if the restored file is older
than the current code.

## 7. Upgrade

```bash
git fetch --tags
git switch main
git pull --ff-only
git switch -c deploy/v1.4.0 v1.4.0     # deploy a tag, never a moving branch
python -m unittest discover -s tests -t .
# stop the service, take a backup, start the service on the new commit
```

The migration in `models/database.py` is applied on the first query after
start-up. Migrations are additive, so rolling back means redeploying the previous
tag; the database file does not need to change.

## 8. Known limitations of this deployment

1. SQLite is a single-writer database. It is appropriate for the club's volume
   (a few hundred registrations a year, a handful of concurrent users) and not
   appropriate beyond that. `DATABASE_URL` exists so that the persistence layer
   can be moved to a client-server database without changing the services.
2. The built-in HTTP server is single-process. It is not designed to be exposed
   directly to the public internet; put it behind a reverse proxy, or restrict
   access to the club's network.
3. There is no login screen. Access control is out of scope for this release and
   is recorded as future work in the project report; until it is implemented the
   application must not be published beyond the club's own network.
