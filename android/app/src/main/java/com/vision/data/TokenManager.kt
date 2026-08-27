package com.vision.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.ds by preferencesDataStore("vision_prefs")

@Singleton
class TokenManager @Inject constructor(@ApplicationContext private val ctx: Context) {
    private val KEY = stringPreferencesKey("access_token")
    val tokenFlow: Flow<String?> = ctx.ds.data.map { it[KEY] }
    suspend fun save(token: String) { ctx.ds.edit { it[KEY] = token } }
    suspend fun clear() { ctx.ds.edit { it.remove(KEY) } }
    fun authHeader(token: String) = "Bearer $token"
}
