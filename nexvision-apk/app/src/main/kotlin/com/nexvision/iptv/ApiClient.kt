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

data class RoomInfo(
    val token: String,
    val room_number: String,
    val tv_name: String
)

data class Settings(
    val deployment_mode: String = "hotel",
    val hotel_name: String = "NexVision"
)

object ApiClient {

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()
    private val JSON = "application/json; charset=utf-8".toMediaType()

    fun registerRoom(serverUrl: String, roomNumber: String): RoomInfo {
        val body = gson.toJson(mapOf("room_number" to roomNumber))
        val request = Request.Builder()
            .url("${serverUrl.trimEnd('/')}/api/rooms/register")
            .post(body.toRequestBody(JSON))
            .build()
        val response = client.newCall(request).execute()
        val responseBody = response.body?.string() ?: throw Exception("Empty response")
        if (!response.isSuccessful) {
            val error = try {
                gson.fromJson(responseBody, Map::class.java)["error"] as? String
            } catch (e: Exception) { null }
            throw Exception(error ?: "Registration failed (${response.code})")
        }
        return gson.fromJson(responseBody, RoomInfo::class.java)
    }

    fun getChannels(serverUrl: String, roomToken: String): List<Channel> {
        val request = Request.Builder()
            .url("${serverUrl.trimEnd('/')}/api/channels?active=1&limit=500")
            .addHeader("X-Room-Token", roomToken)
            .get()
            .build()
        val response = client.newCall(request).execute()
        val responseBody = response.body?.string() ?: throw Exception("Empty response")
        if (!response.isSuccessful) throw Exception("Failed to load channels (${response.code})")
        val type = object : TypeToken<List<Channel>>() {}.type
        return gson.fromJson(responseBody, type)
    }

    fun getSettings(serverUrl: String): Settings {
        val request = Request.Builder()
            .url("${serverUrl.trimEnd('/')}/api/settings")
            .get()
            .build()
        return try {
            val response = client.newCall(request).execute()
            val body = response.body?.string() ?: return Settings()
            val map = gson.fromJson(body, Map::class.java)
            Settings(
                deployment_mode = map["deployment_mode"] as? String ?: "hotel",
                hotel_name = map["hotel_name"] as? String ?: "NexVision"
            )
        } catch (e: Exception) {
            Settings()
        }
    }
}
