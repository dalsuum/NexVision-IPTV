package com.nexvision.iptv

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.widget.SearchView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.DividerItemDecoration
import androidx.recyclerview.widget.LinearLayoutManager
import com.nexvision.iptv.databinding.ActivityMainBinding
import com.nexvision.iptv.databinding.DialogServerConfigBinding
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var adapter: ChannelAdapter
    private val executor = Executors.newSingleThreadExecutor()

    private var allChannels: List<Channel> = emptyList()
    private var isCommercialMode = false

    private val prefs get() = getSharedPreferences("nexvision", Context.MODE_PRIVATE)
    private var serverUrl: String
        get() = prefs.getString("server_url", "") ?: ""
        set(v) { prefs.edit().putString("server_url", v).apply() }
    private var roomToken: String
        get() = prefs.getString("room_token", "") ?: ""
        set(v) { prefs.edit().putString("room_token", v).apply() }
    private var roomNumber: String
        get() = prefs.getString("room_number", "") ?: ""
        set(v) { prefs.edit().putString("room_number", v).apply() }

    private val unitLabel get() = if (isCommercialMode) "Screen" else "Room"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        setSupportActionBar(binding.toolbar)

        setupRecyclerView()
        setupRegisterForm()
        setupSearch()

        if (serverUrl.isNotEmpty() && roomToken.isNotEmpty()) {
            loadSettingsThenChannels()
        } else {
            showRegisterForm()
        }
    }

    private fun setupRecyclerView() {
        adapter = ChannelAdapter(emptyList()) { channel ->
            val intent = Intent(this, VLCPlayerActivity::class.java).apply {
                putExtra(VLCPlayerActivity.EXTRA_STREAM_URL, channel.url)
                putExtra(VLCPlayerActivity.EXTRA_CHANNEL_NAME, channel.name)
            }
            startActivity(intent)
        }
        binding.recyclerView.layoutManager = LinearLayoutManager(this)
        binding.recyclerView.addItemDecoration(
            DividerItemDecoration(this, DividerItemDecoration.VERTICAL)
        )
        binding.recyclerView.adapter = adapter
    }

    private fun setupRegisterForm() {
        binding.etServerUrl.setText(serverUrl)
        binding.etRoomNumber.setText(roomNumber)

        binding.btnConnect.setOnClickListener {
            val url = binding.etServerUrl.text.toString().trim()
            val room = binding.etRoomNumber.text.toString().trim()

            if (url.isEmpty() || room.isEmpty()) {
                Toast.makeText(this, "Server URL and room number are required", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            serverUrl = url
            doRegister(url, room)
        }
    }

    private fun setupSearch() {
        binding.searchView.setOnQueryTextListener(object : SearchView.OnQueryTextListener {
            override fun onQueryTextSubmit(query: String?) = false
            override fun onQueryTextChange(newText: String?): Boolean {
                val filtered = if (newText.isNullOrBlank()) allChannels
                else allChannels.filter { it.name.contains(newText, ignoreCase = true) }
                adapter.updateData(filtered)
                return true
            }
        })
    }

    private fun doRegister(url: String, room: String) {
        showLoading(true)
        executor.execute {
            try {
                val info = ApiClient.registerRoom(url, room)
                roomToken = info.token
                roomNumber = info.room_number
                runOnUiThread {
                    showLoading(false)
                    showChannelList()
                    loadSettingsThenChannels()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    showLoading(false)
                    Toast.makeText(this, e.message ?: "Registration failed", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun loadSettingsThenChannels() {
        executor.execute {
            try {
                val settings = ApiClient.getSettings(serverUrl)
                isCommercialMode = settings.deployment_mode == "commercial"
            } catch (e: Exception) {
                // settings failure is non-fatal, continue with defaults
            }
            runOnUiThread {
                val label = if (roomNumber.isNotEmpty()) "$unitLabel $roomNumber" else unitLabel
                supportActionBar?.subtitle = label
                showChannelList()
                loadChannels()
            }
        }
    }

    private fun loadChannels() {
        showLoading(true)
        executor.execute {
            try {
                val channels = ApiClient.getChannels(serverUrl, roomToken)
                allChannels = channels
                runOnUiThread {
                    showLoading(false)
                    adapter.updateData(channels)
                    binding.tvChannelCount.text = "${channels.size} channels"
                }
            } catch (e: Exception) {
                runOnUiThread {
                    showLoading(false)
                    Toast.makeText(
                        this, "Failed to load channels: ${e.message}", Toast.LENGTH_LONG
                    ).show()
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        executor.shutdownNow()
    }

    private fun showRegisterForm() {
        binding.registerForm.visibility = View.VISIBLE
        binding.channelListView.visibility = View.GONE
    }

    private fun showChannelList() {
        binding.registerForm.visibility = View.GONE
        binding.channelListView.visibility = View.VISIBLE
    }

    private fun showLoading(loading: Boolean) {
        binding.progressBar.visibility = if (loading) View.VISIBLE else View.GONE
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_refresh -> {
                if (roomToken.isNotEmpty()) loadChannels()
                true
            }
            R.id.action_settings -> {
                showServerConfigDialog()
                true
            }
            R.id.action_logout -> {
                roomToken = ""
                roomNumber = ""
                allChannels = emptyList()
                adapter.updateData(emptyList())
                showRegisterForm()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    private fun showServerConfigDialog() {
        val dialogBinding = DialogServerConfigBinding.inflate(layoutInflater)
        dialogBinding.etDialogServerUrl.setText(serverUrl)
        dialogBinding.etDialogRoomNumber.setText(roomNumber)

        AlertDialog.Builder(this)
            .setTitle("Change $unitLabel")
            .setView(dialogBinding.root)
            .setPositiveButton("Connect") { _, _ ->
                val url = dialogBinding.etDialogServerUrl.text.toString().trim()
                val room = dialogBinding.etDialogRoomNumber.text.toString().trim()
                if (url.isNotEmpty() && room.isNotEmpty()) {
                    serverUrl = url
                    roomToken = ""
                    doRegister(url, room)
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }
}
