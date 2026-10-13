package com.masterdooom.proxyproof

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.LifecycleOwner
import androidx.core.content.ContextCompat
import com.masterdooom.proxyproof.data.ApiClient
import com.masterdooom.proxyproof.ble.BleAdvertiser
import com.masterdooom.proxyproof.ble.BleObservation
import com.masterdooom.proxyproof.ble.BleProtocol
import com.masterdooom.proxyproof.ble.BleScanner
import com.masterdooom.proxyproof.security.SecureTokenStore
import com.masterdooom.proxyproof.ui.theme.ProxyProofTheme
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import java.util.UUID

private const val PREFS_NAME = "proxyproof_preferences"

private fun requiredBlePermissions(): Array<String> =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        arrayOf(
            Manifest.permission.BLUETOOTH_SCAN,
            Manifest.permission.BLUETOOTH_ADVERTISE,
            Manifest.permission.BLUETOOTH_CONNECT
        )
    } else {
        arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
    }

private fun hasRequiredBlePermissions(context: Context): Boolean =
    requiredBlePermissions().all {
        ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
    }

private fun isAuthenticationRejected(error: Throwable): Boolean {
    val message = error.message.orEmpty()
    return message.startsWith("HTTP 401:") && (
        message.contains("access token", ignoreCase = true) ||
            message.contains("authentication required", ignoreCase = true)
    )
}

private data class RoomItem(
    val id: Int,
    val building: String,
    val roomCode: String,
    val displayName: String
)

private data class SessionItem(
    val id: String,
    val roomId: Int,
    val roomName: String,
    val subject: String,
    val scheduledStart: String,
    val deadline: String,
    val status: String,
    val attendanceOpen: Boolean
)

private data class HistoryItem(
    val sessionId: String,
    val roomName: String,
    val subject: String,
    val markedAt: String,
    val status: String,
    val method: String
)

private data class RosterItem(
    val studentId: Int,
    val username: String,
    val displayName: String,
    val status: String?,
    val markedAt: String?,
    val method: String?
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            ProxyProofTheme {
                ProxyProofRoot()
            }
        }
    }
}

@Composable
private fun ProxyProofRoot() {
    val context = LocalContext.current
    val prefs = remember { context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE) }
    val secureTokenStore = remember(context) { SecureTokenStore(context) }
    val legacyToken = remember { prefs.getString("access_token", null) }
    val defaultApiUrl = remember { context.getString(R.string.default_api_url) }
    var apiBase by remember {
        mutableStateOf(prefs.getString("api_base", defaultApiUrl) ?: defaultApiUrl)
    }
    var token by remember { mutableStateOf(secureTokenStore.read() ?: legacyToken.orEmpty()) }
    LaunchedEffect(secureTokenStore) {
        // Migrate an older plaintext token once, then remove the old preference.
        if (secureTokenStore.read().isNullOrBlank() && !legacyToken.isNullOrBlank()) {
            val migrated = runCatching { secureTokenStore.write(legacyToken) }.isSuccess
            prefs.edit().remove("access_token").apply()
            if (!migrated) token = ""
        }
    }
    var username by remember { mutableStateOf(prefs.getString("username", "") ?: "") }
    var displayName by remember { mutableStateOf(prefs.getString("display_name", "") ?: "") }
    var role by remember { mutableStateOf(prefs.getString("role", "student") ?: "student") }
    var authBusy by remember { mutableStateOf(false) }
    var authMessage by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    if (token.isBlank()) {
        LoginScreen(
            apiBase = apiBase,
            onApiBaseChange = {
                apiBase = it
                prefs.edit().putString("api_base", it).apply()
            },
            busy = authBusy,
            message = authMessage,
            onClearMessage = { authMessage = "" },
            onSubmit = { isRegister, user, name, password, selectedRole, inviteCode ->
                scope.launch {
                    authBusy = true
                    authMessage = ""
                    try {
                        val payload = JSONObject()
                            .put("username", user.trim())
                            .put("password", password)
                        val path: String
                        val method: String
                        if (isRegister) {
                            path = "/auth/register"
                            method = "POST"
                            payload.put("display_name", name.trim())
                                .put("role", selectedRole)
                            if (selectedRole == "organiser") {
                                payload.put("organiser_invite_code", inviteCode)
                            }
                        } else {
                            path = "/auth/login"
                            method = "POST"
                        }
                        val response = JSONObject(
                            ApiClient.request(
                                baseUrl = apiBase,
                                method = method,
                                path = path,
                                body = payload
                            )
                        )
                        val userData = response.getJSONObject("user")
                        val issuedToken = response.getString("access_token")
                        secureTokenStore.write(issuedToken)
                        token = issuedToken
                        username = userData.optString("username", user.trim())
                        displayName = userData.optString("display_name", username)
                        role = userData.optString("role", "student")
                        prefs.edit()
                            .remove("access_token")
                            .putString("username", username)
                            .putString("display_name", displayName)
                            .putString("role", role)
                            .apply()
                    } catch (error: Exception) {
                        authMessage = error.message
                            ?.takeIf { it.isNotBlank() }
                            ?: "Could not connect. Check the server URL and try again."
                    } finally {
                        authBusy = false
                    }
                }
            }
        )
    } else {
        DashboardScreen(
            apiBase = apiBase,
            token = token,
            username = username,
            displayName = displayName,
            role = role,
            prefs = prefs,
            onLogout = {
                val apiUrlToRevoke = apiBase
                val tokenToRevoke = token
                secureTokenStore.clear()
                prefs.edit().remove("access_token").apply()
                token = ""
                authMessage = ""
                scope.launch {
                    runCatching {
                        ApiClient.request(
                            apiUrlToRevoke,
                            "POST",
                            "/auth/logout",
                            tokenToRevoke
                        )
                    }
                }
            },
            onAuthExpired = {
                secureTokenStore.clear()
                prefs.edit().remove("access_token").apply()
                token = ""
                authMessage = "Your sign-in expired. Log in again to continue."
            }
        )
    }
}

