# Linux (Ubuntu 24.04) Development Environment Setup

Step-by-step instructions to clone and develop this project on a fresh Ubuntu 24.04 machine.

---

## Prerequisites

You need: **Python 3.12+**, **Docker**, **Docker Compose**, **Make**, **Git**.

---

## Step 1 — System packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git make curl
```

Verify:
```bash
python3 --version   # Should be 3.12+
git --version
make --version
```

---

## Step 2 — Install Docker Engine

Follow the official Docker docs for Ubuntu 24.04:

```bash
# Remove old versions
sudo apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null

# Add Docker's official GPG key and repository
sudo apt install -y ca-certificates gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine + Compose plugin
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add your user to the docker group (avoids sudo for docker commands)
sudo usermod -aG docker $USER
```

**Log out and log back in** for the group change to take effect, then verify:

```bash
docker --version
docker compose version
docker run --rm hello-world
```

---

## Step 3 — Clone the repository

```bash
git clone <YOUR_REPO_URL> Production-Ready-multi-service-deployment-project
cd Production-Ready-multi-service-deployment-project
```

If not using git yet, just copy the project directory to the machine.

---

## Step 4 — Create the virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

Add this to your `~/.bashrc` or `~/.zshrc` if you want auto-activation:
```bash
# Optional: alias to quickly activate
alias activate-task='cd ~/Production-Ready-multi-service-deployment-project && source venv/bin/activate'
```

---

## Step 5 — Install Python dependencies

The only local dependency is Jinja2 (for `orchestrate.py` template rendering).
The API/worker dependencies run inside Docker containers — you don't need them locally.

```bash
pip install jinja2
```

**Optional — install API deps locally for IDE autocompletion and linting:**
```bash
pip install -r api/requirements.txt
pip install -r worker/requirements.txt
```

This gives your IDE (VS Code, PyCharm) access to:
- `fastapi`, `sqlalchemy`, `pydantic`, `redis`, `celery`, `prometheus_client`
- Enables autocomplete, type checking, and inline error detection
- Eliminates the "unresolved import" squiggly lines

---

## Step 6 — Generate all project files

```bash
python3 orchestrate.py generate
```

Expected output:
```
[orchestrate] Writing 29 files...
  api/app.py
  worker/app.py
  ...
[orchestrate] Done — 29 files written.
```

This creates/overwrites all generated files from templates and inline generators.

---

## Step 7 — Verify everything works

```bash
# Check generated API code imports cleanly
cd api && python3 -c "import app" && cd ..

# Check generated worker code imports cleanly
cd worker && python3 -c "import app" && cd ..

# Validate docker-compose.yml
docker compose config --quiet && echo "docker-compose.yml is VALID"
```

---

## Step 8 — IDE setup (VS Code)

### Install VS Code
```bash
sudo snap install code --classic
```

### Recommended extensions
Install these for the best development experience on the template files:

| Extension | ID | Why |
|-----------|-----|-----|
| Python | `ms-python.python` | Syntax highlighting, linting, autocomplete |
| Pylance | `ms-python.vscode-pylance` | Type checking, IntelliSense |
| Docker | `ms-azuretools.vscode-docker` | Dockerfile/compose syntax |
| YAML | `redhat.vscode-yaml` | prometheus.yml, docker-compose |

```bash
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension ms-azuretools.vscode-docker
code --install-extension redhat.vscode-yaml
```

### Point VS Code to the venv

1. Open the project: `code .`
2. `Ctrl+Shift+P` → "Python: Select Interpreter"
3. Choose `./venv/bin/python3`

This tells Pylance where to find installed packages, which eliminates
"unresolved import" warnings for `fastapi`, `sqlalchemy`, etc.

### Workspace settings (optional)

Create `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "./venv/bin/python3",
    "python.analysis.extraPaths": ["./api", "./worker"],
    "python.analysis.typeCheckingMode": "basic",
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true
    },
    "editor.formatOnSave": true,
    "python.formatting.provider": "none",
    "[python]": {
        "editor.defaultFormatter": "ms-python.python"
    }
}
```

The `extraPaths` setting tells Pylance to resolve imports from `api/` and `worker/`
directories, so `from app import ...` in test files resolves correctly.

---

## Step 9 — Start the full stack

```bash
make up
```

This runs `python orchestrate.py up`, which:
1. Regenerates all 29 files
2. Runs `docker compose up -d --build`

First run takes a few minutes (downloads base images, builds containers).

### Verify services are running
```bash
make ps
```

| Service | URL | Purpose |
|---------|-----|---------|
| API | http://localhost:8000 | FastAPI app |
| Nginx | http://localhost:80 | Reverse proxy |
| Grafana | http://localhost:3000 | Dashboards (admin/changeme) |
| Prometheus | http://localhost:9090 | Metrics |
| PostgreSQL | localhost:5432 | Database |
| Redis | localhost:6379 | Cache + broker |

---

## Development workflow

### Edit application code

```bash
# 1. Edit the template file (full IDE support)
code templates/api/app.py

# 2. Regenerate output files
python3 orchestrate.py generate

# 3. Rebuild and restart
make up
```

### Edit config values

```bash
# 1. Edit CONFIG in orchestrate.py Section 1
code orchestrate.py

# 2. Regenerate — new values flow to .env, docker-compose, nginx, etc.
python3 orchestrate.py generate

# 3. Rebuild and restart
make up
```

### Useful commands

```bash
make logs       # Follow all service logs
make shell      # Open a shell in the API container
make test       # Run pytest inside the API container
make migrate    # Run Alembic database migrations
make down       # Stop all containers
make clean      # Stop containers AND delete all data volumes
```

---

## Troubleshooting

### "python: command not found"
Ubuntu 24.04 uses `python3`. The Makefile calls `python orchestrate.py`, so create an alias:
```bash
sudo apt install -y python-is-python3
```
This creates a `python` → `python3` symlink system-wide.

### "docker: permission denied"
You forgot to log out after adding yourself to the `docker` group:
```bash
sudo usermod -aG docker $USER
# Log out and log back in, or:
newgrp docker
```

### "ModuleNotFoundError: No module named 'jinja2'"
You're not in the venv:
```bash
source venv/bin/activate
pip install jinja2
```

### IDE shows "unresolved import" for fastapi/sqlalchemy/etc.
Install the API deps in your local venv:
```bash
source venv/bin/activate
pip install -r api/requirements.txt
```
Then reload VS Code (`Ctrl+Shift+P` → "Developer: Reload Window").

### Docker build fails with network errors
Check your internet connection. If behind a proxy:
```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/proxy.conf <<EOF
[Service]
Environment="HTTP_PROXY=http://proxy:port"
Environment="HTTPS_PROXY=http://proxy:port"
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
```

### Port already in use
```bash
# Find what's using port 8000
sudo lsof -i :8000
# Kill it, or change the port in orchestrate.py CONFIG and regenerate
```
