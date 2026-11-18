/* Android arm64, no libc/NDK dependency.
 * Usage: zram-loop-direct-io-arm64 /dev/block/loopN
 * Matches Android 14 fs_mgr EnableDirectIo: 4096-byte block size, then direct I/O.
 * Exit: 0 on success, Linux errno on syscall failure, 64 on invalid argc.
 * Build: aarch64-linux-gnu-as -o /tmp/zram-loop.o tools/zram-loop-direct-io-arm64.S
 *        aarch64-linux-gnu-ld -static -z max-page-size=4096 -e _start \
 *          -o app/src/main/resources/zram-loop-direct-io-arm64 /tmp/zram-loop.o
 */
.global _start
.section .text
_start:
    ldr x0, [sp]
    cmp x0, #2
    b.ne usage
    ldr x1, [sp, #16]    // argv[1]
    mov x0, #-100       // AT_FDCWD
    mov x2, #2          // O_RDWR
    mov x3, #0
    mov x8, #56         // openat
    svc #0
    cmp x0, #0
    b.lt failed
    mov x19, x0
    mov x1, #0x4c09     // LOOP_SET_BLOCK_SIZE
    mov x2, #4096
    mov x8, #29         // ioctl
    svc #0
    cmp x0, #0
    b.lt failed
    mov x0, x19
    mov x1, #0x4c08     // LOOP_SET_DIRECT_IO
    mov x2, #1
    mov x8, #29
    svc #0
    cmp x0, #0
    b.lt failed
    mov x0, #0
    b exit
failed:
    neg x0, x0          // expose errno in shell exit status
    b exit
usage:
    mov x0, #64
exit:
    mov x8, #93         // exit (also closes fd)
    svc #0