@Composable
private fun LoginScreen(
    apiBase: String,
    onApiBaseChange: (String) -> Unit,
    busy: Boolean,
    message: String,
    onClearMessage: () -> Unit,
    onSubmit: (Boolean, String, String, String, String, String) -> Unit
) {
    var isRegister by remember { mutableStateOf(false) }
    var username by remember { mutableStateOf("") }
    var displayName by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var inviteCode by remember { mutableStateOf("") }
    var selectedRole by remember { mutableStateOf("student") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 22.dp, vertical = 28.dp),
        verticalArrangement = Arrangement.Center
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .size(48.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(MaterialTheme.colorScheme.primary),
                contentAlignment = Alignment.Center
            ) {
                Text("P", color = MaterialTheme.colorScheme.onPrimary, fontSize = 27.sp, fontWeight = FontWeight.Black)
            }
            Spacer(Modifier.width(12.dp))
            Column {
                Text("ProxyProof", fontSize = 27.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.8).sp)
                Text("ROOM-BASED ATTENDANCE", color = MaterialTheme.colorScheme.secondary, fontSize = 10.sp, letterSpacing = 2.sp, fontWeight = FontWeight.SemiBold)
            }
        }
        Spacer(Modifier.height(30.dp))
        Text(
            if (isRegister) "Create your account." else "Attendance, without the roll call.",
            fontSize = 25.sp,
            lineHeight = 31.sp,
            fontWeight = FontWeight.Bold
        )
        Spacer(Modifier.height(8.dp))
        Text(
            "Register your phone once. ProxyProof connects each attendance session to its room.",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 14.sp,
            lineHeight = 20.sp
        )
        Spacer(Modifier.height(22.dp))

        PPPanel {
            Text("SERVER CONNECTION", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.secondary, letterSpacing = 1.2.sp)
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = apiBase,
                onValueChange = onApiBaseChange,
                modifier = Modifier.fillMaxWidth(),
                label = { Text("API server URL") },
                placeholder = { Text("http://192.168.1.10:8000") },
                singleLine = true
            )
            Spacer(Modifier.height(6.dp))
            Text(
                "Emulator default: 10.0.2.2. On your phone, enter your laptop's Wi-Fi IPv4 address. Keep the backend running.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp,
                lineHeight = 17.sp
            )
            Spacer(Modifier.height(18.dp))
            HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.5f))
            Spacer(Modifier.height(18.dp))
            Text(if (isRegister) "CREATE ACCOUNT" else "SIGN IN", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.secondary, letterSpacing = 1.2.sp)
            Spacer(Modifier.height(10.dp))
            if (isRegister) {
                OutlinedTextField(
                    value = displayName,
                    onValueChange = { displayName = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Your name") },
                    singleLine = true
                )
                Spacer(Modifier.height(10.dp))
                Text("Account type", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(
                        selected = selectedRole == "student",
                        onClick = { selectedRole = "student" },
                        label = { Text("Student") }
                    )
                    FilterChip(
                        selected = selectedRole == "organiser",
                        onClick = { selectedRole = "organiser" },
                        label = { Text("Organiser") }
                    )
                }
                if (selectedRole == "organiser") {
                    OutlinedTextField(
                        value = inviteCode,
                        onValueChange = { inviteCode = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Organiser invite code") },
                        singleLine = true
                    )
                    Spacer(Modifier.height(10.dp))
                }
            }
            OutlinedTextField(
                value = username,
                onValueChange = { username = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Username") },
                singleLine = true
            )
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Password") },
                visualTransformation = PasswordVisualTransformation(),
                singleLine = true
            )
            if (message.isNotBlank()) {
                Spacer(Modifier.height(12.dp))
                Text(message, color = MaterialTheme.colorScheme.error, fontSize = 13.sp, lineHeight = 18.sp)
            }
            Spacer(Modifier.height(16.dp))
            Button(
                onClick = {
                    onClearMessage()
                    onSubmit(isRegister, username, displayName, password, selectedRole, inviteCode)
                },
                enabled = !busy && username.isNotBlank() && password.isNotBlank() &&
                    (!isRegister || (displayName.isNotBlank() && (selectedRole != "organiser" || inviteCode.isNotBlank()))),
                modifier = Modifier.fillMaxWidth().height(52.dp),
                shape = RoundedCornerShape(15.dp)
            ) {
                if (busy) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary
                    )
                } else {
                    Text(if (isRegister) "Create account" else "Sign in", fontWeight = FontWeight.Bold)
                }
            }
            Spacer(Modifier.height(6.dp))
            TextButton(
                onClick = {
                    isRegister = !isRegister
                    onClearMessage()
                },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(if (isRegister) "Already registered? Sign in" else "New here? Create an account")
            }
        }
        Spacer(Modifier.height(18.dp))
        Text(
            "Prototype build · BLE attendance is the next integration stage",
            modifier = Modifier.fillMaxWidth(),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 11.sp
        )
    }
}

