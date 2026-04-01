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
    private lateinit var libVLC: LibVLC
    private lateinit var mediaPlayer: MediaPlayer

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityVlcplayerBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val streamUrl = intent.getStringExtra(EXTRA_STREAM_URL) ?: run {
            Toast.makeText(this, "No stream URL provided", Toast.LENGTH_SHORT).show()
            finish()
            return
        }
        val channelName = intent.getStringExtra(EXTRA_CHANNEL_NAME) ?: "Playing"
        binding.tvChannelName.text = channelName

        val options = arrayListOf(
            "--no-drop-late-frames",
            "--no-skip-frames",
            "--rtsp-tcp",
            "--network-caching=1500"
        )
        libVLC = LibVLC(this, options)
        mediaPlayer = MediaPlayer(libVLC)

        binding.surfaceView.holder.addCallback(this)

        binding.btnBack.setOnClickListener { finish() }
    }

    private fun playStream(url: String) {
        binding.progressBar.visibility = View.VISIBLE
        val media = Media(libVLC, Uri.parse(url))
        mediaPlayer.media = media
        media.release()

        mediaPlayer.setEventListener { event ->
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
        mediaPlayer.play()
    }

    override fun surfaceCreated(holder: SurfaceHolder) {
        val vout = mediaPlayer.vlcVout
        vout.setVideoSurface(holder.surface, holder)
        vout.attachViews()
        val url = intent.getStringExtra(EXTRA_STREAM_URL) ?: return
        playStream(url)
    }

    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
        mediaPlayer.vlcVout.setWindowSize(width, height)
    }

    override fun surfaceDestroyed(holder: SurfaceHolder) {
        mediaPlayer.stop()
        mediaPlayer.vlcVout.detachViews()
    }

    override fun onDestroy() {
        super.onDestroy()
        mediaPlayer.release()
        libVLC.release()
    }
}
