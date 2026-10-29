#!/usr/bin/env bash
# Build scanwise-agent binaries into agent/dist/. Requires Go 1.22+. No cgo, no external modules.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
VERSION="${VERSION:-$(git describe --tags --always --dirty 2>/dev/null || echo dev)}"
mkdir -p dist
gofmt -l . | (! grep .) || { echo "gofmt needed"; exit 1; }
go vet ./...
GOOS=windows go vet ./...
go test -count=1 ./...
for target in linux/amd64 linux/arm64 windows/amd64; do
    os="${target%/*}"; arch="${target#*/}"
    out="dist/scanwise-agent-${os}-${arch}"
    [ "$os" = windows ] && out="$out.exe"
    CGO_ENABLED=0 GOOS="$os" GOARCH="$arch" go build -trimpath -ldflags "-s -w -X main.version=$VERSION" -o "$out" .
    echo "built $out"
done