@Composable
private fun DashboardScreen(
    apiBase: String,
    token: String,
    username: String,
    displayName: String,
    role: String,
    prefs: android.content.SharedPreferences,
    onLogout: () -> Unit,
    onAuthExpired: () -> Unit
) {
    val scope = rememberCoroutineScope()
    val isOrganiser = role == "organiser"
    val context = LocalContext.current
    val lifecycleOwner = context as? LifecycleOwner
    val advertiser = remember(context) { BleAdvertiser(context) }
    val scanner = remember(context) { BleScanner(context) }
    var bleMessage by remember { mutableStateOf("BLE attendance is stopped.") }
    var isBroadcasting by remember { mutableStateOf(false) }
    var isScanning by remember { mutableStateOf(false) }
    var selectedBroadcastSessionId by remember { mutableStateOf("") }
    var pendingBleAction by remember { mutableStateOf("") }
    var blePermissionsGranted by remember { mutableStateOf(hasRequiredBlePermissions(context)) }
    val observationsByTag = remember { mutableMapOf<String, MutableList<BleObservation>>() }
    val successfulTags = remember { mutableSetOf<String>() }
    val lastAttemptByTag = remember { mutableMapOf<String, Long>() }
    val blePermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { _ ->
        blePermissionsGranted = hasRequiredBlePermissions(context)
        if (!blePermissionsGranted) {
            bleMessage = "Nearby-device permission was denied. Allow Bluetooth access in Settings and retry."
            pendingBleAction = ""
        } else {
            when (pendingBleAction) {
                "scan" -> isScanning = true
                "advertise" -> isBroadcasting = true
            }
            pendingBleAction = ""
        }
    }
    DisposableEffect(lifecycleOwner, advertiser, scanner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) {
                // Keep BLE foreground-only; background attendance is not promised.
                advertiser.stop()
                scanner.stop()
                isBroadcasting = false
                isScanning = false
                bleMessage = "BLE paused when ProxyProof left the foreground. Return and start it again when ready."
            }
        }
        lifecycleOwner?.lifecycle?.addObserver(observer)
        onDispose {
            lifecycleOwner?.lifecycle?.removeObserver(observer)
            advertiser.stop()
            scanner.stop()
        }
    }
    var rooms by remember { mutableStateOf(emptyList<RoomItem>()) }
    var enrolledRoomIds by remember { mutableStateOf(emptySet<Int>()) }
    var sessions by remember { mutableStateOf(emptyList<SessionItem>()) }
    var history by remember { mutableStateOf(emptyList<HistoryItem>()) }
    var attendancePercentage by remember { mutableStateOf(0.0) }
    var totalEligible by remember { mutableStateOf(0) }
    var totalPresent by remember { mutableStateOf(0) }
    var loading by remember { mutableStateOf(false) }
    var busyAction by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var pendingCsvContent by remember { mutableStateOf<String?>(null) }
    var pendingCsvFilename by remember { mutableStateOf("proxyproof-attendance.csv") }
    val csvDocumentLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("text/csv")
    ) { uri ->
        val csv = pendingCsvContent
        if (uri == null || csv == null) {
            message = "CSV export cancelled."
        } else {
            scope.launch(Dispatchers.IO) {
                val result = runCatching {
                    context.contentResolver.openOutputStream(uri)?.use { output ->
                        output.write(csv.toByteArray(Charsets.UTF_8))
                    } ?: error("Could not open the selected document.")
                }
                scope.launch(Dispatchers.Main.immediate) {
                    message = if (result.isSuccess) {
                        "Attendance CSV saved."
                    } else {
                        result.exceptionOrNull()?.message ?: "Could not save the CSV."
                    }
                    pendingCsvContent = null
                }
            }
        }
    }
    var building by remember { mutableStateOf("AB1") }
    var roomCode by remember { mutableStateOf("") }
    var roomName by remember { mutableStateOf("") }
    var subject by remember { mutableStateOf("Engineering Mathematics") }
    var scheduledStartText by remember {
        mutableStateOf(OffsetDateTime.now().format(DateTimeFormatter.ISO_OFFSET_DATE_TIME))
    }
    var selectedRoomId by remember { mutableStateOf(0) }
    var roomMenuExpanded by remember { mutableStateOf(false) }
    var broadcastMenuExpanded by remember { mutableStateOf(false) }
    var selectedRosterSession by remember { mutableStateOf("") }
    var roster by remember { mutableStateOf(emptyList<RosterItem>()) }
    var rosterBusy by remember { mutableStateOf(false) }
    val deviceKey = remember {
        prefs.getString("device_key", null) ?: UUID.randomUUID().toString().also {
            prefs.edit().putString("device_key", it).apply()
        }
    }
    var deviceRegistered by remember(username) {
        mutableStateOf(
            prefs.getString("device_registered_username", null) == username
        )
    }

    suspend fun loadData() {
        loading = true
        try {
            rooms = parseRooms(JSONArray(ApiClient.request(apiBase, "GET", "/rooms", token)))
            if (selectedRoomId == 0 || rooms.none { it.id == selectedRoomId }) {
                selectedRoomId = rooms.firstOrNull()?.id ?: 0
            }
            if (isOrganiser) {
                enrolledRoomIds = emptySet()
                history = emptyList()
                attendancePercentage = 0.0
                totalEligible = 0
                totalPresent = 0
            } else {
                enrolledRoomIds = parseRooms(JSONArray(ApiClient.request(apiBase, "GET", "/rooms/my", token)))
                    .map { it.id }.toSet()
            }
            sessions = parseSessions(JSONArray(ApiClient.request(apiBase, "GET", "/sessions/active", token)))
            if (!isOrganiser) {
                val historyObject = JSONObject(ApiClient.request(apiBase, "GET", "/attendance/me", token))
                history = parseHistory(historyObject.optJSONArray("items") ?: JSONArray())
                attendancePercentage = historyObject.optDouble("percentage", 0.0)
                totalEligible = historyObject.optInt("eligible_sessions", 0)
                totalPresent = historyObject.optInt("present_sessions", 0)
            }
            message = "Synced with ProxyProof API."
        } catch (error: Exception) {
            if (isAuthenticationRejected(error)) {
                onAuthExpired()
                return
            }
            message = error.message ?: "Could not load data from the backend."
        } finally {
            loading = false
        }
    }

    suspend fun prepareCsvExport(sessionId: String) {
        try {
            val csv = ApiClient.request(
                apiBase,
                "GET",
                "/attendance/export.csv?session_id=$sessionId",
                token
            )
            pendingCsvContent = csv
            pendingCsvFilename = "proxyproof-attendance-${sessionId.take(8)}.csv"
            csvDocumentLauncher.launch(pendingCsvFilename)
            message = "Choose where to save the attendance CSV."
        } catch (error: Exception) {
            if (isAuthenticationRejected(error)) {
                onAuthExpired()
                return
            }
            message = error.message ?: "Could not export attendance."
        }
    }

    suspend fun loadRoster(sessionId: String) {
        rosterBusy = true
        try {
            val response = JSONObject(
                ApiClient.request(apiBase, "GET", "/sessions/$sessionId/attendance", token)
            )
            roster = parseRoster(response.optJSONArray("records") ?: JSONArray())
            selectedRosterSession = sessionId
            message = "Roster updated."
        } catch (error: Exception) {
            if (isAuthenticationRejected(error)) {
                onAuthExpired()
                return
            }
            message = error.message ?: "Could not load the attendance roster."
        } finally {
            rosterBusy = false
        }
    }

    LaunchedEffect(apiBase, token, role) {
        loadData()
    }

    LaunchedEffect(sessions) {
        if (selectedBroadcastSessionId.isBlank() || sessions.none { it.id == selectedBroadcastSessionId }) {
            isBroadcasting = false
            selectedBroadcastSessionId = sessions.firstOrNull()?.id.orEmpty()
        }
    }

    LaunchedEffect(isOrganiser, selectedRosterSession, apiBase, token) {
        if (!isOrganiser || selectedRosterSession.isBlank()) return@LaunchedEffect
        while (isActive) {
            delay(4_000)
            try {
                val response = JSONObject(
                    ApiClient.request(
                        apiBase,
                        "GET",
                        "/sessions/$selectedRosterSession/attendance",
                        token
                    )
                )
                roster = parseRoster(response.optJSONArray("records") ?: JSONArray())
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (isAuthenticationRejected(error)) {
                    onAuthExpired()
                    return@LaunchedEffect
                }
                // Preserve the last roster on a transient polling failure; manual refresh remains available.
            }
        }
    }

    LaunchedEffect(isOrganiser, isBroadcasting, selectedBroadcastSessionId, apiBase, token) {
        if (!isOrganiser || !isBroadcasting || selectedBroadcastSessionId.isBlank()) {
            advertiser.stop()
            return@LaunchedEffect
        }
        var lastPayload: ByteArray? = null
        bleMessage = "Connecting to the session token endpoint…"
        try {
            while (isActive) {
                val json = JSONObject(
                    ApiClient.request(
                        apiBase,
                        "GET",
                        "/sessions/$selectedBroadcastSessionId/current-token",
                        token
                    )
                )
                val payload = BleProtocol.encode(
                    json.getString("session_tag"),
                    json.getString("token")
                )
                if (lastPayload == null || !lastPayload!!.contentEquals(payload)) {
                    advertiser.start(payload) { status ->
                        scope.launch(Dispatchers.Main.immediate) { bleMessage = status }
                    }
                    lastPayload = payload
                }
                delay(5_000)
            }
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            if (isAuthenticationRejected(error)) {
                onAuthExpired()
                return@LaunchedEffect
            }
            bleMessage = error.message ?: "Could not start BLE advertising."
            isBroadcasting = false
        } finally {
            advertiser.stop()
        }
    }

    LaunchedEffect(isScanning, apiBase, token, deviceRegistered, sessions) {
        if (!isScanning) {
            scanner.stop()
            return@LaunchedEffect
        }
        if (!deviceRegistered) {
            bleMessage = "Register this phone before scanning for attendance."
            isScanning = false
            return@LaunchedEffect
        }
        if (sessions.isEmpty()) {
            bleMessage = "There are no eligible active sessions in your enrolled rooms."
            isScanning = false
            return@LaunchedEffect
        }
        if (!hasRequiredBlePermissions(context)) {
            bleMessage = "Nearby-device permission is required to scan."
            isScanning = false
            return@LaunchedEffect
        }

        observationsByTag.clear()
        bleMessage = "Scanning for nearby ProxyProof sessions…"
        scanner.start(
            onObservation = { observation ->
                scope.launch(Dispatchers.Main.immediate) {
                    if (!isScanning || observation.sessionTag in successfulTags) return@launch
                    val now = observation.elapsedRealtimeMs
                    val recent = observationsByTag.getOrPut(observation.sessionTag) { mutableListOf() }
                    recent.removeAll { now - it.elapsedRealtimeMs > 6_000 }
                    recent.add(observation)
                    if (recent.size > 30) recent.removeAt(0)

                    val recentCandidates = observationsByTag.mapNotNull { (tag, values) ->
                        val window = values.filter { now - it.elapsedRealtimeMs <= 4_000 }
                        if (window.size < 2) null else {
                            tag to window
                        }
                    }
                    val stableCandidates = recentCandidates.filter { (_, values) ->
                        values.size >= 4 &&
                            values.last().elapsedRealtimeMs - values.first().elapsedRealtimeMs >= 3_000 &&
                            now - values.last().elapsedRealtimeMs <= 1_500
                    }
                    if (stableCandidates.size >= 2) {
                        val ranked = stableCandidates.map { (tag, values) ->
                            tag to values.map { it.rssi }.average()
                        }.sortedByDescending { it.second }
                        if (kotlin.math.abs(ranked[0].second - ranked[1].second) <= 8.0) {
                            scanner.stop()
                            isScanning = false
                            bleMessage = "Ambiguous room: two sessions have similar signal strength. Move closer to the intended classroom and scan again."
                            return@launch
                        }
                    }

                    val candidate = stableCandidates.maxByOrNull { (_, values) ->
                        values.map { it.rssi }.average()
                    } ?: return@launch
                    val tag = candidate.first
                    if (tag in successfulTags) return@launch
                    val lastAttempt = lastAttemptByTag[tag]
                    if (lastAttempt != null && now - lastAttempt < 10_000) return@launch
                    lastAttemptByTag[tag] = now
                    val latest = candidate.second.last()
                    bleMessage = "Validating presence for a nearby room…"
                    try {
                        val result = JSONObject(
                            ApiClient.request(
                                apiBase,
                                "POST",
                                "/attendance/ble",
                                token,
                                JSONObject()
                                    .put("session_tag", latest.sessionTag)
                                    .put("token", latest.token)
                                    .put("rssi", latest.rssi)
                            )
                        )
                        successfulTags.add(tag)
                        scanner.stop()
                        isScanning = false
                        bleMessage = "Attendance confirmed: ${result.optString("subject_label")} · ${result.optString("room_name")}."
                        loadData()
                    } catch (error: Exception) {
                        if (isAuthenticationRejected(error)) {
                            scanner.stop()
                            isScanning = false
                            onAuthExpired()
                            return@launch
                        }
                        bleMessage = error.message ?: "Attendance could not be verified by the server."
                        val text = error.message.orEmpty().lowercase(Locale.getDefault())
                        if (text.contains("not registered for this room") ||
                            text.contains("already marked") ||
                            text.contains("session is closed") ||
                            text.contains("outside the 15-minute")
                        ) {
                            scanner.stop()
                            isScanning = false
                        }
                    }
                }
            },
            onStatus = { status ->
                scope.launch(Dispatchers.Main.immediate) {
                    bleMessage = status
                    if (status.contains("failed", true) ||
                        status.contains("turned off", true) ||
                        status.contains("not available", true) ||
                        status.contains("permission is missing", true)
                    ) {
                        isScanning = false
                    }
                }
            }
        )
        try {
            awaitCancellation()
        } finally {
            scanner.stop()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp, vertical = 20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(RoundedCornerShape(14.dp))
                    .background(MaterialTheme.colorScheme.primary),
                contentAlignment = Alignment.Center
            ) {
                Text("P", color = MaterialTheme.colorScheme.onPrimary, fontSize = 24.sp, fontWeight = FontWeight.Black)
            }
            Spacer(Modifier.width(10.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text("ProxyProof", fontSize = 23.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.6).sp)
                Text(if (isOrganiser) "ORGANISER CONSOLE" else "STUDENT SPACE", color = MaterialTheme.colorScheme.secondary, fontSize = 10.sp, letterSpacing = 1.7.sp, fontWeight = FontWeight.SemiBold)
            }
            TextButton(onClick = onLogout) { Text("Sign out") }
        }

        PPPanel {
            Text("HELLO, ${(displayName.ifBlank { username }).uppercase(Locale.getDefault())}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp, letterSpacing = 1.2.sp)
            Spacer(Modifier.height(5.dp))
            Text(
                if (isOrganiser) "Take attendance." else "You're in the right place.",
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.height(5.dp))
            Text(
                if (isOrganiser) "Create room sessions and manage your class roster." else "Your room sessions, attendance and history in one place.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 13.sp,
                lineHeight = 18.sp
            )
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                StatusPill(text = if (loading) "SYNCING" else "API CONNECTED", positive = !loading)
                TextButton(onClick = { scope.launch { loadData() } }, enabled = !loading) {
                    Text(if (loading) "Syncing…" else "Refresh")
                }
            }
        }

        if (message.isNotBlank()) {
            Text(
                message,
                color = if (message.startsWith("HTTP") || message.contains("failed", true) || message.contains("could not", true)) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp,
                lineHeight = 17.sp
            )
        }

        if (isOrganiser) {
            PPPanel {
                SectionHeading("CREATE A ROOM", "Add the rooms where classes take place.")
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(value = building, onValueChange = { building = it }, modifier = Modifier.fillMaxWidth(), label = { Text("Building / block") }, singleLine = true)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = roomCode, onValueChange = { roomCode = it }, modifier = Modifier.fillMaxWidth(), label = { Text("Room code, e.g. 301") }, singleLine = true)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = roomName, onValueChange = { roomName = it }, modifier = Modifier.fillMaxWidth(), label = { Text("Display name, e.g. AB1-301") }, singleLine = true)
                Spacer(Modifier.height(12.dp))
                Button(
                    onClick = {
                        scope.launch {
                            busyAction = true
                            try {
                                val name = roomName.ifBlank { "${building.trim()}-${roomCode.trim()}" }
                                val body = JSONObject()
                                    .put("building", building.trim())
                                    .put("room_code", roomCode.trim())
                                    .put("display_name", name.trim())
                                ApiClient.request(apiBase, "POST", "/rooms", token, body)
                                roomCode = ""
                                roomName = ""
                                message = "Room created."
                                loadData()
                            } catch (error: Exception) {
                                message = error.message ?: "Room creation failed."
                            } finally {
                                busyAction = false
                            }
                        }
                    },
                    enabled = !busyAction && building.isNotBlank() && roomCode.isNotBlank(),
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    shape = RoundedCornerShape(14.dp)
                ) {
                    Text(if (busyAction) "Working…" else "＋  Create room")
                }
            }

            PPPanel {
                SectionHeading("START ATTENDANCE", "The automatic window ends 15 minutes after the scheduled start.")
                Spacer(Modifier.height(12.dp))
                Box {
                    OutlinedButton(
                        onClick = { roomMenuExpanded = true },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = rooms.isNotEmpty(),
                        shape = RoundedCornerShape(13.dp)
                    ) {
                        Text(
                            rooms.firstOrNull { it.id == selectedRoomId }?.displayName ?: "Create a room first",
                            modifier = Modifier.weight(1f),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        Text("⌄")
                    }
                    DropdownMenu(expanded = roomMenuExpanded, onDismissRequest = { roomMenuExpanded = false }) {
                        rooms.forEach { room ->
                            DropdownMenuItem(
                                text = { Text(room.displayName) },
                                onClick = { selectedRoomId = room.id; roomMenuExpanded = false }
                            )
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = subject, onValueChange = { subject = it }, modifier = Modifier.fillMaxWidth(), label = { Text("Subject / class") }, singleLine = true)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = scheduledStartText,
                    onValueChange = { scheduledStartText = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Scheduled start (ISO 8601 with offset)") },
                    placeholder = { Text("2026-10-13T08:00:00+05:30") },
                    supportingText = { Text("The server closes automatic attendance 15 minutes after this time.") },
                    singleLine = true
                )
                Spacer(Modifier.height(12.dp))
                Button(
                    onClick = {
                        scope.launch {
                            busyAction = true
                            try {
                                val body = JSONObject()
                                    .put("room_id", selectedRoomId)
                                    .put("subject_label", subject.trim())
                                    .put("scheduled_start_at", scheduledStartText.trim())
                                val created = JSONObject(ApiClient.request(apiBase, "POST", "/sessions", token, body))
                                message = "Attendance session created for ${created.optString("room_name")}. Start its BLE broadcast below."
                                loadData()
                            } catch (error: Exception) {
                                message = error.message ?: "Could not start the session."
                            } finally {
                                busyAction = false
                            }
                        }
                    },
                    enabled = !busyAction && selectedRoomId > 0 && subject.isNotBlank() && scheduledStartText.isNotBlank(),
                    modifier = Modifier.fillMaxWidth().height(50.dp),
                    shape = RoundedCornerShape(14.dp)
                ) {
                    Text("Start attendance session")
                }
            }

            PPPanel {
                SectionHeading("BLE BROADCAST", "Advertise the rotating session token from this organiser phone.")
                Spacer(Modifier.height(8.dp))
                if (sessions.isEmpty()) {
                    EmptyState("No eligible session to broadcast.", "Start a session during its scheduled attendance window.")
                } else {
                    Box {
                        OutlinedButton(
                            onClick = { broadcastMenuExpanded = !broadcastMenuExpanded },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(13.dp)
                        ) {
                            val chosen = sessions.firstOrNull { it.id == selectedBroadcastSessionId }
                            Text(
                                chosen?.let { "${it.roomName} · ${it.subject}" } ?: "Select active session",
                                modifier = Modifier.weight(1f),
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                            Text("⌄")
                        }
                        DropdownMenu(
                            expanded = broadcastMenuExpanded,
                            onDismissRequest = { broadcastMenuExpanded = false }
                        ) {
                            sessions.forEach { session ->
                                DropdownMenuItem(
                                    text = { Text("${session.roomName} · ${session.subject}") },
                                    onClick = {
                                        selectedBroadcastSessionId = session.id
                                        broadcastMenuExpanded = false
                                    }
                                )
                            }
                        }
                    }
                    Spacer(Modifier.height(10.dp))
                    Button(
                        onClick = {
                            if (isBroadcasting) {
                                isBroadcasting = false
                                advertiser.stop()
                                bleMessage = "BLE broadcast stopped."
                            } else if (!advertiser.isSupported()) {
                                bleMessage = "This phone cannot advertise BLE. Use the clearly labelled manual attendance fallback."
                            } else if (!hasRequiredBlePermissions(context)) {
                                pendingBleAction = "advertise"
                                blePermissionLauncher.launch(requiredBlePermissions())
                            } else {
                                isBroadcasting = true
                            }
                        },
                        enabled = selectedBroadcastSessionId.isNotBlank(),
                        modifier = Modifier.fillMaxWidth().height(48.dp),
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (isBroadcasting) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary
                        )
                    ) {
                        Text(if (isBroadcasting) "Stop BLE broadcast" else "Start BLE broadcast")
                    }
                    Spacer(Modifier.height(6.dp))
                }
                Text(
                    bleMessage,
                    color = if (bleMessage.contains("failed", true) || bleMessage.contains("missing", true) ||
                        bleMessage.contains("cannot", true) || bleMessage.contains("unavailable", true)
                    ) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    lineHeight = 17.sp
                )
                Spacer(Modifier.height(5.dp))
                Text(
                    "Foreground only. Prototype manufacturer ID 0xFFFF is development-only and must be replaced before public release.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                    lineHeight = 15.sp
                )
            }

            PPPanel {
                SectionHeading("LIVE SESSIONS", "Sessions are isolated by room and session ID.")
                Spacer(Modifier.height(10.dp))
                if (sessions.isEmpty()) {
                    EmptyState("No attendance window is currently open.", "Start a session at its scheduled class time.")
                } else {
                    sessions.forEach { session ->
                        SessionCard(
                            session = session,
                            organiser = true,
                            onClose = {
                                scope.launch {
                                    try {
                                        ApiClient.request(apiBase, "POST", "/sessions/${session.id}/close", token)
                                        message = "Session closed."
                                        loadData()
                                    } catch (error: Exception) {
                                        message = error.message ?: "Could not close session."
                                    }
                                }
                            },
                            onViewRoster = {
                                scope.launch { loadRoster(session.id) }
                            }
                        )
                        Spacer(Modifier.height(8.dp))
                    }
                }
            }

            if (selectedRosterSession.isNotBlank()) {
                PPPanel {
                    SectionHeading("ATTENDANCE ROSTER", "Manual changes are labelled and recorded separately from BLE.")
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(
                        onClick = {
                            scope.launch { prepareCsvExport(selectedRosterSession) }
                        },
                        enabled = selectedRosterSession.isNotBlank() && !rosterBusy,
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(13.dp)
                    ) {
                        Text("Export this session as CSV")
                    }
                    Spacer(Modifier.height(8.dp))
                    if (rosterBusy) {
                        CircularProgressIndicator(modifier = Modifier.size(24.dp), strokeWidth = 2.dp)
                    } else if (roster.isEmpty()) {
                        EmptyState("No students are enrolled in this room yet.", "Students can register for this room from their account.")
                    } else {
                        roster.forEach { student ->
                            Row(
                                modifier = Modifier.fillMaxWidth().padding(vertical = 7.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(student.displayName, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                                    Text("${student.username} · ${student.status ?: "Not marked"}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                                }
                                TextButton(onClick = {
                                    scope.launch {
                                        try {
                                            ApiClient.request(
                                                apiBase, "POST",
                                                "/sessions/$selectedRosterSession/attendance/manual",
                                                token,
                                                JSONObject().put("student_id", student.studentId).put("status", "present")
                                            )
                                            loadRoster(selectedRosterSession)
                                            message = "Manual attendance saved."
                                        } catch (error: Exception) {
                                            message = error.message ?: "Could not update attendance."
                                        }
                                    }
                                }) { Text("Present") }
                                TextButton(onClick = {
                                    scope.launch {
                                        try {
                                            ApiClient.request(
                                                apiBase, "POST",
                                                "/sessions/$selectedRosterSession/attendance/manual",
                                                token,
                                                JSONObject().put("student_id", student.studentId).put("status", "absent")
                                            )
                                            loadRoster(selectedRosterSession)
                                            message = "Manual attendance saved."
                                        } catch (error: Exception) {
                                            message = error.message ?: "Could not update attendance."
                                        }
                                    }
                                }) { Text("Absent", color = MaterialTheme.colorScheme.error) }
                            }
                            HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.35f))
                        }
                    }
                }
            }

            PPPanel {
                SectionHeading("ROOM DIRECTORY", "Room IDs stay distinct even when sessions overlap.")
                Spacer(Modifier.height(10.dp))
                if (rooms.isEmpty()) {
                    EmptyState("No rooms yet.", "Create your first room above.")
                } else {
                    rooms.forEach { RoomRow(it, detail = "${it.building} · Room ${it.roomCode}", action = null) }
                }
            }
        } else {
            PPPanel {
                SectionHeading("YOUR ATTENDANCE", "Attendance is calculated from completed sessions in your enrolled rooms.")
                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    MetricBlock("$attendancePercentage%", "ATTENDANCE", Modifier.weight(1f))
                    MetricBlock("$totalPresent / $totalEligible", "PRESENT", Modifier.weight(1f))
                }
                Spacer(Modifier.height(8.dp))
                Text("Automatic attendance uses foreground BLE discovery and must be confirmed by the server. Keep this screen open and Bluetooth enabled.", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp, lineHeight = 17.sp)
                Spacer(Modifier.height(12.dp))
                Button(
                    onClick = {
                        scope.launch {
                            busyAction = true
                            try {
                                ApiClient.request(
                                    apiBase, "POST", "/devices/register", token,
                                    JSONObject().put("device_key", deviceKey)
                                )
                                deviceRegistered = true
                                prefs.edit()
                                    .putString("device_registered_username", username)
                                    .remove("device_registered")
                                    .apply()
                                message = "This installation is registered to your account."
                            } catch (error: Exception) {
                                message = error.message ?: "Device registration failed."
                            } finally {
                                busyAction = false
                            }
                        }
                    },
                    enabled = !busyAction,
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    shape = RoundedCornerShape(14.dp)
                ) {
                    Text(if (deviceRegistered) "✓  Phone registered in this session" else "Register this phone")
                }
                Spacer(Modifier.height(6.dp))
                Text("Installation ID: ${deviceKey.take(8)}…", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
            }

            PPPanel {
                SectionHeading("BLE ATTENDANCE", "Keep this screen open while the app looks for your enrolled room's beacon.")
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    StatusPill(
                        text = if (isScanning) "SCANNING" else "STOPPED",
                        positive = isScanning
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        if (!blePermissionsGranted) "Nearby-device permission required"
                        else if (!deviceRegistered) "Register this phone first"
                        else "Foreground scan only",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp
                    )
                }
                Spacer(Modifier.height(10.dp))
                Button(
                    onClick = {
                        if (isScanning) {
                            isScanning = false
                            scanner.stop()
                            bleMessage = "BLE scanning stopped."
                        } else if (!deviceRegistered) {
                            bleMessage = "Register this phone before scanning for attendance."
                        } else if (sessions.isEmpty()) {
                            bleMessage = "No eligible sessions are active in your enrolled rooms."
                        } else if (!scanner.isSupported()) {
                            bleMessage = "This phone does not support BLE scanning."
                        } else if (!hasRequiredBlePermissions(context)) {
                            pendingBleAction = "scan"
                            blePermissionLauncher.launch(requiredBlePermissions())
                        } else {
                            observationsByTag.clear()
                            successfulTags.clear()
                            lastAttemptByTag.clear()
                            isScanning = true
                        }
                    },
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    shape = RoundedCornerShape(14.dp),
                    enabled = isScanning || (deviceRegistered && sessions.isNotEmpty())
                ) {
                    Text(if (isScanning) "Stop scanning" else "Start attendance scan")
                }
                Spacer(Modifier.height(8.dp))
                Text(
                    bleMessage,
                    color = if (bleMessage.contains("failed", true) || bleMessage.contains("could not", true) ||
                        bleMessage.contains("denied", true) || bleMessage.contains("ambiguous", true)
                    ) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    lineHeight = 17.sp
                )
                Spacer(Modifier.height(5.dp))
                Text(
                    "The backend validates the rotating token, registered device, enrolment, session and 15-minute cutoff. Signal strength is only a heuristic.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                    lineHeight = 15.sp
                )
            }

            PPPanel {
                SectionHeading("YOUR ROOMS", "Join the rooms used for your scheduled classes.")
                Spacer(Modifier.height(8.dp))
                if (rooms.isEmpty()) {
                    EmptyState("No rooms have been created.", "Ask the organiser to add your classroom.")
                } else {
                    rooms.forEach { room ->
                        RoomRow(
                            room = room,
                            detail = "${room.building} · Room ${room.roomCode}",
                            action = if (room.id in enrolledRoomIds) null else {
                                {
                                    scope.launch {
                                        try {
                                            ApiClient.request(apiBase, "POST", "/rooms/${room.id}/enroll", token)
                                            enrolledRoomIds = enrolledRoomIds + room.id
                                            message = "Registered for ${room.displayName}."
                                            loadData()
                                        } catch (error: Exception) {
                                            message = error.message ?: "Room registration failed."
                                        }
                                    }
                                }
                            },
                            actionLabel = if (room.id in enrolledRoomIds) "Enrolled" else "Join"
                        )
                    }
                }
            }

            PPPanel {
                SectionHeading("ACTIVE CLASS SESSIONS", "Only sessions for rooms you've joined appear here.")
                Spacer(Modifier.height(8.dp))
                if (sessions.isEmpty()) {
                    EmptyState("Nothing active in your rooms right now.", "Attendance is open only from the scheduled start until 15 minutes later.")
                } else {
                    sessions.forEach { session ->
                        SessionCard(session, organiser = false, onClose = null, onViewRoster = null)
                        Spacer(Modifier.height(8.dp))
                    }
                }
            }

            PPPanel {
                SectionHeading("RECENT ATTENDANCE", "A record for each completed session.")
                Spacer(Modifier.height(8.dp))
                if (history.isEmpty()) {
                    EmptyState("No attendance records yet.", "Your records will appear after attendance is marked.")
                } else {
                    history.take(10).forEach { item ->
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                modifier = Modifier.size(36.dp).clip(CircleShape)
                                    .background(if (item.status == "present") MaterialTheme.colorScheme.primary.copy(alpha = 0.15f) else MaterialTheme.colorScheme.surfaceVariant),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(if (item.status == "present") "✓" else "–", color = if (item.status == "present") MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant, fontWeight = FontWeight.Bold)
                            }
                            Spacer(Modifier.width(10.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(item.subject, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                                Text("${item.roomName} · ${formatLocalTime(item.markedAt)}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                            }
                            StatusPill(item.status.uppercase(), item.status == "present")
                        }
                        HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.35f))
                    }
                }
            }
        }

        PPPanel {
            Text("PROTOTYPE BUILD", color = MaterialTheme.colorScheme.secondary, fontSize = 10.sp, letterSpacing = 1.4.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(6.dp))
            Text(
                "BLE signal strength is a rough proximity check, not proof that someone crossed the classroom door.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp,
                lineHeight = 17.sp
            )
            Spacer(Modifier.height(4.dp))
            Text("Server: $apiBase", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
        }
        Spacer(Modifier.height(12.dp))
    }
}

@Composable
private fun PPPanel(content: @Composable ColumnScope.() -> Unit) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(21.dp),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 1.dp,
        shadowElevation = 0.dp
    ) {
        Column(modifier = Modifier.padding(16.dp), content = content)
    }
}

