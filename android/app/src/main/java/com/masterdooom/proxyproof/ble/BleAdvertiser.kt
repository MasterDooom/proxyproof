package com.masterdooom.proxyproof.ble

import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.content.Context
import android.content.pm.PackageManager

/**
 * Manages a foreground-only legacy BLE advertisement. The caller owns lifecycle,
 * permissions, token refresh, and must call stop() when the session is no longer
 * eligible. This class never puts identity or bearer credentials into the packet.
 */
class BleAdvertiser(context: Context) {
    private val appContext = context.applicationContext
    private val manager = appContext.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    private var activeCallback: AdvertiseCallback? = null

    fun isSupported(): Boolean {
        if (!appContext.packageManager.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH_LE)) {
            return false
        }
        val adapter = runCatching { manager.adapter }.getOrNull() ?: return false
        return runCatching { adapter.isEnabled && adapter.isMultipleAdvertisementSupported && adapter.bluetoothLeAdvertiser != null }
            .getOrDefault(false)
    }

    @Synchronized
    fun start(payload: ByteArray, onStatus: (String) -> Unit = {}) {
        require(payload.size == BleProtocol.PAYLOAD_BYTES) { "Invalid ProxyProof BLE payload size." }
        stop()
        try {
            val adapter: BluetoothAdapter = manager.adapter
                ?: run { onStatus("Bluetooth is not available on this device."); return }
            if (!adapter.isEnabled) {
                onStatus("Bluetooth is turned off.")
                return
            }
            if (!adapter.isMultipleAdvertisementSupported) {
                onStatus("This device does not support BLE advertising.")
                return
            }
            val advertiser = adapter.bluetoothLeAdvertiser
                ?: run { onStatus("The BLE advertiser is unavailable."); return }

            val callback = object : AdvertiseCallback() {
                override fun onStartSuccess(settingsInEffect: AdvertiseSettings?) {
                    onStatus("BLE broadcast active.")
                }

                override fun onStartFailure(errorCode: Int) {
                    synchronized(this@BleAdvertiser) { activeCallback = null }
                    onStatus("BLE broadcast failed (code $errorCode).")
                }
            }
            val settings = AdvertiseSettings.Builder()
                .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
                .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_MEDIUM)
                .setConnectable(false)
                .setTimeout(0)
                .build()
            val data = AdvertiseData.Builder()
                .setIncludeDeviceName(false)
                .addManufacturerData(BleProtocol.DEVELOPMENT_MANUFACTURER_ID, payload)
                .build()

            activeCallback = callback
            advertiser.startAdvertising(settings, data, callback)
        } catch (_: SecurityException) {
            activeCallback = null
            onStatus("Bluetooth permission is missing. Allow nearby-device access and retry.")
        } catch (error: IllegalArgumentException) {
            activeCallback = null
            onStatus("BLE payload is unsupported: ${error.message ?: "invalid advertisement"}.")
        }
    }

    @Synchronized
    fun stop() {
        val callback = activeCallback ?: return
        activeCallback = null
        try {
            manager.adapter?.bluetoothLeAdvertiser?.stopAdvertising(callback)
        } catch (_: SecurityException) {
            // Permission may have been revoked while advertising. Cleanup stays safe.
        } catch (_: IllegalStateException) {
            // The adapter may already have stopped advertising during a radio reset.
        }
    }
}
