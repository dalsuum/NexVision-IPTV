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

    private val prefs get() = getSharedPreferences("nexvision", Context.MODE_PRIVATE)
    private var serverUrl: String get() = prefs.getString("server_url", "") ?: ""
        set(v) { prefs.edit().putString("server_url", v).apply() }
    private var savedUsername: String get() = prefs.getString("username", "") ?: ""
        set(v) { prefs.edit().putString("username", v).apply() }
    private var savedPassword: String get() = prefs.getString("password", "") ?: ""
        set(v) { prefs.edit().putString("password", v).apply() }
    private var authToken: String get() = prefs.getString("token", "") ?: ""
        set(v) { prefs.edit().putString("token", v).apply() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        setSupportActionBar(binding.toolbar)

        setupRecyclerView()
        setupLoginForm()
        setupSearch()

        if (serverUrl.isNotEmpty() && authToken.isNotEmpty()) {
            showChannelList()
            loadChannels()
        } else if (serverUrl.isNotEmpty()) {
            showLoginForm()
        } else {
            showLoginForm()
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
        binding.recyclerView.addItemDecoration(DividerItemDecoration(this, DividerItemDecoration.VERTICAL))
        binding.recyclerView.adapter = adapter
    }

    private fun setupLoginForm() {
        binding.etServerUrl.setText(serverUrl)
        binding.etUsername.setText(savedUsername)
        binding.btnConnect.setOnClickListener {
            val url = binding.etServerUrl.text.toString().trim()
            val username = binding.etUsername.text.toString().trim()
            val password = binding.etPassword.text.toString()

            if (url.isEmpty() || username.isEmpty() || password.isEmpty()) {
                Toast.makeText(this, "All fields are required", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            serverUrl = url
            savedUsername = username
            savedPassword = password
            doLogin(url, username, password)
        }
    }

    private fun setupSearch() {
        binding.searchView.setOnQueryTextListener(object : SearchView.OnQueryTextListener {
            override fun onQueryTextSubmit(query: String?) = false
            override fun onQueryTextChange(newText: String?): Boolean {
                val filtered = if (newText.isNullOrBlank()) {
                    allChannels
                } else {
                    allChannels.filter { it.name.contains(newText, ignoreCase = true) }
                }
                adapter.updateData(filtered)
                return true
            }
        })
    }

    private fun doLogin(url: String, username: String, password: String) {
        showLoading(true)
        executor.execute {
            try {
                val response = ApiClient.login(url, username, password)
                authToken = response.token
                runOnUiThread {
                    showLoading(false)
                    showChannelList()
                    loadChannels()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    showLoading(false)
                    Toast.makeText(this, "Login failed: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun loadChannels() {
        showLoading(true)
        executor.execute {
            try {
                val channels = ApiClient.getChannels(serverUrl, authToken)
                allChannels = channels
                runOnUiThread {
                    showLoading(false)
                    adapter.updateData(channels)
                    binding.tvChannelCount.text = "${channels.size} channels"
                }
            } catch (e: Exception) {
                runOnUiThread {
                    showLoading(false)
                    // Token may have expired — go back to login
                    if (e.message?.contains("401") == true || e.message?.contains("403") == true) {
                        authToken = ""
                        showLoginForm()
                        Toast.makeText(this, "Session expired. Please login again.", Toast.LENGTH_LONG).show()
                    } else {
                        Toast.makeText(this, "Failed to load channels: ${e.message}", Toast.LENGTH_LONG).show()
                    }
                }
            }
        }
    }

    private fun showLoginForm() {
        binding.loginForm.visibility = View.VISIBLE
        binding.channelListView.visibility = View.GONE
    }

    private fun showChannelList() {
        binding.loginForm.visibility = View.GONE
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
            R.id.action_settings -> {
                showServerConfigDialog()
                true
            }
            R.id.action_refresh -> {
                if (authToken.isNotEmpty()) loadChannels()
                true
            }
            R.id.action_logout -> {
                authToken = ""
                allChannels = emptyList()
                adapter.updateData(emptyList())
                showLoginForm()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    private fun showServerConfigDialog() {
        val dialogBinding = DialogServerConfigBinding.inflate(layoutInflater)
        dialogBinding.etDialogServerUrl.setText(serverUrl)
        dialogBinding.etDialogUsername.setText(savedUsername)

        AlertDialog.Builder(this)
            .setTitle("Server Configuration")
            .setView(dialogBinding.root)
            .setPositiveButton("Connect") { _, _ ->
                val url = dialogBinding.etDialogServerUrl.text.toString().trim()
                val username = dialogBinding.etDialogUsername.text.toString().trim()
                val password = dialogBinding.etDialogPassword.text.toString()
                if (url.isNotEmpty() && username.isNotEmpty() && password.isNotEmpty()) {
                    serverUrl = url
                    savedUsername = username
                    savedPassword = password
                    authToken = ""
                    doLogin(url, username, password)
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }
}
