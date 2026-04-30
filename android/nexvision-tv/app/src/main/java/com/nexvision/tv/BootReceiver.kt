package com.nexvision.tv

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Relaunches MainActivity after the device finishes booting.
 *
 * Why both actions?
 *   BOOT_COMPLETED       — fires after the user has unlocked (full boot, credentials available).
 *   LOCKED_BOOT_COMPLETED — fires earlier, before unlock, on devices with file-based encryption.
 *                           Including it ensures the app appears on the TV home screen immediately
 *                           on devices that auto-boot without a PIN (most Android TV boxes).
 *
 * FLAG_ACTIVITY_NEW_TASK is mandatory when starting an Activity from a non-Activity context.
 * FLAG_ACTIVITY_CLEAR_TOP + SINGLE_TOP collapse any stale instances from the previous session.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return

        if (action != Intent.ACTION_BOOT_COMPLETED &&
            action != "android.intent.action.LOCKED_BOOT_COMPLETED"
        ) return

        val launch = Intent(context, MainActivity::class.java).apply {
            addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK
                or Intent.FLAG_ACTIVITY_CLEAR_TOP
                or Intent.FLAG_ACTIVITY_SINGLE_TOP
            )
        }

        context.startActivity(launch)
    }
}
