package com.nexvision.iptv

import android.webkit.JavascriptInterface

/**
 * JavaScript bridge injected as `window.AndroidBridge` in the WebView.
 * Allows the TV client JS to trigger native VLC playback for streams
 * that the browser cannot handle (RTSP, UDP, etc.).
 */
class NexVisionBridge(private val activity: MainActivity) {

    @JavascriptInterface
    fun playStream(url: String, name: String) {
        activity.runOnUiThread {
            activity.launchVlc(url, name)
        }
    }

    @JavascriptInterface
    fun isNativeApp(): Boolean = true
}
