package com.nexvision.iptv

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

data class Channel(
    val id: Int,
    val name: String,
    val logo: String?,
    val url: String,
    val group_name: String?,
    val active: Int = 1
)

data class LoginResponse(
    val token: String,
    val user: UserInfo
)

data class UserInfo(
    val id: Int,
    val username: String,
    val role: String
)

object ApiClient {

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()
    private val JSON = "application/json; charset=utf-8".toMediaType()

    fun login(serverUrl: String, username: String, password: String): LoginResponse {
        val body = gson.toJson(mapOf("username" to username, "password" to password))
        val request = Request.Builder()
            .url("${serverUrl.trimEnd('/')}/api/auth/login")
            .post(body.toRequestBody(JSON))
            .build()
        val response = client.newCall(request).execute()
        val responseBody = response.body?.string() ?: throw Exception("Empty response")
        if (!response.isSuccessful) {
            val error = try { gson.fromJson(responseBody, Map::class.java)["error"] as? String } catch (e: Exception) { null }
            throw Exception(error ?: "Login failed (${response.code})")
        }
        return gson.fromJson(responseBody, LoginResponse::class.java)
    }

    fun getChannels(serverUrl: String, token: String): List<Channel> {
        val request = Request.Builder()
            .url("${serverUrl.trimEnd('/')}/api/channels?active=1&limit=500")
            .addHeader("Authorization", "Bearer $token")
            .get()
            .build()
        val response = client.newCall(request).execute()
        val responseBody = response.body?.string() ?: throw Exception("Empty response")
        if (!response.isSuccessful) throw Exception("Failed to load channels (${response.code})")
        val type = object : TypeToken<List<Channel>>() {}.type
        return gson.fromJson(responseBody, type)
    }
}
