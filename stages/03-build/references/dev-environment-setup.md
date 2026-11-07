# Dev Environment Setup (Windows 11)

What this is: a Linux environment (Ubuntu in WSL2) with Docker Engine installed inside
it, so the stack runs the same on your machine as in CI and production. About 30
minutes, one restart. Needs admin rights for step 1.

Decision 2026-11-07: Docker Engine inside Ubuntu, not Docker Desktop (same
`docker compose`, about a quarter of the disk space, no Windows app).

Checked 2026-11-07: WSL2 is enabled with no Linux distribution; no Docker or `make`;
C: drive had 0.6 to 8.6 GB free.

## 0. Make room (target: 15 GB free on C:)

Total setup needs about 5 GB, and Linux and Docker fail in confusing ways on a full
drive. Free space first:

1. Run **Disk Cleanup** (`cleanmgr` in the Start menu), choose C:, click
   "Clean up system files", tick Temporary files and Windows Update Cleanup.
   Untick Downloads.
2. Empty the Recycle Bin after checking nothing in it is needed (this is permanent).

Check, in PowerShell:

```powershell
Get-PSDrive C
```

Pass: Free (GB) is 15 or more (10 is the bare minimum).

## 1. Install Ubuntu (WSL2)

In PowerShell **as Administrator**:

```powershell
wsl --install -d Ubuntu-24.04
```

Restart when asked. Ubuntu opens and asks for a Linux username and password (only for
Ubuntu; pick anything you will remember, you need the password for `sudo`).

Check, in PowerShell:

```powershell
wsl -l -v
```

Pass: `Ubuntu-24.04` listed with VERSION 2.

## 2. Install Docker Engine inside Ubuntu

In the Ubuntu terminal (from Docker's official apt repository):

```bash
sudo apt update && sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

Close the Ubuntu window, open it again (so the group change applies), then check:

```bash
docker run --rm hello-world
docker compose version
```

Pass: "Hello from Docker!" and a Compose version (v2 or later).

If `docker` says it cannot connect to the daemon, start it with
`sudo service docker start`. On current WSL, Ubuntu runs systemd by default and Docker
starts on its own.

## 3. Tools inside Ubuntu

```bash
sudo apt install -y make git gh
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL
uv python install 3.12
```

Check:

```bash
make --version && git --version && gh --version && uv --version && uv python find 3.12
```

Pass: all five print a version or path.

## 4. Get the project into Ubuntu

Work from the Linux file system (much faster than `/mnt/c`):

```bash
gh auth login                      # GitHub.com, HTTPS, log in with a browser
gh auth setup-git
git config --global user.name udomekem
git config --global user.email emmysudoms@gmail.com
mkdir -p ~/code && cd ~/code
gh repo clone udomekem/recruit-agent
cd recruit-agent
cp /mnt/c/Users/emmys/Projects/recruit-agent/product/.env product/.env
```

The `.env` file holds your keys and is not in git, so it is copied by hand.

From then on, `~/code/recruit-agent` in Ubuntu is the working copy. The Windows
folder can be deleted once everything is pushed.

## 5. Open it in Claude Code

In the desktop app, open the folder
`\\wsl$\Ubuntu-24.04\home\<your-linux-username>\code\recruit-agent`,
or install Claude Code inside Ubuntu and run `claude` from that folder.

Then say "continue phase 0".

## How the workspace uses this

`make up` starts API, worker, Postgres and Redis with Docker Compose; `make test`,
`make lint`, `make eval` and `make smoke` run inside Ubuntu. CI runs the same targets
on GitHub's Ubuntu runners.
