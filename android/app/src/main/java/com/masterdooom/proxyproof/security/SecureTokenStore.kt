package com.masterdooom.proxyproof.security

import android.content.Context
import android.util.Base64
import java.nio.ByteBuffer
import java.nio.charset.StandardCharsets
import java.security.GeneralSecurityException
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.KeyGenParameterSpec
import javax.crypto.KeyProperties

/**
 * Small AES-GCM token store backed by an Android Keystore key.
 *
 * SharedPreferences contains only a Base64-encoded IV+ciphertext envelope. The
 * AES key is non-exportable in Android Keystore. This protects the bearer token
 * at rest; it is not a replacement for TLS, server revocation or device attestation.
 */
class SecureTokenStore(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(
        "proxyproof_secure_auth",
        Context.MODE_PRIVATE
    )

    @Synchronized
    fun read(): String? {
        val encoded = preferences.getString(KEY_TOKEN, null) ?: return null
        return try {
            val envelope = Base64.decode(encoded, Base64.NO_WRAP)
            if (envelope.size <= 1) throw GeneralSecurityException("Invalid token envelope.")
            val buffer = ByteBuffer.wrap(envelope)
            val ivLength = buffer.get().toInt() and 0xff
            if (ivLength !in 12..16 || buffer.remaining() <= ivLength) {
                throw GeneralSecurityException("Invalid token envelope.")
            }
            val iv = ByteArray(ivLength).also(buffer::get)
            val ciphertext = ByteArray(buffer.remaining()).also(buffer::get)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(128, iv))
            String(cipher.doFinal(ciphertext), StandardCharsets.UTF_8)
        } catch (_: Exception) {
            // If Keystore data was invalidated or corrupted, fail closed and force login.
            preferences.edit().remove(KEY_TOKEN).apply()
            null
        }
    }

    @Synchronized
    fun write(token: String) {
        require(token.isNotBlank()) { "Token cannot be blank." }
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val iv = cipher.iv
        val encrypted = cipher.doFinal(token.toByteArray(StandardCharsets.UTF_8))
        val envelope = ByteBuffer.allocate(1 + iv.size + encrypted.size)
            .put(iv.size.toByte())
            .put(iv)
            .put(encrypted)
            .array()
        preferences.edit().putString(KEY_TOKEN, Base64.encodeToString(envelope, Base64.NO_WRAP)).apply()
    }

    @Synchronized
    fun clear() {
        preferences.edit().remove(KEY_TOKEN).apply()
    }

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setRandomizedEncryptionRequired(true)
                .build()
        )
        return generator.generateKey()
    }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val KEY_ALIAS = "proxyproof.access-token.aes-gcm.v1"
        const val KEY_TOKEN = "access_token_encrypted"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
