package com.masterdooom.proxyproof.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

object ApiClient {
    suspend fun request(
        baseUrl: String,
        method: String,
        path: String,
        bearerToken: String? = null,
        body: JSONObject? = null
    ): String = withContext(Dispatchers.IO) {
        val normalizedBase = baseUrl.trim().trimEnd('/')
        if (!normalizedBase.startsWith("http://") && !normalizedBase.startsWith("https://")) {
            throw IOException("Server URL must start with http:// or https://")
        }

        val connection = (URL(normalizedBase + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 8_000
            readTimeout = 8_000
            setRequestProperty("Accept", "application/json")
            if (!bearerToken.isNullOrBlank()) {
                setRequestProperty("Authorization", "Bearer $bearerToken")
            }
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }

        try {
            if (body != null) {
                connection.outputStream.use { output ->
                    output.write(body.toString().toByteArray(Charsets.UTF_8))
                }
            }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val response = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                val detail = runCatching {
                    JSONObject(response).optString("detail", response)
                }.getOrDefault(response)
                throw IOException("HTTP $code: $detail")
            }
            response
        } finally {
            connection.disconnect()
        }
    }
}
