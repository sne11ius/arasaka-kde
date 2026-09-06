// Based on Burn-My-Windows by Simon Schneegans, Martin Floeser and Vlad Zahorodnii.
// Local Arasaka adaptation for KWin 6.7 minimize/restore and popup visibility events.
// SPDX-License-Identifier: GPL-3.0-or-later

'use strict';

class TvGlitchMinimizeEffect {
    constructor() {
        this.running = new Map();
        // Keep directions and window/popup durations independent during overlapping animations.
        this.shaders = Array.from({length: 4}, (_, index) => {
            const shader = effect.addFragmentShader(Effect.MapTexture, 'tv-glitch.frag');
            effect.setUniform(shader, 'uForOpening', index % 2);
            effect.setUniform(shader, 'uIsFullscreen', 0);
            effect.setUniform(shader, 'uSeed', Math.random());
            return shader;
        });
        this.loadConfig();
        effect.configChanged.connect(() => this.loadConfig());
        effect.animationEnded.connect(window => this.finish(window, false));
        effects.windowClosed.connect(window => {
            if (this.isPopup(window) && (window.visible || this.running.has(window)) &&
                !window.skipsCloseAnimation) {
                this.animate(window, true, true);
            } else {
                this.finish(window, true);
            }
        });
        effects.windowDeleted.connect(window => this.running.delete(window));
        effects.windowAdded.connect(window => {
            this.watch(window);
            if (this.isPopup(window) && window.visible) {
                this.animate(window, false, true);
            }
        });
        effects.windowDataChanged.connect((window, role) => {
            const running = this.running.get(window);
            if (running && running.role === role && effect.isGrabbed(window, role)) {
                this.finish(window, true);
            }
        });
        const cancelAll = () => {
            for (const window of this.running.keys()) {
                this.finish(window, true);
            }
        };
        effects.desktopChanged.connect(cancelAll);
        effects.desktopChanging.connect(cancelAll);
        effects.currentActivityChanged.connect(cancelAll);
        effects.activeFullScreenEffectChanged.connect(cancelAll);
        effects.screenLockingChanged.connect(cancelAll);
        for (const window of effects.stackingOrder) {
            this.watch(window);
        }
    }

    loadConfig() {
        this.duration = animationTime(effect.readConfig('Duration', 700));
        this.popupDuration = animationTime(effect.readConfig('PopupDuration', 300));
        const channels = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})?$/i
            .exec(effect.readConfig('Color', '#64a0ff'))
            .slice(1).filter(value => value !== undefined)
            .map(value => parseInt(value, 16) / 255);
        const color = channels.length === 3 ? [...channels, 1] :
                      [channels[1], channels[2], channels[3], channels[0]];
        this.shaders.forEach((shader, index) => {
            effect.setUniform(shader, 'uDuration', (index < 2 ? this.duration : this.popupDuration) / 1000);
            effect.setUniform(shader, 'uScale', effect.readConfig('Scale', 1));
            effect.setUniform(shader, 'uStrength', effect.readConfig('Strength', 2));
            effect.setUniform(shader, 'uSpeed', effect.readConfig('Speed', 2));
            effect.setUniform(shader, 'uColor', color);
        });
    }

    isPopup(window) {
        if (window.lockScreen || window.outline || window.desktopWindow || window.dock ||
            /^(ksmserver|ksmserver-logout-greeter|kscreenlocker_greet|ksplashqml) /.test(window.windowClass)) {
            return false;
        }
        return window.popupWindow || window.appletPopup || window.menu ||
               window.dropdownMenu || window.popupMenu || window.tooltip || window.comboBox ||
               (window.x11Client && !window.managed && (window.normalWindow || window.utility));
    }

    watch(window) {
        const popup = this.isPopup(window);
        if ((!popup && ((!window.normalWindow && !window.dialog) || window.popupWindow)) ||
            window.lockScreen || window.outline) {
            return;
        }
        if (popup) {
            window.windowHiddenChanged.connect(() => {
                if (!window.deleted) {
                    this.animate(window, !window.visible, true);
                }
            });
        } else {
            window.minimizedChanged.connect(() => this.animate(window, window.minimized, false));
        }
        window.windowDesktopsChanged.connect(() => {
            if (!window.onCurrentDesktop) {
                this.finish(window, true);
            }
        });
    }

    finish(window, cancelAnimation) {
        const running = this.running.get(window);
        if (!running) {
            return;
        }
        this.running.delete(window);
        effect.ungrab(window, Effect.WindowAddedGrabRole);
        effect.ungrab(window, Effect.WindowClosedGrabRole);
        // A close effect may already have claimed these shared rendering roles.
        if (!window.deleted) {
            window.setData(Effect.WindowForceBlurRole, null);
            window.setData(Effect.WindowForceBackgroundContrastRole, null);
        }
        // Cancellation may release the last reference to a closed popup.
        if (cancelAnimation) {
            cancel(running.ids);
        }
    }

    animate(window, closing, popup) {
        const role = popup ? (closing ? Effect.WindowClosedGrabRole : Effect.WindowAddedGrabRole) :
                             (closing ? Effect.WindowMinimizedGrabRole : Effect.WindowUnminimizedGrabRole);
        const duration = popup ? this.popupDuration : this.duration;
        if (!window.onCurrentDesktop || !window.onCurrentActivity ||
            effects.hasActiveFullScreenEffect ||
            (!popup && effect.isGrabbed(window, role)) || duration === 0 ||
            (popup && closing && window.skipsCloseAnimation)) {
            this.finish(window, true);
            return;
        }
        // We replace popup effects, including stale grabs left by an unloaded effect.
        if (popup && !effect.grab(window, role, true)) {
            this.finish(window, true);
            return;
        }

        const running = this.running.get(window);
        if (running) {
            // Keep the shader and current progress when reversing an interrupted effect.
            const target = closing === running.closing ? 1 : 0;
            if (target === running.target || retarget(running.ids, target, duration)) {
                if (popup && running.role !== role) {
                    effect.ungrab(window, running.role);
                }
                running.target = target;
                running.role = role;
                return;
            }
            this.finish(window, true);
        }

        window.setData(Effect.WindowForceBlurRole, true);
        window.setData(Effect.WindowForceBackgroundContrastRole, true);
        try {
            const ids = animate({
                window: window,
                duration: duration,
                curve: QEasingCurve.Linear,
                keepAlive: popup,
                animations: [{
                    type: Effect.ShaderUniform,
                    fragmentShader: this.shaders[(popup ? 2 : 0) + (closing ? 0 : 1)],
                    uniform: 'uProgress',
                    from: 0,
                    to: 1
                }]
            });
            this.running.set(window, {ids: ids, closing: closing, target: 1, role: role});
        } catch (error) {
            effect.ungrab(window, Effect.WindowAddedGrabRole);
            effect.ungrab(window, Effect.WindowClosedGrabRole);
            window.setData(Effect.WindowForceBlurRole, null);
            window.setData(Effect.WindowForceBackgroundContrastRole, null);
            console.warn('TV Glitch Minimize: ' + error);
        }
    }
}

new TvGlitchMinimizeEffect();
