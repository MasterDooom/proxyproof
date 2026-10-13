package com.masterdooom.proxyproof.ble

/**
 * BLE packet codec used by both the organiser advertiser and student scanner.
 *
 * Current prototype format: 6 raw bytes of session tag followed by 8 raw bytes
 * of rotating HMAC token. In Android manufacturer data the platform prepends
 * the 2-byte company identifier. The 0xFFFF identifier is development-only and
 * must be replaced with an appropriate assigned identifier before public release.
 */
object BleProtocol {
    const val DEVELOPMENT_MANUFACTURER_ID: Int = 0xFFFF
    const val SESSION_TAG_BYTES: Int = 6
    const val TOKEN_BYTES: Int = 8
    const val PAYLOAD_BYTES: Int = SESSION_TAG_BYTES + TOKEN_BYTES

    data class Payload(val sessionTag: String, val token: String)

    fun encode(sessionTag: String, token: String): ByteArray {
        val tag = decodeHex(sessionTag, SESSION_TAG_BYTES)
        val tokenBytes = decodeHex(token, TOKEN_BYTES)
        return tag + tokenBytes
    }

    fun decode(bytes: ByteArray?): Payload? {
        if (bytes == null || bytes.size != PAYLOAD_BYTES) return null
        val tag = bytes.copyOfRange(0, SESSION_TAG_BYTES).toHex()
        val token = bytes.copyOfRange(SESSION_TAG_BYTES, PAYLOAD_BYTES).toHex()
        return Payload(sessionTag = tag, token = token)
    }

    private fun decodeHex(value: String, expectedBytes: Int): ByteArray {
        require(value.length == expectedBytes * 2) {
            "Expected ${expectedBytes * 2} hexadecimal characters."
        }
        require(value.all { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }) {
            "Value must be hexadecimal."
        }
        return ByteArray(expectedBytes) { index ->
            value.substring(index * 2, index * 2 + 2).toInt(16).toByte()
        }
    }

    private fun ByteArray.toHex(): String = joinToString(separator = "") {
        "%02x".format(it.toInt() and 0xff)
    }
}
