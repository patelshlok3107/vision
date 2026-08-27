package com.vision.di

import android.content.Context
import androidx.room.Room
import com.vision.data.local.VisionDatabase
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {
    @Provides @Singleton
    fun provideDb(@ApplicationContext ctx: Context): VisionDatabase =
        Room.databaseBuilder(ctx, VisionDatabase::class.java, "vision.db")
            .fallbackToDestructiveMigration()
            .build()

    @Provides fun provideAlarmDao(db: VisionDatabase) = db.alarmDao()
    @Provides fun provideTaskDao(db: VisionDatabase) = db.taskDao()
}
