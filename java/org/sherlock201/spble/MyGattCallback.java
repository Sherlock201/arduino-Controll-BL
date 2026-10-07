package org.sherlock201.spble;

import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

public class MyGattCallback extends BluetoothGattCallback {
    private static final String TAG = "MyGattCallback";
    private static final int DISCOVER_DELAY_MS = 300;
    private static final int DISCOVER_MAX_RETRIES = 5;

    public interface BleListener {
        void onConnected();
        void onDisconnected();
        void onServicesDiscovered(BluetoothGatt gatt, int status);
        void onError(String message);
    }

    private BleListener listener;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private BluetoothGatt currentGatt;
    private int discoverAttempt = 0;
    private boolean servicesDone = false;

    public MyGattCallback(BleListener listener) {
        this.listener = listener;
    }

    private final Runnable discoverRunnable = new Runnable() {
        @Override public void run() {
            if (currentGatt == null || servicesDone) return;
            discoverAttempt++;
            Log.d(TAG, "discoverServices() attempt #" + discoverAttempt);
            boolean ok = currentGatt.discoverServices();
            Log.d(TAG, "discoverServices() returned: " + ok);

            if (!servicesDone && discoverAttempt < DISCOVER_MAX_RETRIES) {
                handler.postDelayed(this, DISCOVER_DELAY_MS);
            }
        }
    };

    @Override
    public void onConnectionStateChange(BluetoothGatt gatt, int status, int newState) {
        if (newState == 2) { // STATE_CONNECTED
            Log.d(TAG, "Connected, scheduling discoverServices");
            currentGatt = gatt;
            servicesDone = false;
            discoverAttempt = 0;

            if (listener != null) listener.onConnected();

            handler.postDelayed(discoverRunnable, DISCOVER_DELAY_MS);

        } else if (newState == 0) { // STATE_DISCONNECTED
            Log.d(TAG, "Disconnected");
            handler.removeCallbacksAndMessages(null);
            servicesDone = true;
            currentGatt = null;
            if (listener != null) listener.onDisconnected();
        }
    }

    @Override
    public void onServicesDiscovered(BluetoothGatt gatt, int status) {
        servicesDone = true;
        handler.removeCallbacks(discoverRunnable);
        Log.d(TAG, "Services discovered, status=" + status);
        if (listener != null) {
            listener.onServicesDiscovered(gatt, status);
        }
    }

    @Override
    public void onCharacteristicWrite(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic, int status) {
        Log.d(TAG, "Characteristic write status: " + status);
    }
}