@Composable
private fun SectionHeading(title: String, subtitle: String) {
    Text(title, color = MaterialTheme.colorScheme.secondary, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.45.sp)
    Spacer(Modifier.height(5.dp))
    Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp, lineHeight = 17.sp)
}

@Composable
private fun StatusPill(text: String, positive: Boolean) {
    val color = if (positive) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
    Surface(shape = CircleShape, color = color.copy(alpha = 0.12f)) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
            color = color,
            fontSize = 9.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 0.5.sp
        )
    }
}

@Composable
private fun MetricBlock(value: String, label: String, modifier: Modifier = Modifier) {
    Surface(modifier = modifier, shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.surfaceVariant) {
        Column(modifier = Modifier.padding(14.dp)) {
            Text(value, color = MaterialTheme.colorScheme.primary, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(3.dp))
            Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
        }
    }
}

@Composable
private fun EmptyState(title: String, subtitle: String) {
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text("◌", color = MaterialTheme.colorScheme.secondary, fontSize = 27.sp)
        Spacer(Modifier.height(4.dp))
        Text(title, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
        Spacer(Modifier.height(4.dp))
        Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp, lineHeight = 16.sp)
    }
}

@Composable
private fun RoomRow(
    room: RoomItem,
    detail: String,
    action: (() -> Unit)?,
    actionLabel: String = "Join"
) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier.size(38.dp).clip(RoundedCornerShape(12.dp)).background(MaterialTheme.colorScheme.surfaceVariant),
            contentAlignment = Alignment.Center
        ) {
            Text("⌂", color = MaterialTheme.colorScheme.secondary, fontSize = 22.sp)
        }
        Spacer(Modifier.width(10.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(room.displayName, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
            Text(detail, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
        }
        if (action != null) {
            OutlinedButton(onClick = action, shape = RoundedCornerShape(12.dp)) { Text(actionLabel) }
        } else if (actionLabel == "Enrolled") {
            StatusPill("ENROLLED", positive = true)
        }
    }
}

@Composable
private fun SessionCard(
    session: SessionItem,
    organiser: Boolean,
    onClose: (() -> Unit)?,
    onViewRoster: (() -> Unit)?
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
    ) {
        Column(modifier = Modifier.padding(13.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(session.subject, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    Spacer(Modifier.height(3.dp))
                    Text(session.roomName, color = MaterialTheme.colorScheme.secondary, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                }
                StatusPill(if (session.attendanceOpen) "OPEN" else session.status.uppercase(), session.attendanceOpen)
            }
            Spacer(Modifier.height(9.dp))
            Text(
                "Started: ${formatLocalTime(session.scheduledStart)}  ·  Deadline: ${formatLocalTime(session.deadline)}",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 11.sp
            )
            if (!organiser) {
                Spacer(Modifier.height(7.dp))
                Text("Detected through the room's session ID once BLE scanning is enabled.", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp, lineHeight = 16.sp)
            } else {
                Spacer(Modifier.height(7.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { onViewRoster?.invoke() }, shape = RoundedCornerShape(11.dp)) { Text("View roster") }
                    TextButton(onClick = { onClose?.invoke() }) { Text("Close session", color = MaterialTheme.colorScheme.error) }
                }
            }
        }
    }
}

private fun parseRooms(array: JSONArray): List<RoomItem> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        add(
            RoomItem(
                id = item.optInt("id"),
                building = item.optString("building"),
                roomCode = item.optString("room_code"),
                displayName = item.optString("display_name")
            )
        )
    }
}

