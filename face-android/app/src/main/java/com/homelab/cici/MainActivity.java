package com.homelab.cici;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.TextView;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.homelab.cici.api.EarsClient;
import com.homelab.cici.api.MindClient;
import com.homelab.cici.api.MouthClient;
import com.homelab.cici.audio.AudioPlayer;
import com.homelab.cici.audio.AudioRecorder;
import com.homelab.cici.model.Message;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends AppCompatActivity
        implements EarsClient.TranscriptionListener, AudioPlayer.PlaybackListener {

    private static final int PERMISSION_REQUEST_AUDIO = 100;

    private SettingsManager settings;
    private MindClient mindClient;
    private EarsClient earsClient;
    private MouthClient mouthClient;
    private AudioRecorder audioRecorder;
    private AudioPlayer audioPlayer;

    private final ExecutorService executor = Executors.newCachedThreadPool();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    // UI
    private RecyclerView messageList;
    private MessageAdapter messageAdapter;
    private EditText textInput;
    private ImageButton btnSend;
    private ImageButton btnMic;
    private ImageButton btnSettings;
    private TextView statusBar;
    private View micIndicator;

    private final List<Message> messages = new ArrayList<>();
    private boolean micActive = false;

    private final ActivityResultLauncher<Intent> settingsLauncher =
            registerForActivityResult(new ActivityResultContracts.StartActivityForResult(), result -> {
                if (result.getResultCode() == RESULT_OK) {
                    reinitClients();
                }
            });

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        settings = new SettingsManager(this);
        initViews();
        initClients();
        checkHealth();
    }

    private void initViews() {
        messageList = findViewById(R.id.message_list);
        textInput = findViewById(R.id.text_input);
        btnSend = findViewById(R.id.btn_send);
        btnMic = findViewById(R.id.btn_mic);
        btnSettings = findViewById(R.id.btn_settings);
        statusBar = findViewById(R.id.status_bar);
        micIndicator = findViewById(R.id.mic_indicator);

        messageAdapter = new MessageAdapter(messages);
        messageList.setLayoutManager(new LinearLayoutManager(this));
        messageList.setAdapter(messageAdapter);

        btnSend.setOnClickListener(v -> sendText());
        btnMic.setOnClickListener(v -> toggleMic());
        btnSettings.setOnClickListener(v ->
                settingsLauncher.launch(new Intent(this, SettingsActivity.class)));

        textInput.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_SEND) {
                sendText();
                return true;
            }
            return false;
        });
    }

    private void initClients() {
        String host = settings.getServerHost();

        mindClient = new MindClient(host, settings.getMindPort());
        earsClient = new EarsClient(host, settings.getEarsPort(), settings.getEarsDebug());
        mouthClient = new MouthClient(host, settings.getMouthPort());
        audioRecorder = new AudioRecorder(earsClient);
        audioPlayer = new AudioPlayer(mouthClient);

        earsClient.setListener(this);
        audioPlayer.setListener(this);
    }

    private void reinitClients() {
        // Stop active audio
        if (micActive) toggleMic();
        audioPlayer.stopPolling();

        String host = settings.getServerHost();
        mindClient.updateEndpoint(host, settings.getMindPort());
        earsClient.updateEndpoint(host, settings.getEarsPort(), settings.getEarsDebug());
        mouthClient.updateEndpoint(host, settings.getMouthPort());

        checkHealth();
    }

    private void checkHealth() {
        executor.execute(() -> {
            boolean mind = mindClient.healthCheck();
            boolean mouth = mouthClient.healthCheck();
            mainHandler.post(() -> {
                String host = settings.getServerHost();
                String status = "MIND:" + (mind ? "OK" : "DOWN")
                        + "  MOUTH:" + (mouth ? "OK" : "DOWN")
                        + "  [" + host + "]";
                statusBar.setText(status);

                if (mind) {
                    audioPlayer.startPolling();
                }
            });
        });
    }

    private void sendText() {
        String text = textInput.getText().toString().trim();
        if (text.isEmpty()) return;

        textInput.setText("");
        addMessage(new Message(Message.Type.USER, text));

        executor.execute(() -> {
            try {
                MindClient.ProcessResult result = mindClient.processText(text, null);
                mainHandler.post(() -> handleMindResult(result));
            } catch (Exception e) {
                mainHandler.post(() ->
                        addMessage(new Message(Message.Type.ERROR, "MIND error: " + e.getMessage())));
            }
        });
    }

    private void handleMindResult(MindClient.ProcessResult result) {
        if (result == null || result.messages == null) return;

        for (MindClient.MessageEntry entry : result.messages) {
            if (entry.error != null && !entry.error.isEmpty()) {
                addMessage(new Message(Message.Type.ERROR, entry.error));
                continue;
            }

            switch (entry.type) {
                case "llm_response":
                    String prefix = entry.model != null ? "[" + entry.model + "] " : "";
                    addMessage(new Message(Message.Type.ASSISTANT, prefix + entry.content));
                    break;
                case "cli_result":
                    if (entry.command != null) {
                        addMessage(new Message(Message.Type.CLI_COMMAND, "$ " + entry.command));
                    }
                    addMessage(new Message(Message.Type.CLI_OUTPUT, entry.content));
                    break;
                case "system":
                    addMessage(new Message(Message.Type.SYSTEM, entry.content));
                    break;
                case "error":
                    addMessage(new Message(Message.Type.ERROR, entry.content));
                    break;
                default:
                    addMessage(new Message(Message.Type.ASSISTANT, entry.content));
                    break;
            }
        }

        // Update status with mode
        String mode = result.mode != null ? result.mode : "unknown";
        String dir = result.currentDirectory != null ? result.currentDirectory : "";
        statusBar.setText("Mode: " + mode + (dir.isEmpty() ? "" : "  " + dir));
    }

    private void toggleMic() {
        if (micActive) {
            // Stop recording
            audioRecorder.stop();
            earsClient.disconnect();
            micActive = false;
            btnMic.setImageResource(android.R.drawable.ic_btn_speak_now);
            micIndicator.setVisibility(View.GONE);
        } else {
            // Check permission
            if (ActivityCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                    != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(this,
                        new String[]{Manifest.permission.RECORD_AUDIO}, PERMISSION_REQUEST_AUDIO);
                return;
            }
            startRecording();
        }
    }

    private void startRecording() {
        earsClient.connect();
        // Small delay to let WebSocket connect before sending audio
        mainHandler.postDelayed(() -> {
            if (audioRecorder.start(this)) {
                micActive = true;
                btnMic.setImageResource(android.R.drawable.ic_media_pause);
                micIndicator.setVisibility(View.VISIBLE);
                addMessage(new Message(Message.Type.SYSTEM, "Listening..."));
            } else {
                addMessage(new Message(Message.Type.ERROR, "Failed to start microphone"));
                earsClient.disconnect();
            }
        }, 300);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == PERMISSION_REQUEST_AUDIO
                && grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            startRecording();
        } else {
            addMessage(new Message(Message.Type.ERROR, "Microphone permission denied"));
        }
    }

    // --- EarsClient.TranscriptionListener ---

    @Override
    public void onTranscription(String text, boolean isFinal) {
        mainHandler.post(() -> {
            if (isFinal && !text.trim().isEmpty()) {
                addMessage(new Message(Message.Type.TRANSCRIPTION, text));
                // Auto-send transcription to MIND
                executor.execute(() -> {
                    try {
                        MindClient.ProcessResult result = mindClient.processText(text, text);
                        mainHandler.post(() -> handleMindResult(result));
                    } catch (Exception e) {
                        mainHandler.post(() ->
                                addMessage(new Message(Message.Type.ERROR, "MIND error: " + e.getMessage())));
                    }
                });
            }
        });
    }

    @Override
    public void onError(String error) {
        mainHandler.post(() -> addMessage(new Message(Message.Type.ERROR, error)));
    }

    @Override
    public void onConnected() {
        mainHandler.post(() -> addMessage(new Message(Message.Type.SYSTEM, "EARS connected")));
    }

    @Override
    public void onDisconnected() {
        mainHandler.post(() -> {
            if (micActive) {
                micActive = false;
                audioRecorder.stop();
                btnMic.setImageResource(android.R.drawable.ic_btn_speak_now);
                micIndicator.setVisibility(View.GONE);
                addMessage(new Message(Message.Type.SYSTEM, "EARS disconnected"));
            }
        });
    }

    // --- AudioPlayer.PlaybackListener ---

    @Override
    public void onPlaybackStarted() {}

    @Override
    public void onPlaybackFinished() {}

    // --- Helpers ---

    private void addMessage(Message msg) {
        messages.add(msg);
        messageAdapter.notifyItemInserted(messages.size() - 1);
        messageList.scrollToPosition(messages.size() - 1);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        audioRecorder.stop();
        earsClient.disconnect();
        audioPlayer.stopPolling();
        executor.shutdown();
    }
}
