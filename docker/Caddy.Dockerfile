# Official stable Caddy source, patched official Go toolchain and x/net.
FROM --platform=$BUILDPLATFORM caddy:2.11.7-builder-alpine@sha256:aa705b1e8e4bce41a7a30de934c1e00f6821667c1d1206424465065c92cb7674 AS builder
ARG TARGETOS
ARG TARGETARCH
ENV GOTOOLCHAIN=go1.26.9 GOMAXPROCS=2 CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH
RUN xcaddy build v2.11.7 --replace golang.org/x/net=golang.org/x/net@v0.60.0
FROM caddy:2.11.7-alpine@sha256:173b26306d711395accaeba8b67afcaad2a085ccb1e6bf26010bfe8c095a5229
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
# Keep certificate/config volume format and official startup command.
# Run on unprivileged internal ports; production host ports map to these.
RUN apk add --no-cache zlib=1.3.2-r1 \
    && setcap -r /usr/bin/caddy \
    && addgroup -g 10001 -S caddy && adduser -u 10001 -G caddy -S -D -H caddy \
    && chown -R caddy:caddy /data /config
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:2019/config/"]
