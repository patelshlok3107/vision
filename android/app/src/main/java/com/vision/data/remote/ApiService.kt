package com.vision.data.remote

import okhttp3.ResponseBody
import retrofit2.http.*

/** Matches backend/config/urls.py + ai_agent/urls.py: actual endpoints */
data class LoginRequest(val username: String, val password: String)
data class TokenResponse(val access: String, val refresh: String)
data class TaskDto(val id: Int, val title: String, val priority: String, val status: String, val due_date: String?)
data class BriefingResponse(val text: String, val tasks: List<TaskDto>, val reminders: List<String>)
data class AgentChatRequest(val message: String, val conversation_id: String? = null)
data class ToolCall(val name: String, val arguments: Map<String, String>)

interface ApiService {
    @POST("api/auth/login/")
    suspend fun login(@Body body: LoginRequest): TokenResponse

    @GET("api/tasks/")
    suspend fun getTasks(@Header("Authorization") auth: String): List<TaskDto>

    @GET("api/reminders/")
    suspend fun getReminders(@Header("Authorization") auth: String): List<Map<String, String>>

    /** Streaming NDJSON — backend ai_agent/views.py:74 AIChatView returns StreamingHttpResponse */
    @POST("api/ai/chat/")
    @Streaming
    suspend fun agentChatStream(
        @Header("Authorization") auth: String,
        @Body body: AgentChatRequest
    ): ResponseBody

    /** Non-stream fallback if needed */
    @POST("api/ai/chat/")
    suspend fun agentChat(
        @Header("Authorization") auth: String,
        @Body body: AgentChatRequest
    ): ResponseBody

    @GET("api/ai/briefing/morning/")
    suspend fun morningBriefing(@Header("Authorization") auth: String): BriefingResponse

    @GET("api/ai/briefing/night/")
    suspend fun nightBriefing(@Header("Authorization") auth: String): BriefingResponse

    @GET("api/ai/health/")
    suspend fun health(): Map<String, Any>
}
