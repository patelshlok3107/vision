package com.vision.data.local

import androidx.room.*
import com.vision.alarm.AlarmEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface AlarmDao {
    @Query("SELECT * FROM alarms ORDER BY triggerAtMillis ASC")
    fun observeAll(): Flow<List<AlarmEntity>>

    @Query("SELECT * FROM alarms ORDER BY triggerAtMillis ASC")
    suspend fun getAllOnce(): List<AlarmEntity>

    @Query("SELECT * FROM alarms WHERE id = :id LIMIT 1")
    suspend fun getById(id: Long): AlarmEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(e: AlarmEntity): Long

    @Update
    suspend fun update(e: AlarmEntity)

    @Query("DELETE FROM alarms WHERE id = :id")
    suspend fun deleteById(id: Long)
}

@Entity(tableName = "tasks")
data class TaskEntity(
    @PrimaryKey val id: String,
    val title: String,
    val priority: String,
    val done: Boolean,
    val dueAt: Long?
)

@Dao
interface TaskDao {
    @Query("SELECT * FROM tasks ORDER BY dueAt ASC")
    fun observeAll(): Flow<List<TaskEntity>>
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertAll(items: List<TaskEntity>)
    @Query("DELETE FROM tasks") suspend fun clear()
}

@Database(entities = [AlarmEntity::class, TaskEntity::class], version = 1, exportSchema = false)
@TypeConverters(Converters::class)
abstract class VisionDatabase : RoomDatabase() {
    abstract fun alarmDao(): AlarmDao
    abstract fun taskDao(): TaskDao
}

class Converters {
    // placeholder for future type converters
}
