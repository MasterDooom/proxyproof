package com.masterdooom.proxyproof.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val ProxyColorScheme = darkColorScheme(
    primary = ProxyEmerald,
    onPrimary = ProxyBlack,
    secondary = ProxyCyan,
    onSecondary = ProxyBlack,
    tertiary = ProxyCyan,
    background = ProxyBackground,
    onBackground = ProxyText,
    surface = ProxySurface,
    onSurface = ProxyText,
    surfaceVariant = ProxySurfaceVariant,
    onSurfaceVariant = ProxyMuted,
    outline = ProxyOutline,
    error = ProxyError
)

@Composable
fun ProxyProofTheme(
    darkTheme: Boolean = true,
    dynamicColor: Boolean = false,
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = ProxyColorScheme,
        typography = Typography,
        content = content
    )
}
