package com.vision.alarm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.vision.data.local.VisionDatabase
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class BootReceiver : BroadcastReceiver() {
    @Inject lateinit var scheduler: AlarmScheduler
    @Inject lateinit var db: VisionDatabase

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action !in setOf(Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED)) return
        CoroutineScope(Dispatchers.IO).launch {
            db.alarmDao().getAllOnce().filter { it.triggerAtMillis > System.currentTimeMillis() }.forEach {
                scheduler.schedule(it)
            }
        }
    }
}
