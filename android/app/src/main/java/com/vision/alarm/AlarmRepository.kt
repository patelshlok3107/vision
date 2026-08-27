package com.vision.alarm

import com.vision.data.local.AlarmDao
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AlarmRepository @Inject constructor(
    private val dao: AlarmDao,
    private val scheduler: AlarmScheduler
) {
    val alarms: Flow<List<AlarmEntity>> = dao.observeAll()

    suspend fun add(entity: AlarmEntity): Long {
        val id = dao.insert(entity)
        val withId = entity.copy(id = id)
        scheduler.schedule(withId)
        return id
    }

    suspend fun cancel(id: Long) {
        scheduler.cancel(id)
        dao.deleteById(id)
    }

    suspend fun rescheduleRepeating(id: Long, intervalMinutes: Int) {
        val existing = dao.getById(id) ?: return
        val next = existing.copy(triggerAtMillis = System.currentTimeMillis() + intervalMinutes * 60_000L)
        dao.update(next)
        scheduler.schedule(next)
    }

    suspend fun snooze(id: Long, minutes: Int) {
        val e = dao.getById(id) ?: return
        val snoozed = e.copy(triggerAtMillis = System.currentTimeMillis() + minutes * 60_000L)
        dao.update(snoozed)
        scheduler.schedule(snoozed)
    }
}
