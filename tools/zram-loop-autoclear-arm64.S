/* Test-only Android arm64 helper: set LO_FLAGS_AUTOCLEAR on an already-bound loop.
 * Build with aarch64-linux-gnu-as and aarch64-linux-gnu-ld -static -z max-page-size=4096.
 * LOOP_GET_STATUS64 preserves all existing properties; only flag bit 4 is added.
 */
.global _start
.section .text
_start:
    ldr x0, [sp]
    cmp x0, #2
    b.ne usage
    ldr x1, [sp, #16]
    sub sp, sp, #256
    mov x0, #-100
    mov x2, #2
    mov x3, #0
    mov x8, #56
    svc #0
    cmp x0, #0
    b.lt failed
    mov x19, x0
    mov x1, #0x4c05
    mov x2, sp
    mov x8, #29
    svc #0
    cmp x0, #0
    b.lt failed
    ldr w3, [sp, #52]
    orr w3, w3, #4
    str w3, [sp, #52]
    mov x0, x19
    mov x1, #0x4c04
    mov x2, sp
    mov x8, #29
    svc #0
    cmp x0, #0
    b.lt failed
    mov x0, #0
    b exit
failed:
    neg x0, x0
    b exit
usage:
    mov x0, #64
exit:
    mov x8, #93
    svc #0
