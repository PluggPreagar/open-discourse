#!/bin/bash
# One-time bootstrap for a fresh Arch Linux WSL distro to run this project.
# Run once after installing/resetting the distro, then use setup.sh / build.sh as usual.
set -euo pipefail

echo "== Updating package database =="
sudo pacman -Syu --noconfirm

echo "== Build tools + git =="
sudo pacman -S --needed --noconfirm base-devel git

echo "== Python =="
sudo pacman -S --needed --noconfirm python python-pip

echo "== Node.js + Yarn (needed for the database migration step in build.sh) =="
sudo pacman -S --needed --noconfirm nodejs npm
sudo npm install -g yarn

echo "== Postgres client libs (fallback in case psycopg2-binary needs to build) =="
sudo pacman -S --needed --noconfirm postgresql-libs

cat <<'EOF'

Done. Remaining manual steps:
  1. Docker Desktop -> Settings -> Resources -> WSL Integration -> enable this distro.
  2. cd into the project's python/ folder, e.g.:
       cd /mnt/d/_project/202506_InfoPedia/open-discourse/python
  3. bash setup.sh
  4. ./build.sh
EOF
