#!/system/bin/sh
# Run as root on Android. Creates an isolated zram device; never resets zram0.
set -eu
BACKING=/data/per_boot/rushhour_zram_dio_probe
DATA=/data/local/tmp/rushhour_zram_dio_probe_data
HELPER=/data/local/tmp/rushhour-loop-direct-io
[ ! -e "$BACKING" ] && [ ! -e "$DATA" ] || { echo "Probe paths already exist; refusing overwrite"; exit 1; }
ZID=$(cat /sys/class/zram-control/hot_add)
case "$ZID" in ''|*[!0-9]*|0) echo "Unsafe test zram id: $ZID"; exit 1;; esac
SYS=/sys/block/zram$ZID
DEV=/dev/block/zram$ZID
LOOP=
cleanup() {
    echo 1 > "$SYS/reset" || return
    echo "$ZID" > /sys/class/zram-control/hot_remove || return
    if [ -n "$LOOP" ]; then
        NAME=${LOOP##*/}
        ACTUAL=$(cat /sys/block/$NAME/loop/backing_file)
        [ "$ACTUAL" = "$BACKING" ] || { echo "Unexpected loop file; not removing"; return; }
        losetup -d "$LOOP" || return
    fi
    # Verified fixed probe paths, not existing user files (guard above).
    rm -f /data/per_boot/rushhour_zram_dio_probe /data/local/tmp/rushhour_zram_dio_probe_data
}
trap cleanup EXIT
[ -e "$DEV" ] || { NUM=$(cat "$SYS/dev"); mknod "$DEV" b "${NUM%:*}" "${NUM#*:}" || [ -b "$DEV" ]; }
dd if=/dev/zero of="$BACKING" bs=1M count=32
chmod 600 "$BACKING"
dd if=/dev/urandom of="$DATA" bs=1M count=4
EXPECTED=$(sha256sum "$DATA")
EXPECTED=${EXPECTED%% *}
LOOP=$(losetup -f)
case "$LOOP" in /dev/block/loop[0-9]*|/dev/loop[0-9]*) ;; *) echo "Unexpected loop: $LOOP"; exit 1;; esac
losetup "$LOOP" "$BACKING"
NAME=${LOOP##*/}
run_phase() {
    if [ "$1" = "initialize" ]; then
        echo "$LOOP" > "$SYS/backing_dev"
        echo 33554432 > "$SYS/disksize"
        dd if="$DATA" of="$DEV" bs=4096
        blockdev --flushbufs "$DEV"
    fi
    echo all > "$SYS/idle"
    echo "dio=$(cat /sys/block/$NAME/loop/dio) blocksize=$(cat /sys/block/$NAME/queue/logical_block_size)"
    set +e
    echo idle > "$SYS/writeback"
    RC=$?
    set -e
    echo "writebackExit=$RC bdStat=$(cat "$SYS/bd_stat")"
}
echo "=== buffered control ==="
run_phase initialize
[ "$RC" != 0 ] || echo "NOTE: buffered writeback did not reproduce failure"
# Also verifies repair of an already-attached buffered backing loop.
"$HELPER" "$LOOP"
echo "=== direct IO ==="
run_phase reuse
[ "$RC" = 0 ] || exit 1
WRITES=$(cat "$SYS/bd_stat")
set -- $WRITES
[ "$3" -gt 0 ] || { echo "No backend writes"; exit 1; }
blockdev --flushbufs "$DEV"
ACTUAL=$(dd if="$DEV" bs=4096 count=1024 | sha256sum)
ACTUAL=${ACTUAL%% *}
echo "expectedSHA256=$EXPECTED actualSHA256=$ACTUAL"
[ "$ACTUAL" = "$EXPECTED" ]
echo "readback bdStat=$(cat "$SYS/bd_stat")"
echo "SELinux=$(getenforce) isolated zram$ZID verification PASS"
