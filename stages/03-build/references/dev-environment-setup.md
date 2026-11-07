# Dev Environment Setup (Windows 11)

What this is: a Linux environment (Ubuntu in WSL2) plus Docker, so the stack runs the
same on your machine as in CI. About 30 minutes, one restart. Needs admin rights.

Checked 2026-11-07: WSL2 is enabled but has no Linux distribution; Docker and `make`
are not installed.

## 1. Install Ubuntu (WSL2)

In PowerShell **as Administrator**:

```powershell
wsl --install -d Ubuntu-24.04
```

Restart when asked. Ubuntu opens and asks for a Linux username and password (these
are only for Ubuntu; pick anything you will remember).

Check, in PowerShell:

```powershell
wsl -l -v
```

Pass: `Ubuntu-24.04` listed with VERSION 2.

## 2. Install Docker Desktop

1. Download Docker Desktop for Windows from docker.com and install it.
2. Keep "Use WSL 2 instead of Hyper-V" ticked.
3. Open Docker Desktop: Settings > Resources > WSL integration > turn on
   **Ubuntu-24.04**. Apply and restart Docker.

Check, in the Ubuntu terminal:

```bash
docker run --rm hello-world
docker compose version
```

Pass: "Hello from Docker!" and a Compose version (v2 or later).

## 3. Tools inside Ubuntu

In the Ubuntu terminal:

```bash
sudo apt update && sudo apt install -y make git curl
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL
uv python install 3.12
```

Check:

```bash
make --version && git --version && uv --version && uv python find 3.12
```

Pass: all four print a version or path.

## 4. Get the project into Ubuntu

Work from the Linux file system (much faster than `/mnt/c`):

```bash
mkdir -p ~/code && cd ~/code
git clone https://github.com/udomekem/recruit-agent.git
cd recruit-agent
gh auth login   # or set up a GitHub credential; install gh with: sudo apt install -y gh
```

Then copy your keys file across (it is not in git):

```bash
cp /mnt/c/Users/emmys/Projects/recruit-agent/product/.env product/.env
```

From then on, the Ubuntu copy (`~/code/recruit-agent`) is the working copy. The
Windows folder can be deleted later once everything is pushed.

## 5. Open it in Claude Code

From the Ubuntu terminal in `~/code/recruit-agent`, run `claude`, or in the desktop
app open the folder `\\wsl$\Ubuntu-24.04\home\<you>\code\recruit-agent`.

## How the workspace uses this

`make up` starts the stack with Docker Compose; `make test`, `make lint`, `make eval`
and `make smoke` run inside Ubuntu. CI runs the same targets on GitHub's Ubuntu runners.
