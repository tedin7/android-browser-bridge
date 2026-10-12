package net.arvos.browserbridge.companion

import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject

class HttpFailure(val status: Int, val code: String) : Exception("Broker HTTP $status: $code")

object BrokerTransport {
    fun request(origin: String, path: String, body: JSONObject, token: String? = null): JSONObject {
        require(path in setOf("/api/pair", "/api/poll", "/api/result", "/api/native-share"))
        val connection = URL(Policy.origin(origin) + path).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "POST"
            connection.instanceFollowRedirects = false // Never forward credentials to a redirect target.
            connection.connectTimeout = 5000
            connection.readTimeout = 25000
            connection.setRequestProperty("Content-Type", "application/json")
            if (token != null) connection.setRequestProperty("Authorization", "Bearer $token")
            connection.doOutput = true
            connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val bytes = stream?.use { input ->
                val output = java.io.ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                while (output.size() <= 262144) {
                    val count = input.read(buffer, 0, minOf(buffer.size, 262145 - output.size()))
                    if (count < 0) break
                    output.write(buffer, 0, count)
                }
                output.toByteArray()
            } ?: byteArrayOf()
            require(bytes.size <= 262144) { "Broker response exceeds size limit" }
            val parsed = try { JSONObject(String(bytes, Charsets.UTF_8)) } catch (_: Exception) { JSONObject() }
            if (status !in 200..299) throw HttpFailure(status, parsed.optString("code", "HTTP_ERROR").take(80))
            return parsed
        } finally { connection.disconnect() }
    }
}
