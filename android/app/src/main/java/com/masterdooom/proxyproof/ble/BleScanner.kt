package com.masterdooom.proxyproof.ble

import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.pm.PackageManager
import android.os.SystemClock

/** One validated ProxyProof advertisement observation. */
data class BleObservation(
    val sessionTag: String,
    val token: String,
    val rssi: Int,
    val elapsedRealtimeMs: Long
)

/**
 * Foreground BLE scanner for the development ProxyProof manufacturer payload.
 * The caller is responsible for permission requests, dwell/ambiguity policy,
 * authenticated attendance submission, and stopping on disposal/backgrounding.
 */
class BleScanner(context: Context) {
    private val appContext = context.applicationContext
    private val manager = appContext.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    private var callback: ScanCallback? = null

    fun isSupported(): Boolean =
        appContext.packageManager.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH_LE) &&
            runCatching { manager.adapter?.bluetoothLeScanner != null }.getOrDefault(false)

    @Synchronized
    fun start(onObservation: (BleObservation) -> Unit, onStatus: (String) -> Unit = {}) {
        stop()
        try {
            val adapter = manager.adapter
            if (adapter == null) {
                onStatus("Bluetooth is not available on this device.")
                return
            }
            if (!adapter.isEnabled) {
                onStatus("Bluetooth is turned off.")
                return
            }
            val scanner = adapter.bluetoothLeScanner
            if (scanner == null) {
                onStatus("The BLE scanner is unavailable.")
                return
            }

            val scanCallback = object : ScanCallback() {
                override fun onScanResult(callbackType: Int, result: ScanResult) {
                    emit(result, onObservation)
                }

                override fun onBatchScanResults(results: MutableList<ScanResult>) {
                    results.forEach { emit(it, onObservation) }
                }

                override fun onScanFailed(errorCode: Int) {
                    synchronized(this@BleScanner) { callback = null }
                    onStatus("BLE scan failed (code $errorCode).")
                }
            }
            val settings = ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
                .setCallbackType(ScanSettings.CALLBACK_TYPE_ALL_MATCHES)
                .build()
            callback = scanCallback
            scanner.startScan(null, settings, scanCallback)
            onStatus("Scanning for nearby ProxyProof sessions.")
        } catch (_: SecurityException) {
            callback = null
            onStatus("Nearby-device permission is missing. Allow Bluetooth access and retry.")
        } catch (_: IllegalStateException) {
            callback = null
            onStatus("Bluetooth is restarting. Wait a moment and retry.")
        }
    }

    private fun emit(result: ScanResult, onObservation: (BleObservation) -> Unit) {
        val bytes = runCatching {
            result.scanRecord?.getManufacturerSpecificData(BleProtocol.DEVELOPMENT_MANUFACTURER_ID)
        }.getOrNull() ?: return
        val payload = BleProtocol.decode(bytes) ?: return
        onObservation(
            BleObservation(
                sessionTag = payload.sessionTag,
                token = payload.token,
                rssi = result.rssi,
                elapsedRealtimeMs = SystemClock.elapsedRealtime()
            )
        )
    }

    @Synchronized
    fun stop() {
        val previous = callback ?: return
        callback = null
        try {
            manager.adapter?.bluetoothLeScanner?.stopScan(previous)
        } catch (_: SecurityException) {
            // Permission may be revoked while scanning; cleanup stays safe.
        } catch (_: IllegalStateException) {
            // The adapter can reset or shut down between start and stop.
        }
    }
}