private fun parseSessions(array: JSONArray): List<SessionItem> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        add(
            SessionItem(
                id = item.optString("id"),
                roomId = item.optInt("room_id"),
                roomName = item.optString("room_name"),
                subject = item.optString("subject_label"),
                scheduledStart = item.optString("scheduled_start_at"),
                deadline = item.optString("attendance_deadline"),
                status = item.optString("status", "open"),
                attendanceOpen = item.optBoolean("attendance_open")
            )
        )
    }
}

private fun parseHistory(array: JSONArray): List<HistoryItem> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        add(
            HistoryItem(
                sessionId = item.optString("session_id"),
                roomName = item.optString("room_name"),
                subject = item.optString("subject_label"),
                markedAt = item.optString("marked_at"),
                status = item.optString("status", "absent"),
                method = item.optString("method", "")
            )
        )
    }
}

private fun parseRoster(array: JSONArray): List<RosterItem> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        add(
            RosterItem(
                studentId = item.optInt("student_id"),
                username = item.optString("username"),
                displayName = item.optString("display_name"),
                status = nullableString(item, "status"),
                markedAt = nullableString(item, "marked_at"),
                method = nullableString(item, "method")
            )
        )
    }
}

private fun nullableString(json: JSONObject, key: String): String? {
    if (json.isNull(key)) return null
    return json.optString(key).takeIf { it.isNotBlank() && it != "null" }
}

private fun formatLocalTime(value: String): String {
    return try {
        OffsetDateTime.parse(value)
            .atZoneSameInstant(ZoneId.systemDefault())
            .format(DateTimeFormatter.ofPattern("h:mm a", Locale.getDefault()))
    } catch (_: Exception) {
        value.substringAfter('T', value).take(5)
    }
}
