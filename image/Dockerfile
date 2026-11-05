FROM debian:trixie
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl xz-utils fdisk e2fsprogs dosfstools util-linux openssl pv \
 && rm -rf /var/lib/apt/lists/*
