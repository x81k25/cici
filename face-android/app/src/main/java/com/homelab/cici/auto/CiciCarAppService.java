package com.homelab.cici.auto;

import androidx.annotation.NonNull;
import androidx.car.app.CarAppService;
import androidx.car.app.Session;
import androidx.car.app.validation.HostValidator;

/**
 * Android Auto entry point. Minimal stub for future implementation.
 */
public class CiciCarAppService extends CarAppService {

    @NonNull
    @Override
    public Session onCreateSession() {
        return new CiciCarSession();
    }

    @NonNull
    @Override
    public HostValidator createHostValidator() {
        return HostValidator.ALLOW_ALL_HOSTS_VALIDATOR;
    }
}
