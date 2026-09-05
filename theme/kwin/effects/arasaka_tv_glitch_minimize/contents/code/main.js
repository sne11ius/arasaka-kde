// Based on Burn-My-Windows by Simon Schneegans, Martin Floeser and Vlad Zahorodnii.
// Local Arasaka adaptation for KWin 6.7 minimize/restore events.
// SPDX-License-Identifier: GPL-3.0-or-later

'use strict';

class TvGlitchMinimizeEffect {
    constructor() {
        this.running = new Map();
        // Separate shaders keep simultaneous minimize/restore directions independent.
        this.shaders = [
            effect.addFragmentShader(Effect.MapTexture, 'tv-glitch.frag'),
            effect.addFragmentShader(Effect.MapTexture, 'tv-glitch.frag')
        ];
        this.shaders.forEach((shader, opening) => {
            effect.setUniform(shader, 'uForOpening', opening);
            effect.setUniform(shader, 'uIsFullscreen', 0);
            effect.setUniform(shader, 'uSeed', Math.random());
        });
        this.loadConfig();
        effect.configChanged.connect(() => this.loadConfig());
        effect.animationEnded.connect(window => this.finish(window, false));
        effects.windowClosed.connect(window => this.finish(window, true));
        effects.windowDeleted.connect(window => this.running.delete(window));
        effects.windowAdded.connect(window => this.watch(window));
        const cancelAll = () => {
            for (const window of this.running.keys()) {
                this.finish(window, true);
            }
        };
        effects.desktopChanged.connect(cancelAll);
        effects.desktopChanging.connect(cancelAll);
        effects.currentActivityChanged.connect(cancelAll);
        effects.activeFullScreenEffectChanged.connect(cancelAll);
        for (const window of effects.stackingOrder) {
            this.watch(window);
        }
    }

    loadConfig() {
        this.duration = animationTime(effect.readConfig('Duration', 700));
        const channels = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})?$/i
            .exec(effect.readConfig('Color', '#64a0ff'))
            .slice(1).filter(value => value !== undefined)
            .map(value => parseInt(value, 16) / 255);
        const color = channels.length === 3 ? [...channels, 1] :
                      [channels[1], channels[2], channels[3], channels[0]];
        for (const shader of this.shaders) {
            effect.setUniform(shader, 'uDuration', this.duration / 1000);
            effect.setUniform(shader, 'uScale', effect.readConfig('Scale', 1));
            effect.setUniform(shader, 'uStrength', effect.readConfig('Strength', 2));
            effect.setUniform(shader, 'uSpeed', effect.readConfig('Speed', 2));
            effect.setUniform(shader, 'uColor', color);
        }
    }

    watch(window) {
        if ((!window.normalWindow && !window.dialog) || window.popupWindow ||
            window.lockScreen || window.outline) {
            return;
        }
        window.minimizedChanged.connect(() => this.animate(window));
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
        if (cancelAnimation) {
            cancel(running.ids);
        }
        // A close effect may already have claimed these shared rendering roles.
        if (!window.deleted) {
            window.setData(Effect.WindowForceBlurRole, null);
            window.setData(Effect.WindowForceBackgroundContrastRole, null);
        }
    }

    animate(window) {
        const role = window.minimized ? Effect.WindowMinimizedGrabRole :
                                        Effect.WindowUnminimizedGrabRole;
        if (!window.onCurrentDesktop || !window.onCurrentActivity ||
            effects.hasActiveFullScreenEffect || effect.isGrabbed(window, role) ||
            this.duration === 0) {
            this.finish(window, true);
            return;
        }

        const running = this.running.get(window);
        if (running) {
            // Keep the shader and current progress when reversing an interrupted effect.
            const target = window.minimized === running.minimizing ? 1 : 0;
            if (retarget(running.ids, target, this.duration)) {
                return;
            }
            this.finish(window, true);
        }

        window.setData(Effect.WindowForceBlurRole, true);
        window.setData(Effect.WindowForceBackgroundContrastRole, true);
        try {
            const ids = animate({
                window: window,
                duration: this.duration,
                curve: QEasingCurve.Linear,
                keepAlive: false,
                animations: [{
                    type: Effect.ShaderUniform,
                    fragmentShader: this.shaders[window.minimized ? 0 : 1],
                    uniform: 'uProgress',
                    from: 0,
                    to: 1
                }]
            });
            this.running.set(window, {ids: ids, minimizing: window.minimized});
        } catch (error) {
            window.setData(Effect.WindowForceBlurRole, null);
            window.setData(Effect.WindowForceBackgroundContrastRole, null);
            console.warn('TV Glitch Minimize: ' + error);
        }
    }
}

new TvGlitchMinimizeEffect();
