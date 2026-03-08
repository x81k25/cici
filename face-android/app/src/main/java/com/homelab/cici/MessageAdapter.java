package com.homelab.cici;

import android.graphics.Color;
import android.graphics.Typeface;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.homelab.cici.model.Message;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;

public class MessageAdapter extends RecyclerView.Adapter<MessageAdapter.ViewHolder> {
    private final List<Message> messages;
    private final SimpleDateFormat timeFormat = new SimpleDateFormat("HH:mm:ss", Locale.getDefault());

    public MessageAdapter(List<Message> messages) {
        this.messages = messages;
    }

    @NonNull
    @Override
    public ViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext())
                .inflate(R.layout.item_message, parent, false);
        return new ViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ViewHolder holder, int position) {
        Message msg = messages.get(position);
        holder.timestamp.setText(timeFormat.format(new Date(msg.getTimestamp())));
        holder.content.setText(msg.getContent());

        switch (msg.getType()) {
            case USER:
                holder.content.setTextColor(Color.parseColor("#90CAF9")); // light blue
                holder.content.setTypeface(null, Typeface.NORMAL);
                break;
            case ASSISTANT:
                holder.content.setTextColor(Color.parseColor("#E0E0E0")); // light gray
                holder.content.setTypeface(null, Typeface.NORMAL);
                break;
            case CLI_COMMAND:
                holder.content.setTextColor(Color.parseColor("#80CBC4")); // teal
                holder.content.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
                break;
            case CLI_OUTPUT:
                holder.content.setTextColor(Color.parseColor("#A5D6A7")); // light green
                holder.content.setTypeface(Typeface.MONOSPACE, Typeface.NORMAL);
                break;
            case SYSTEM:
                holder.content.setTextColor(Color.parseColor("#FFE082")); // amber
                holder.content.setTypeface(null, Typeface.ITALIC);
                break;
            case ERROR:
                holder.content.setTextColor(Color.parseColor("#EF9A9A")); // light red
                holder.content.setTypeface(null, Typeface.BOLD);
                break;
            case TRANSCRIPTION:
                holder.content.setTextColor(Color.parseColor("#CE93D8")); // light purple
                holder.content.setTypeface(null, Typeface.NORMAL);
                break;
        }
    }

    @Override
    public int getItemCount() {
        return messages.size();
    }

    static class ViewHolder extends RecyclerView.ViewHolder {
        final TextView timestamp;
        final TextView content;

        ViewHolder(View view) {
            super(view);
            timestamp = view.findViewById(R.id.msg_timestamp);
            content = view.findViewById(R.id.msg_content);
        }
    }
}
