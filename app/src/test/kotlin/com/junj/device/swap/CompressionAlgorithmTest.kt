package com.junj.device.swap

import kotlin.test.Test
import kotlin.test.assertTrue

/** Guards the invariant behind COMPRESSION_ALGORITHM (pure, no device required). */
class CompressionAlgorithmTest {
    @Test
    fun `compression algorithm is available to both zram and zswap`() {
        // Measured on tokay:
        //   zRAM   comp_algorithm -> lz77eh zstd lz4 lzo-rle lzo
        //   crypto /proc/crypto   -> zstd lz4 lzo-rle lzo deflate
        assertTrue(
            COMPRESSION_ALGORITHM in setOf("zstd", "lz4", "lzo-rle", "lzo"),
            COMPRESSION_ALGORITHM,
        )
    }
}
