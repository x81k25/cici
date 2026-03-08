package com.homelab.cici;

import android.content.Context;
import android.content.SharedPreferences;

public class SettingsManager {
    private static final String PREFS_NAME = "cici_settings";
    private static final String KEY_SERVER_HOST = "server_host";
    private static final String KEY_MIND_PORT = "mind_port";
    private static final String KEY_EARS_PORT = "ears_port";
    private static final String KEY_MOUTH_PORT = "mouth_port";
    private static final String KEY_EARS_DEBUG = "ears_debug";

    private static final String DEFAULT_HOST = "192.168.50.2";
    private static final int DEFAULT_MIND_PORT = 30211;
    private static final int DEFAULT_EARS_PORT = 30212;
    private static final int DEFAULT_MOUTH_PORT = 30213;

    private final SharedPreferences prefs;

    public SettingsManager(Context context) {
        prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    public String getServerHost() { return prefs.getString(KEY_SERVER_HOST, DEFAULT_HOST); }
    public int getMindPort() { return prefs.getInt(KEY_MIND_PORT, DEFAULT_MIND_PORT); }
    public int getEarsPort() { return prefs.getInt(KEY_EARS_PORT, DEFAULT_EARS_PORT); }
    public int getMouthPort() { return prefs.getInt(KEY_MOUTH_PORT, DEFAULT_MOUTH_PORT); }
    public boolean getEarsDebug() { return prefs.getBoolean(KEY_EARS_DEBUG, false); }

    public void setServerHost(String host) { prefs.edit().putString(KEY_SERVER_HOST, host).apply(); }
    public void setMindPort(int port) { prefs.edit().putInt(KEY_MIND_PORT, port).apply(); }
    public void setEarsPort(int port) { prefs.edit().putInt(KEY_EARS_PORT, port).apply(); }
    public void setMouthPort(int port) { prefs.edit().putInt(KEY_MOUTH_PORT, port).apply(); }
    public void setEarsDebug(boolean debug) { prefs.edit().putBoolean(KEY_EARS_DEBUG, debug).apply(); }
}
