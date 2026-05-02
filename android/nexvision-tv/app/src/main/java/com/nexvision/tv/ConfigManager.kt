package com.nexvision.tv

import android.content.Context
import org.json.JSONObject
import java.io.File

/**
 * Reads and writes /sdcard/Android/data/com.nexvision.tv/files/config.json
 *
 * getExternalFilesDir() requires zero storage permissions on all API levels
 * and is always accessible via ADB:
 *
 *   adb push config.json /sdcard/Android/data/com.nexvision.tv/files/config.json
 *
 * Expected JSON format:
 *   { "server_ip": "192.168.1.100", "server_port": 80, "room_number": "101" }
 */
object ConfigManager {

    private const val FILE_NAME    = "config.json"
    private const val KEY_IP       = "server_ip"
    private const val KEY_PORT     = "server_port"
    private const val KEY_ROOM     = "room_number"
    private const val DEFAULT_PORT = 80

    fun configFile(context: Context): File =
        File(context.getExternalFilesDir(null), FILE_NAME)

    fun read(context: Context): ServerConfig? {
        val file = configFile(context)
        if (!file.exists()) return null
        return try {
            val json       = JSONObject(file.readText().trim())
            val ip         = json.optString(KEY_IP,   "").trim()
            val port       = json.optInt  (KEY_PORT,  DEFAULT_PORT)
            val roomNumber = json.optString(KEY_ROOM, "").trim()
            if (ip.isBlank()) null else ServerConfig(ip, port, roomNumber)
        } catch (_: Exception) {
            null
        }
    }

    fun write(context: Context, ip: String, port: Int, roomNumber: String): Boolean {
        return try {
            val json = JSONObject().apply {
                put(KEY_IP,   ip.trim())
                put(KEY_PORT, port)
                put(KEY_ROOM, roomNumber.trim())
            }
            configFile(context).writeText(json.toString(2))
            true
        } catch (_: Exception) {
            false
        }
    }
}

data class ServerConfig(val ip: String, val port: Int, val roomNumber: String) {
    val url: String get() = "http://$ip:$port/tv?platform=tv"
}
