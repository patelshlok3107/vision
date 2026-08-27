package com.vision.alarm

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "alarms")
data class AlarmEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val title: String,
    val speakText: String,
    val triggerAtMillis: Long,
    val type: String, // ALARM | REMINDER
    val repeatIntervalMinutes: Int? = null, // null = one-shot, else repeating
    val enabled: Boolean = true,
    val createdAt: Long = System.currentTimeMillis()
)
