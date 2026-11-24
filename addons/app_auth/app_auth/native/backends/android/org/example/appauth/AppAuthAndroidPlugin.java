package org.example.appauth;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Bundle;
import java.util.Collections;
import java.util.Set;
import net.openid.appauth.AuthorizationException;
import net.openid.appauth.AuthorizationRequest;
import net.openid.appauth.AuthorizationResponse;
import net.openid.appauth.AuthorizationService;
import net.openid.appauth.AuthorizationServiceConfiguration;
import net.openid.appauth.ResponseTypeValues;
import net.openid.appauth.TokenResponse;
import org.godotengine.godot.Godot;
import org.godotengine.godot.plugin.GodotPlugin;
import org.godotengine.godot.plugin.SignalInfo;
import org.godotengine.godot.plugin.UsedByGodot;

/**
 * The Android login backend: AppAuth for Android behind one plugin signal. Games use the
 * AppAuth classes of the extension; this singleton is an implementation detail.
 */
public final class AppAuthAndroidPlugin extends GodotPlugin {
    private static final int REQUEST_CODE = 0x4170;
    private static final String FINISHED = "finished";
    /** The meta-data entry of the add-on's manifest that the application's manifest value fills. */
    private static final String SCHEME_META_DATA = "org.example.appauth.redirect_scheme";

    private AuthorizationService service;
    private boolean pending;
    private long pendingRequestId;

    public AppAuthAndroidPlugin(Godot godot) {
        super(godot);
    }

    @Override
    public String getPluginName() {
        return "AppAuthAndroid";
    }

    @Override
    public Set<SignalInfo> getPluginSignals() {
        // request_id, status, message, provider_error, access_token, id_token, scopes,
        // expires_at (Unix seconds), has_refresh_token
        return Collections.singleton(new SignalInfo(FINISHED, Long.class, String.class, String.class,
                String.class, String.class, String.class, String.class, Long.class, Boolean.class));
    }

    /** The redirect scheme the application set through android_manifest_values; empty if unset. */
    @UsedByGodot
    public String redirect_scheme() {
        Activity activity = getActivity();
        if (activity == null) {
            return "";
        }
        try {
            ApplicationInfo info = activity.getPackageManager()
                    .getApplicationInfo(activity.getPackageName(), PackageManager.GET_META_DATA);
            Bundle metaData = info.metaData;
            String scheme = metaData == null ? null : metaData.getString(SCHEME_META_DATA);
            return scheme == null ? "" : scheme;
        } catch (PackageManager.NameNotFoundException exception) {
            return "";
        }
    }

    /** Starts a login; false without an activity or while another login is pending. */
    @UsedByGodot
    public boolean start(long requestId, String issuer, String clientId, String scopes, String redirectUri) {
        final Activity activity = getActivity();
        synchronized (this) {
            if (activity == null || pending) {
                return false;
            }
            pending = true;
            pendingRequestId = requestId;
        }
        activity.runOnUiThread(() -> {
            if (service == null) {
                service = new AuthorizationService(activity);
            }
            AuthorizationServiceConfiguration.fetchFromIssuer(Uri.parse(issuer), (configuration, exception) -> {
                if (configuration == null) {
                    finishWithException(requestId, exception);
                    return;
                }
                AuthorizationRequest request = new AuthorizationRequest.Builder(
                        configuration, clientId, ResponseTypeValues.CODE, Uri.parse(redirectUri))
                        .setScope(scopes)
                        .build();
                try {
                    // PKCE is AppAuth's default; the redirect returns through
                    // AuthorizationManagementActivity to this activity's result.
                    activity.startActivityForResult(service.getAuthorizationRequestIntent(request), REQUEST_CODE);
                } catch (RuntimeException runtimeException) {
                    fail(requestId, "error", "The login page could not be opened: "
                            + runtimeException.getClass().getSimpleName());
                }
            });
        });
        return true;
    }

    @Override
    public void onMainActivityResult(int requestCode, int resultCode, Intent data) {
        final long requestId;
        synchronized (this) {
            if (requestCode != REQUEST_CODE || !pending) {
                return;
            }
            requestId = pendingRequestId;
        }
        if (data == null) {
            fail(requestId, "cancelled", "The login was cancelled");
            return;
        }
        AuthorizationResponse response = AuthorizationResponse.fromIntent(data);
        AuthorizationException exception = AuthorizationException.fromIntent(data);
        if (response == null) {
            finishWithException(requestId, exception);
            return;
        }
        service.performTokenRequest(response.createTokenExchangeRequest(), (tokenResponse, tokenException) -> {
            if (tokenResponse == null) {
                finishWithException(requestId, tokenException);
                return;
            }
            finishWithTokens(requestId, tokenResponse);
        });
    }

    @Override
    public void onMainDestroy() {
        if (service != null) {
            service.dispose();
            service = null;
        }
    }

    private void finishWithTokens(long requestId, TokenResponse response) {
        Long expiration = response.accessTokenExpirationTime;
        long expiresAt = expiration == null ? 0L : expiration / 1000L;
        finish(requestId, "ok", "", "",
                response.accessToken == null ? "" : response.accessToken,
                response.idToken == null ? "" : response.idToken,
                response.scope == null ? "" : response.scope,
                expiresAt, response.refreshToken != null);
    }

    private void finishWithException(long requestId, AuthorizationException exception) {
        if (exception == null) {
            fail(requestId, "error", "AppAuth returned no result");
            return;
        }
        String description = exception.errorDescription != null ? exception.errorDescription
                : exception.getMessage() != null ? exception.getMessage() : "AppAuth error " + exception.code;
        if (exception.type == AuthorizationException.TYPE_GENERAL_ERROR) {
            if (exception.code == AuthorizationException.GeneralErrors.USER_CANCELED_AUTH_FLOW.code
                    || exception.code == AuthorizationException.GeneralErrors.PROGRAM_CANCELED_AUTH_FLOW.code) {
                fail(requestId, "cancelled", "The login was cancelled");
                return;
            }
            if (exception.code == AuthorizationException.GeneralErrors.NETWORK_ERROR.code
                    || exception.code == AuthorizationException.GeneralErrors.SERVER_ERROR.code) {
                fail(requestId, "network_error", "The identity provider could not be reached: " + description);
                return;
            }
        }
        if (exception.type == AuthorizationException.TYPE_OAUTH_AUTHORIZATION_ERROR
                || exception.type == AuthorizationException.TYPE_OAUTH_TOKEN_ERROR) {
            fail(requestId, "provider_error", description, exception.error == null ? "" : exception.error);
            return;
        }
        fail(requestId, "error", description);
    }

    private void fail(long requestId, String status, String message) {
        fail(requestId, status, message, "");
    }

    /** A failed login: every token field stays empty. */
    private void fail(long requestId, String status, String message, String providerError) {
        finish(requestId, status, message, providerError, "", "", "", 0L, false);
    }

    /** Every login ends with exactly one finished signal; tokens are never logged. */
    private void finish(long requestId, String status, String message, String providerError,
            String accessToken, String idToken, String scopes, long expiresAt, boolean hasRefreshToken) {
        synchronized (this) {
            if (!pending || pendingRequestId != requestId) {
                return;
            }
            pending = false;
        }
        emitSignal(FINISHED, requestId, status, message, providerError, accessToken, idToken, scopes,
                expiresAt, hasRefreshToken);
    }
}
