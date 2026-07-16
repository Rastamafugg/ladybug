# Ladybug retro-dev web app — full-stack container.
#
# Bundles the 6809 toolchain (lwtools), the patched XRoar emulator
# (xroar-monitor, built from a pinned project-fork commit), the FastAPI
# backend, and a headless X stack
# (Xvfb + x11vnc + noVNC) so the emulator GUI is viewable in a browser.
#
# Build context MUST be the repo root:
#   docker build -f web/docker/Dockerfile -t ladybug-web .
# (docker-compose.yml in this directory sets the context correctly.)

# ---------------------------------------------------------------------------
# Stage 1 — builder: compile lwtools + xroar-monitor from source.
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS builder

ARG LWTOOLS_VERSION=4.24
ARG LWTOOLS_URL=https://www.lwtools.ca/releases/lwtools/lwtools-${LWTOOLS_VERSION}.tar.gz
ARG LWTOOLS_SHA256=b38a2baad15c017bb7cd8144218e7af61abccf21fd25f7b1a35e6529acd7b3dd

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        ca-certificates \
        wget \
        git \
        autoconf \
        automake \
        libtool \
        libtext-iconv-perl \
        libsdl2-dev \
    && rm -rf /var/lib/apt/lists/*

# --- lwtools (lwasm/lwlink) ------------------------------------------------
# lwtools ships a plain Makefile (no autoconf). Build the binaries and copy
# them out; skip the docs target (it would pull in texinfo).
WORKDIR /src
RUN wget -q "${LWTOOLS_URL}" -O lwtools.tar.gz \
    && echo "${LWTOOLS_SHA256}  lwtools.tar.gz" | sha256sum -c - \
    && tar xzf lwtools.tar.gz \
    && mv lwtools-${LWTOOLS_VERSION} lwtools \
    && make -C lwtools \
    && cp lwtools/lwasm/lwasm lwtools/lwlink/lwlink \
          lwtools/lwar/lwar lwtools/lwlink/lwobjdump /usr/local/bin/

# --- xroar-monitor ---------------------------------------------------------
# Source of truth: the project's monitor-enabled XRoar fork. The
# ladybug/monitor branch carries the -monitor JSON-RPC extension (vendored
# cJSON, --enable-monitor) plus the M6b SIGPIPE fix (a client disconnect no
# longer kills XRoar). Build the SDL2 UI only (no GTK), audio disabled (no
# sound device in the container — XRoar uses its null audio module).
#
# Build notes learned the hard way:
#   * configure/Makefile.in are NOT committed — run autoreconf -fi first.
#   * win2rc needs Text::Iconv (libtext-iconv-perl) to emit windows32 rsrc.
#   * the top-level `make` also builds docs (needs makeinfo); build only
#     portalib + src to get the binary without the texinfo dependency.
ARG XROAR_REPO=https://github.com/Rastamafugg/monitor-xroar.git
ARG XROAR_COMMIT=7787ad937b15102bf8cb8eb81b92e29f5ba7169d
RUN git init /src/xroar \
    && cd /src/xroar \
    && git remote add origin "${XROAR_REPO}" \
    && git fetch --depth 1 origin "${XROAR_COMMIT}" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "${XROAR_COMMIT}"
WORKDIR /src/xroar
RUN autoreconf -fi \
    && ./configure \
        --enable-monitor \
        --without-gtk3 --without-gtk2 --without-gtkgl \
        --without-sdl3 --with-sdl2 \
        --without-alsa --without-pulse --without-oss --without-jack \
        --without-sndfile \
    && make -C portalib -j"$(nproc)" \
    && make -C src -j"$(nproc)" \
    && cp src/xroar /usr/local/bin/xroar-monitor

# ---------------------------------------------------------------------------
# Stage 2 — runtime.
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        bash \
        libsdl2-2.0-0 \
        libgl1 \
        xvfb \
        x11vnc \
        novnc \
        websockify \
        fluxbox \
        supervisor \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Toolchain + emulator from the builder stage.
COPY --from=builder /usr/local/bin/lwasm /usr/local/bin/lwlink \
                    /usr/local/bin/lwar /usr/local/bin/lwobjdump \
                    /usr/local/bin/xroar-monitor /usr/local/bin/

# Python deps (cached layer — copy requirements first).
COPY web/requirements.txt /app/web/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages \
        -r /app/web/requirements.txt

# Application + repo tree (backend operates on the whole repo).
WORKDIR /app
COPY . /app

# Backend resolves the emulator via XROAR_BIN; point it at the installed
# binary so it does not look for the host-built docs/reference/xroar tree.
ENV XROAR_BIN=/usr/local/bin/xroar-monitor \
    DISPLAY=:99 \
    HOME=/root \
    LADYBUG_WEB_HOST=0.0.0.0 \
    LADYBUG_WEB_PORT=8765 \
    SDL_AUDIODRIVER=dummy

# XRoar searches $HOME/.xroar for system ROMs; the compose file mounts the
# host's coco3.rom / extbas11.rom there.
RUN mkdir -p /root/.xroar

COPY web/docker/supervisord.conf /etc/supervisor/conf.d/ladybug.conf
COPY web/docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# 8765 = FastAPI web app, 6080 = noVNC (browser view of the emulator).
EXPOSE 8765 6080

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]
