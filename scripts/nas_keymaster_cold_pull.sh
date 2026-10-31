#!/bin/sh
# Optional QNAP TS-433 low-I/O cold JSON mirror: no daemon or task execution.
set -eu
: "${JANUS_COLD_DIR:?Choose an existing private NAS folder}"
case "$JANUS_COLD_DIR" in /*) ;; *) exit 2 ;; esac
[ -d "$JANUS_COLD_DIR" ] || exit 2
command -v curl >/dev/null || exit 2
command -v sha256sum >/dev/null || exit 2
command -v mktemp >/dev/null || exit 2
SOURCE='https://raw.githubusercontent.com/Hawkar-usls/janus-meta-registry/main/data/daddy_keymaster_db'
TMP="$(mktemp -d "${TMPDIR:-/tmp}/janus-cold-XXXXXXXX")"
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

curl --fail --silent --show-error --location --connect-timeout 5 --max-time 20 \
    "$SOURCE/MIRROR.sha256" -o "$TMP/MIRROR.sha256"
[ "$(wc -c < "$TMP/MIRROR.sha256")" -le 128 ] || exit 2
grep -Eq '^[a-f0-9]{64}  MIRROR\.json$' "$TMP/MIRROR.sha256" || exit 2

if [ -f "$JANUS_COLD_DIR/MIRROR.json" ] && [ -f "$JANUS_COLD_DIR/MIRROR.sha256" ]; then
    if cmp -s "$JANUS_COLD_DIR/MIRROR.sha256" "$TMP/MIRROR.sha256"; then
        if (cd "$JANUS_COLD_DIR" && sha256sum -c MIRROR.sha256 >/dev/null 2>&1); then
            echo JANUS_NAS_COLD_MIRROR_NO_CHANGE
            exit 0
        fi
    fi
fi

curl --fail --silent --show-error --location --connect-timeout 5 --max-time 30 \
    "$SOURCE/MIRROR.json" -o "$TMP/MIRROR.json"
[ "$(wc -c < "$TMP/MIRROR.json")" -le 8388608 ] || exit 2
(cd "$TMP" && sha256sum -c MIRROR.sha256 >/dev/null) || {
    echo JANUS_NAS_REMOTE_SHA_MISMATCH >&2
    exit 2
}
[ ! -L "$JANUS_COLD_DIR/MIRROR.json" ] || exit 2
[ ! -L "$JANUS_COLD_DIR/MIRROR.sha256" ] || exit 2
cp "$TMP/MIRROR.json" "$JANUS_COLD_DIR/MIRROR.new"
cp "$TMP/MIRROR.sha256" "$JANUS_COLD_DIR/MIRROR.sha256.new"
mv -f "$JANUS_COLD_DIR/MIRROR.new" "$JANUS_COLD_DIR/MIRROR.json"
mv -f "$JANUS_COLD_DIR/MIRROR.sha256.new" "$JANUS_COLD_DIR/MIRROR.sha256"
(cd "$JANUS_COLD_DIR" && sha256sum -c MIRROR.sha256 >/dev/null) || exit 2
echo JANUS_NAS_COLD_MIRROR_VERIFIED
