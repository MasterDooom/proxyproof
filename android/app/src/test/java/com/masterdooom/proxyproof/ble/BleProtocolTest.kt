package com.masterdooom.proxyproof.ble

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class BleProtocolTest {
    @Test
    fun encodeDecodeRoundTripPreservesTagAndToken() {
        val tag = "010203a0b0c0"
        val token = "0123456789abcdef"

        val encoded = BleProtocol.encode(tag, token)

        assertEquals(BleProtocol.PAYLOAD_BYTES, encoded.size)
        assertArrayEquals(
            byteArrayOf(
                0x01, 0x02, 0x03, 0xa0.toByte(), 0xb0.toByte(), 0xc0.toByte(),
                0x01, 0x23, 0x45, 0x67, 0x89.toByte(), 0xab.toByte(),
                0xcd.toByte(), 0xef.toByte()
            ),
            encoded
        )
        assertEquals(BleProtocol.Payload(tag, token), BleProtocol.decode(encoded))
    }

    @Test
    fun decoderRejectsNullAndIncorrectLengths() {
        assertNull(BleProtocol.decode(null))
        assertNull(BleProtocol.decode(ByteArray(BleProtocol.PAYLOAD_BYTES - 1)))
        assertNull(BleProtocol.decode(ByteArray(BleProtocol.PAYLOAD_BYTES + 1)))
    }

    @Test(expected = IllegalArgumentException::class)
    fun encoderRejectsIncorrectSessionTagLength() {
        BleProtocol.encode("abcd", "0123456789abcdef")
    }

    @Test(expected = IllegalArgumentException::class)
    fun encoderRejectsNonHexadecimalToken() {
        BleProtocol.encode("010203a0b0c0", "0123456789abcdeg")
    }
}
