FROM python:3.12-slim

# Qt/X11 runtime libraries required for PySide6 windows to render, plus
# PulseAudio client library for QMediaPlayer audio playback.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libegl1 \
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-xinerama0 \
    libxcb-xfixes0 \
    libdbus-1-3 \
    libfontconfig1 \
    libfreetype6 \
    libpulse0 \
    fonts-dejavu-core \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Cache and workspace live on different filesystems in the devcontainer,
# so hardlinking isn't possible; copy instead to avoid uv's warning.
ENV UV_LINK_MODE=copy

# Simplify the default root@host:/full/path# prompt down to just the path.
RUN echo 'PS1="\w\$ "' >> /root/.bashrc

WORKDIR /workspace
