package com.nexvision.tv

import android.app.Activity
import android.net.Uri
import android.webkit.JavascriptInterface
import android.widget.Toast
import androidx.mediarouter.app.MediaRouteChooserDialog
import androidx.mediarouter.media.MediaRouteSelector
import com.google.android.gms.cast.MediaInfo
import com.google.android.gms.cast.MediaLoadRequestData
import com.google.android.gms.cast.MediaMetadata
import com.google.android.gms.cast.framework.CastContext
import com.google.android.gms.cast.framework.CastSession
import com.google.android.gms.cast.framework.SessionManagerListener
import com.google.android.gms.common.images.WebImage

class CastHelper(private val activity: Activity) {

    private var castContext: CastContext? = null
    private var pendingUrl   = ""
    private var pendingTitle = ""
    private var pendingLogo  = ""

    private val sessionListener = object : SessionManagerListener<CastSession> {
        override fun onSessionStarted(session: CastSession, sessionId: String) {
            if (pendingUrl.isNotEmpty()) {
                loadToSession(session, pendingUrl, pendingTitle, pendingLogo)
                pendingUrl = ""; pendingTitle = ""; pendingLogo = ""
            }
        }
        override fun onSessionStartFailed(session: CastSession, error: Int) {
            activity.runOnUiThread {
                Toast.makeText(activity, "Cast connection failed", Toast.LENGTH_SHORT).show()
            }
        }
        override fun onSessionResumed(session: CastSession, wasSuspended: Boolean) {}
        override fun onSessionEnded(session: CastSession, error: Int) {}
        override fun onSessionStarting(session: CastSession) {}
        override fun onSessionEnding(session: CastSession) {}
        override fun onSessionResumeFailed(session: CastSession, error: Int) {}
        override fun onSessionSuspended(session: CastSession, reason: Int) {}
        override fun onSessionResuming(session: CastSession, sessionId: String) {}
    }

    fun init() {
        try {
            castContext = CastContext.getSharedInstance(activity)
            castContext!!.sessionManager.addSessionManagerListener(
                sessionListener, CastSession::class.java
            )
        } catch (_: Exception) {
            // Google Play Services unavailable on this device — Cast disabled
        }
    }

    fun release() {
        castContext?.sessionManager?.removeSessionManagerListener(
            sessionListener, CastSession::class.java
        )
    }

    fun isAvailable() = castContext != null

    // ── JavaScript bridge ─────────────────────────────────────────────────────
    // Registered as "Android" on the WebView.  Methods run on a background
    // thread — UI operations must be posted to the main thread.

    inner class Bridge {

        // Called when the user taps a Cast button in the web UI (requestSession).
        // url/title/logo reflect the channel currently playing, if any.
        @JavascriptInterface
        fun requestCast(url: String, title: String, logo: String) {
            pendingUrl   = url
            pendingTitle = title
            pendingLogo  = logo
            activity.runOnUiThread { showPicker() }
        }

        // Called when a channel changes while a Cast session is already active (loadMedia).
        @JavascriptInterface
        fun loadCast(url: String, title: String, logo: String) {
            val session = castContext?.sessionManager?.currentCastSession
            if (session?.isConnected == true) {
                activity.runOnUiThread { loadToSession(session, url, title, logo) }
            }
        }

        // Called from the web VOD player to cast a movie/episode.
        @JavascriptInterface
        fun loadVod(url: String, title: String, poster: String) {
            val session = castContext?.sessionManager?.currentCastSession
            if (session?.isConnected == true) {
                activity.runOnUiThread { loadVodToSession(session, url, title, poster) }
            }
        }

        // Returns true if a Cast session is currently active (synchronous for JS).
        @JavascriptInterface
        fun isConnected(): Boolean =
            castContext?.sessionManager?.currentCastSession?.isConnected == true
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    private fun showPicker() {
        val ctx = castContext ?: return
        val session = ctx.sessionManager.currentCastSession
        if (session?.isConnected == true && pendingUrl.isNotEmpty()) {
            loadToSession(session, pendingUrl, pendingTitle, pendingLogo)
            pendingUrl = ""; pendingTitle = ""; pendingLogo = ""
            return
        }
        try {
            MediaRouteChooserDialog(activity).apply {
                routeSelector = ctx.mergedSelector ?: MediaRouteSelector.EMPTY
                show()
            }
        } catch (_: Exception) {
            Toast.makeText(activity, "No Cast devices found", Toast.LENGTH_SHORT).show()
        }
    }

    private fun loadToSession(session: CastSession, url: String, title: String, logo: String) {
        if (url.isEmpty()) return
        if (url.startsWith("udp://") || url.startsWith("rtp://")) return

        val meta = MediaMetadata(MediaMetadata.MEDIA_TYPE_GENERIC).apply {
            putString(MediaMetadata.KEY_TITLE, title.ifEmpty { "NexVision IPTV" })
            if (logo.isNotEmpty()) {
                try { addImage(WebImage(Uri.parse(logo))) } catch (_: Exception) {}
            }
        }
        val contentType = when {
            url.contains(".m3u8", ignoreCase = true) ||
            url.contains("/hls/",  ignoreCase = true) ||
            url.contains("/live/", ignoreCase = true) -> "application/x-mpegurl"
            url.endsWith(".ts",    ignoreCase = true)  -> "video/mp2t"
            else                                        -> "application/x-mpegurl"
        }
        val mediaInfo = MediaInfo.Builder(url)
            .setStreamType(MediaInfo.STREAM_TYPE_LIVE)
            .setContentType(contentType)
            .setMetadata(meta)
            .build()

        session.remoteMediaClient?.load(
            MediaLoadRequestData.Builder()
                .setMediaInfo(mediaInfo)
                .setAutoplay(true)
                .build()
        )
    }

    private fun loadVodToSession(session: CastSession, url: String, title: String, poster: String) {
        if (url.isEmpty()) return

        val meta = MediaMetadata(MediaMetadata.MEDIA_TYPE_MOVIE).apply {
            putString(MediaMetadata.KEY_TITLE, title.ifEmpty { "NexVision VOD" })
            if (poster.isNotEmpty()) {
                try { addImage(WebImage(Uri.parse(poster))) } catch (_: Exception) {}
            }
        }
        val contentType = when {
            url.contains(".m3u8", ignoreCase = true) ||
            url.contains("/hls/",  ignoreCase = true) -> "application/x-mpegurl"
            url.endsWith(".mp4",   ignoreCase = true)  -> "video/mp4"
            url.endsWith(".mkv",   ignoreCase = true)  -> "video/x-matroska"
            else                                        -> "video/mp4"
        }
        val mediaInfo = MediaInfo.Builder(url)
            .setStreamType(MediaInfo.STREAM_TYPE_BUFFERED)
            .setContentType(contentType)
            .setMetadata(meta)
            .build()

        session.remoteMediaClient?.load(
            MediaLoadRequestData.Builder()
                .setMediaInfo(mediaInfo)
                .setAutoplay(true)
                .build()
        )
    }
}