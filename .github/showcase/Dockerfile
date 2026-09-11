FROM debian:trixie-slim@sha256:d7e12182ce18b85b93007c1dedf31f2d29e01ccf3182cc4017c709b6259bc132

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        qemu-system-x86 qemu-system-gui qemu-utils ffmpeg xvfb xauth \
        python3 python3-pil openssh-client genisoimage xdotool x11-utils \
        curl ca-certificates openssl git openbox \
    && rm -rf /var/lib/apt/lists/*

ARG SHOWCASE_UID=1000
ARG SHOWCASE_GID=1000
RUN if ! getent group "$SHOWCASE_GID" >/dev/null; then groupadd --gid "$SHOWCASE_GID" recorder; fi \
    && useradd --create-home --uid "$SHOWCASE_UID" --gid "$SHOWCASE_GID" recorder \
    && install -d -m 1777 /tmp/.X11-unix

ENV HOME=/home/recorder PYTHONDONTWRITEBYTECODE=1
WORKDIR /src
USER recorder
ENTRYPOINT ["python3", "-m", "scripts.showcase.runner"]
