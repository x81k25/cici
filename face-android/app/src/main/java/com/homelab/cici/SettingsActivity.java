package com.homelab.cici;

import android.os.Bundle;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Switch;

import androidx.appcompat.app.AppCompatActivity;

public class SettingsActivity extends AppCompatActivity {
    private SettingsManager settings;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_settings);

        settings = new SettingsManager(this);

        EditText hostInput = findViewById(R.id.input_host);
        EditText mindPortInput = findViewById(R.id.input_mind_port);
        EditText earsPortInput = findViewById(R.id.input_ears_port);
        EditText mouthPortInput = findViewById(R.id.input_mouth_port);
        Switch debugSwitch = findViewById(R.id.switch_ears_debug);
        Button saveButton = findViewById(R.id.btn_save);

        // Load current values
        hostInput.setText(settings.getServerHost());
        mindPortInput.setText(String.valueOf(settings.getMindPort()));
        earsPortInput.setText(String.valueOf(settings.getEarsPort()));
        mouthPortInput.setText(String.valueOf(settings.getMouthPort()));
        debugSwitch.setChecked(settings.getEarsDebug());

        saveButton.setOnClickListener(v -> {
            settings.setServerHost(hostInput.getText().toString().trim());
            try {
                settings.setMindPort(Integer.parseInt(mindPortInput.getText().toString().trim()));
                settings.setEarsPort(Integer.parseInt(earsPortInput.getText().toString().trim()));
                settings.setMouthPort(Integer.parseInt(mouthPortInput.getText().toString().trim()));
            } catch (NumberFormatException ignored) {}
            settings.setEarsDebug(debugSwitch.isChecked());
            setResult(RESULT_OK);
            finish();
        });
    }
}
