package com.nexvision.tv

import android.content.Context
import com.google.android.gms.cast.framework.CastOptions
import com.google.android.gms.cast.framework.OptionsProvider
import com.google.android.gms.cast.framework.SessionProvider

class CastOptionsProvider : OptionsProvider {
    override fun getCastOptions(context: Context): CastOptions =
        CastOptions.Builder()
            .setReceiverApplicationId("CC1AD845") // Default Media Receiver — works on all devices
            .build()

    override fun getAdditionalSessionProviders(context: Context): List<SessionProvider>? = null
}