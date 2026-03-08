package com.homelab.cici.auto;

import androidx.annotation.NonNull;
import androidx.car.app.CarContext;
import androidx.car.app.CarToast;
import androidx.car.app.Screen;
import androidx.car.app.model.Action;
import androidx.car.app.model.CarColor;
import androidx.car.app.model.Pane;
import androidx.car.app.model.PaneTemplate;
import androidx.car.app.model.Row;
import androidx.car.app.model.Template;

/**
 * Android Auto screen stub. Shows connection status with placeholder actions.
 * Future: voice-driven interaction with MIND through EARS.
 */
public class CiciCarScreen extends Screen {

    public CiciCarScreen(@NonNull CarContext carContext) {
        super(carContext);
    }

    @NonNull
    @Override
    public Template onGetTemplate() {
        Row statusRow = new Row.Builder()
                .setTitle("CICI Assistant")
                .addText("Status: Ready")
                .build();

        Row infoRow = new Row.Builder()
                .setTitle("Voice Control")
                .addText("Coming soon - use phone app for now")
                .build();

        Pane pane = new Pane.Builder()
                .addRow(statusRow)
                .addRow(infoRow)
                .addAction(new Action.Builder()
                        .setTitle("Open Phone App")
                        .setBackgroundColor(CarColor.BLUE)
                        .setOnClickListener(() ->
                                CarToast.makeText(getCarContext(),
                                        "Use the phone app for full features",
                                        CarToast.LENGTH_LONG).show())
                        .build())
                .build();

        return new PaneTemplate.Builder(pane)
                .setTitle("CICI")
                .setHeaderAction(Action.APP_ICON)
                .build();
    }
}
