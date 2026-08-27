package com.vision.ui

import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.google.accompanist.permissions.ExperimentalPermissionsApi
import com.google.accompanist.permissions.isGranted
import com.google.accompanist.permissions.rememberPermissionState
import com.vision.voice.VoiceEngine
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalPermissionsApi::class)
@Composable
fun VisionNavHost(vm: VisionViewModel = hiltViewModel()) {
    val micPerm = rememberPermissionState(android.Manifest.permission.RECORD_AUDIO)
    val notifPerm = if (android.os.Build.VERSION.SDK_INT >= 33) rememberPermissionState(android.Manifest.permission.POST_NOTIFICATIONS) else null
    LaunchedEffect(Unit) { if (!micPerm.status.isGranted) micPerm.launchPermissionRequest() }
    VisionHomeScreen(vm, micGranted = micPerm.status.isGranted, onRequestMic = { micPerm.launchPermissionRequest() })
}

@Composable
fun VisionHomeScreen(vm: VisionViewModel, micGranted: Boolean = true, onRequestMic: () -> Unit = {}) {
    val alarms by vm.alarmsFlow.collectAsState()
    val voiceState by vm.voiceState.collectAsState()
    val isSpeaking by vm.isSpeaking.collectAsState()
    val reply by vm.lastReply.collectAsState()
    var textInput by remember { mutableStateOf("") }

    val isListening = voiceState is VoiceEngine.State.Listening
    val pulse by rememberInfiniteTransition(label = "pulse").animateFloat(
        initialValue = 0.8f, targetValue = 1.15f,
        animationSpec = infiniteRepeatable(tween(900, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "p"
    )

    Box(modifier = Modifier.fillMaxSize().background(Color(0xFF0A0A0F)).padding(20.dp)) {
        Column(modifier = Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally) {
            Spacer(Modifier.height(32.dp))
            Text("VISION", fontSize = 28.sp, fontWeight = FontWeight.Black, letterSpacing = 8.sp, color = Color.White)
            Spacer(Modifier.height(6.dp))
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center) {
                Box(Modifier.size(8.dp).clip(CircleShape).background(Color(0xFF00E5CC)))
                Spacer(Modifier.width(8.dp))
                Text("ONLINE", fontSize = 11.sp, letterSpacing = 3.sp, color = Color(0xFF00E5CC))
            }
            Spacer(Modifier.height(28.dp))
            // Glass card - reply
            Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFF1A1A2E).copy(alpha = 0.7f)), modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("\"$reply\"", color = Color.White.copy(alpha = 0.9f), fontSize = 16.sp, lineHeight = 22.sp)
                    if (isSpeaking) {
                        Spacer(Modifier.height(10.dp))
                        TextButton(onClick = { vm.stopSpeaking() }) { Text("Stop", color = Color(0xFFFF6B6B)) }
                    }
                }
            }
            Spacer(Modifier.height(24.dp))
            // Listening orb
            Box(contentAlignment = Alignment.Center, modifier = Modifier.size(110.dp)) {
                if (isListening || isSpeaking) Box(Modifier.size((76 * pulse).dp).clip(CircleShape).background(Brush.radialGradient(listOf(Color(0xFF7C4DFF).copy(0.45f), Color.Transparent))))
                FilledIconButton(
                    onClick = { if (!micGranted) onRequestMic() else vm.onMicTap() },
                    modifier = Modifier.size(76.dp),
                    colors = IconButtonDefaults.filledIconButtonColors(containerColor = if (isListening) Color(0xFF7C4DFF) else Color(0xFF1E1E32)),
                    shape = CircleShape
                ) {
                    Icon(if (isListening || isSpeaking) Icons.Filled.Stop else Icons.Filled.Mic, contentDescription = "Talk", tint = Color.White, modifier = Modifier.size(34.dp))
                }
            }
            Text(if (isListening) "Listening..." else if (isSpeaking) "Speaking..." else "Tap to talk", color = Color.White.copy(0.55f), fontSize = 12.sp, letterSpacing = 1.sp)
            Spacer(Modifier.height(20.dp))
            // Stats row
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                StatCard("${alarms.count { it.type == "ALARM" }} Alarms", alarms.count { it.type == "ALARM" }.toString())
                StatCard("${alarms.count { it.type == "REMINDER" }} Reminders", alarms.count { it.type == "REMINDER" }.toString())
            }
            Spacer(Modifier.height(14.dp))
            if (alarms.isNotEmpty()) {
                val next = alarms.minByOrNull { it.triggerAtMillis }
                Card(shape = RoundedCornerShape(14.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFF16162A)), modifier = Modifier.fillMaxWidth()) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("Next: ${next?.title}", color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                            Text(next?.let { SimpleDateFormat("hh:mm a", Locale.getDefault()).format(Date(it.triggerAtMillis)) } ?: "", color = Color.White.copy(0.5f), fontSize = 11.sp)
                        }
                        Text(next?.type ?: "", color = Color(0xFF00E5CC), fontSize = 10.sp, letterSpacing = 1.sp)
                    }
                }
            }
            Spacer(Modifier.height(14.dp))
            LazyColumn(modifier = Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(alarms) { a ->
                    Card(shape = RoundedCornerShape(12.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFF1A1A2E))) {
                        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(a.title, color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                                Text(SimpleDateFormat("EEE hh:mm a", Locale.getDefault()).format(Date(a.triggerAtMillis)) + (a.repeatIntervalMinutes?.let { " • every ${it/60}h" } ?: ""), color = Color.White.copy(0.45f), fontSize = 11.sp)
                            }
                            Text(a.type, color = Color.White.copy(0.35f), fontSize = 10.sp)
                        }
                    }
                }
            }
            // Text input fallback
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(value = textInput, onValueChange = { textInput = it }, placeholder = { Text("Type to VISION...", color = Color.White.copy(0.3f)) }, modifier = Modifier.weight(1f), shape = RoundedCornerShape(24.dp), colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Color(0xFF7C4DFF), unfocusedBorderColor = Color.White.copy(0.12f), focusedTextColor = Color.White, unfocusedTextColor = Color.White))
                Spacer(Modifier.width(8.dp))
                Button(onClick = { if (textInput.isNotBlank()) { vm.onTextSubmit(textInput); textInput = "" } }, shape = CircleShape, colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF7C4DFF))) { Text("Send") }
            }
        }
    }
}

@Composable
private fun StatCard(label: String, value: String) {
    Card(shape = RoundedCornerShape(14.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFF16162A))) {
        Column(Modifier.padding(horizontal = 18.dp, vertical = 12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(value, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 18.sp)
            Text(label, color = Color.White.copy(0.45f), fontSize = 10.sp, letterSpacing = 0.5.sp)
        }
    }
}
