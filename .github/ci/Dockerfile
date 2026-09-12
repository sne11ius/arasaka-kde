FROM debian:trixie-slim@sha256:d7e12182ce18b85b93007c1dedf31f2d29e01ccf3182cc4017c709b6259bc132

# Test dependencies, not full-desktop or PLM deployment prerequisites.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential ca-certificates cmake curl dbus-bin dbus-daemon ffmpeg \
        gcovr git jq libgl1-mesa-dri libglx-mesa0 libkf6config-bin \
        libqt6opengl6-dev librsvg2-bin ninja-build nodejs patch \
        python3 python3-coverage python3-pil qt6-base-dev qt6-declarative-dev \
        xauth xvfb \
    && rm -rf /var/lib/apt/lists/* \
    && command -v kreadconfig6 kwriteconfig6 rsvg-convert node c++ cmake dbus-run-session ffmpeg ffprobe

# The showcase download regressions exercise the real resumable transfer tool.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends aria2 \
    && rm -rf /var/lib/apt/lists/*

# D-Bus requires a passwd entry for the UID used by docker run. Match the
# checkout owner on both local machines and GitHub's UID-1001 hosted runner.
ARG TEST_UID=1000
ARG TEST_GID=1000
RUN if ! getent group "$TEST_GID" >/dev/null; then groupadd --gid "$TEST_GID" builder; fi \
    && useradd --create-home --uid "$TEST_UID" --gid "$TEST_GID" builder \
    && install -d -m 1777 /tmp/opencode /tmp/arasaka-ci-home /workspace

# The artwork uses Rajdhani. Install its actual font instead of testing a
# distribution-dependent sans-serif fallback. Keep the upstream OFL in the image.
ADD --checksum=sha256:94bbd25a18ca665999feb05a537de9fd2b860dcfb78bbe9ca00270825bf235da --chmod=644 \
    https://raw.githubusercontent.com/google/fonts/9d1ce2fc3c335cca32b6db00c19f55d57b0a68fe/ofl/rajdhani/Rajdhani-SemiBold.ttf \
    /usr/local/share/fonts/rajdhani/Rajdhani-SemiBold.ttf
ADD --checksum=sha256:f62ef357d3a1c3d27edd35a6e1ba350e8a8d13499797964eeadefbf0b3b15d1f --chmod=644 \
    https://raw.githubusercontent.com/google/fonts/9d1ce2fc3c335cca32b6db00c19f55d57b0a68fe/ofl/rajdhani/OFL.txt \
    /usr/share/doc/arasaka-ci/Rajdhani-OFL.txt
RUN fc-cache -f \
    && fc-match -f '%{family}: %{file}\n' Rajdhani \
    && test "$(fc-match -f '%{file}' Rajdhani)" = /usr/local/share/fonts/rajdhani/Rajdhani-SemiBold.ttf

ENV HOME=/tmp/arasaka-ci-home
WORKDIR /workspace
USER builder
CMD ["make", "test"]
