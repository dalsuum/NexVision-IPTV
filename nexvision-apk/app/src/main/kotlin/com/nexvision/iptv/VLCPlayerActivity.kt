package com.nexvision.iptv

import android.net.Uri
import android.os.Bundle
import android.view.SurfaceHolder
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.nexvision.iptv.databinding.ActivityVlcplayerBinding
import org.videolan.libvlc.LibVLC
import org.videolan.libvlc.Media
import org.videolan.libvlc.MediaPlayer

class VLCPlayerActivity : AppCompatActivity(), SurfaceHolder.Callback {

    companion object {
        const val EXTRA_STREAM_URL = "stream_url"
        const val EXTRA_CHANNEL_NAME = "channel_name"
    }

    private lateinit var binding: ActivityVlcplayerBinding
    private var libVLC: LibVLC? = null
    private var mediaPlayer: MediaPlayer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityVlcplayerBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val streamUrl = intent.getStringExtra(EXTRA_STREAM_URL)
        val channelName = intent.getStringExtra(EXTRA_CHANNEL_NAME) ?: "Playing"

        if (streamUrl.isNullOrEmpty()) {
            Toast.makeText(this, "No stream URL provided", Toast.LENGTH_SHORT).show()
            finish()
            return
        }

        binding.tvChannelName.text = channelName
        binding.btnBack.setOnClickListener { finish() }

        try {
            val options = arrayListOf(
                "--no-drop-late-frames",
                "--no-skip-frames",
                "--rtsp-tcp",
                "--network-caching=1500"
            )
            libVLC = LibVLC(this, options)
            mediaPlayer = MediaPlayer(libVLC)
            binding.surfaceView.holder.addCallback(this)
        } catch (e: Exception) {
            Toast.makeText(this, "Failed to initialize player: ${e.message}", Toast.LENGTH_LONG).show()
            finish()
        }
    }

    private fun playStream(url: String) {
        val player = mediaPlayer ?: return
        val vlc = libVLC ?: return
        binding.progressBar.visibility = View.VISIBLE
        val media = Media(vlc, Uri.parse(url))
        player.media = media
        media.release()

        player.setEventListener { event ->
            when (event.type) {
                MediaPlayer.Event.Playing -> runOnUiThread {
                    binding.progressBar.visibility = View.GONE
                }
                MediaPlayer.Event.EncounteredError -> runOnUiThread {
                    binding.progressBar.visibility = View.GONE
                    Toast.makeText(this, "Stream error — check URL or network", Toast.LENGTH_LONG).show()
                }
                MediaPlayer.Event.Buffering -> runOnUiThread {
                    binding.progressBar.visibility = if (event.buffering < 100f) View.VISIBLE else View.GONE
                }
            }
        }
        player.play()
    }

    override fun surfaceCreated(holder: SurfaceHolder) {
        val player = mediaPlayer ?: return
        val vout = player.vlcVout
        vout.setVideoSurface(holder.surface, holder)
        vout.attachViews()
        val url = intent.getStringExtra(EXTRA_STREAM_URL) ?: return
        playStream(url)
    }

    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
        mediaPlayer?.vlcVout?.setWindowSize(width, height)
    }

    override fun surfaceDestroyed(holder: SurfaceHolder) {
        mediaPlayer?.stop()
        mediaPlayer?.vlcVout?.detachViews()
    }

    override fun onDestroy() {
        super.onDestroy()
        mediaPlayer?.release()
        libVLC?.release()
        mediaPlayer = null
        libVLC = null
    }
}
