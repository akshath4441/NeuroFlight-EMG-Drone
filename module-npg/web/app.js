/**
 * NPG-DRONE BCI AVIONICS DASHBOARD CONTROLLER
 * Real-time EMG Signal Rendering, Flight Attitude Simulation, and Avionics State Machine
 */

class AvionicsDeck {
  constructor() {
    this.pollInterval = 60; // ms (approx 16 updates/sec)
    this.audioEnabled = true;
    this.audioContext = null;
    this.lastMuscleActive = false;

    // Canvas & Waveform state
    this.canvas = document.getElementById('scopeCanvas');
    this.ctx = this.canvas.getContext('2d');
    this.maxDataPoints = 200;
    this.historyLeft = new Array(this.maxDataPoints).fill(4.5);
    this.historyRight = new Array(this.maxDataPoints).fill(5.4);
    this.historyThreshold = 43.3;

    // Drone flight visual state
    this.droneRoll = 0;
    this.droneTargetRoll = 0;
    this.droneAltitude = 0;
    this.droneTargetAlt = 0;
    this.isArmed = false;

    // Cache DOM Elements
    this.elements = {
      liveClock: document.getElementById('live-clock'),
      banner: document.getElementById('readiness-banner'),
      headline: document.getElementById('banner-headline'),
      subtext: document.getElementById('banner-subtext'),
      flightStateText: document.getElementById('flight-state-text'),
      valBleStatus: document.getElementById('val-ble-status'),
      valDroneStatus: document.getElementById('val-drone-status'),
      valActiveMode: document.getElementById('val-active-mode'),
      btnSound: document.getElementById('btn-sound-toggle'),
      soundIcon: document.getElementById('sound-icon'),
      
      // Meters
      valLeftRms: document.getElementById('val-left-rms'),
      valRightRms: document.getElementById('val-right-rms'),
      barLeftFill: document.getElementById('bar-left-fill'),
      barRightFill: document.getElementById('bar-right-fill'),
      cardLeft: document.getElementById('meter-card-left'),
      cardRight: document.getElementById('meter-card-right'),
      badgeLeft: document.getElementById('badge-left'),
      badgeRight: document.getElementById('badge-right'),

      // Drone Vis
      droneRig: document.getElementById('drone-rig'),
      droneCoreLed: document.getElementById('drone-core-led'),
      thrustWash: document.getElementById('thrust-wash'),
      valRoll: document.getElementById('val-roll'),
      valThrust: document.getElementById('val-thrust'),
      valAlt: document.getElementById('val-alt'),
      valTelemCmd: document.getElementById('val-telem-cmd'),
      valTelemPower: document.getElementById('val-telem-power'),
      lblArmedTag: document.getElementById('lbl-armed-tag'),

      // Controls
      btnModeReplay: document.getElementById('btn-mode-replay'),
      btnModeSim: document.getElementById('btn-mode-sim'),
      btnModeHw: document.getElementById('btn-mode-hw'),
      btnFlexLeft: document.getElementById('btn-flex-left'),
      btnFlexRight: document.getElementById('btn-flex-right'),
      btnFlexBoth: document.getElementById('btn-flex-both'),
      btnRelax: document.getElementById('btn-relax'),
      btnToggleArm: document.getElementById('btn-toggle-arm'),
      btnManualTakeoff: document.getElementById('btn-manual-takeoff'),
      btnEstop: document.getElementById('btn-estop'),
    };

    this.init();
  }

  init() {
    this.bindEvents();
    this.setupCanvas();
    this.startClock();
    this.startPolling();
    this.startAnimationLoop();
  }

  // ============================================================
  // EVENT BINDINGS & KEYBOARD CONTROLS
  // ============================================================
  bindEvents() {
    // Sound Toggle
    this.elements.btnSound.addEventListener('click', () => {
      this.audioEnabled = !this.audioEnabled;
      this.elements.soundIcon.textContent = this.audioEnabled ? '🔊' : '🔇';
      if (this.audioEnabled) this.initAudio();
    });

    // Mode Buttons
    const modeButtons = [this.elements.btnModeReplay, this.elements.btnModeSim, this.elements.btnModeHw];
    modeButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const mode = btn.getAttribute('data-mode');
        this.setMode(mode);
      });
    });

    // Action Triggers
    this.elements.btnFlexLeft.addEventListener('click', () => this.sendAction('flex_left'));
    this.elements.btnFlexRight.addEventListener('click', () => this.sendAction('flex_right'));
    this.elements.btnFlexBoth.addEventListener('click', () => this.sendAction('flex_both'));
    this.elements.btnRelax.addEventListener('click', () => this.sendAction('relax'));
    this.elements.btnToggleArm.addEventListener('click', () => this.sendAction('toggle_arm'));
    this.elements.btnManualTakeoff.addEventListener('click', () => this.sendAction('takeoff'));
    this.elements.btnEstop.addEventListener('click', () => this.sendAction('emergency_stop'));

    // Keyboard Shortcuts for Instant Testing
    window.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      const key = e.key.toLowerCase();
      if (key === 'a') {
        this.sendAction('flex_left');
      } else if (key === 'd') {
        this.sendAction('flex_right');
      } else if (key === 'w' || e.code === 'Space') {
        e.preventDefault();
        this.sendAction('flex_both');
      } else if (key === 's') {
        this.sendAction('relax');
      } else if (e.key === 'Escape') {
        this.sendAction('emergency_stop');
      }
    });

    // Window Resize for canvas
    window.addEventListener('resize', () => this.setupCanvas());
  }

  setupCanvas() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.canvas.width = rect.width;
    this.canvas.height = rect.height;
  }

  startClock() {
    const update = () => {
      const now = new Date();
      this.elements.liveClock.textContent = now.toTimeString().split(' ')[0] + '.' + Math.floor(now.getMilliseconds() / 100);
    };
    setInterval(update, 100);
  }

  // ============================================================
  // SYNTHESIZED AUDIO CHIME (Web Audio API)
  // ============================================================
  initAudio() {
    if (!this.audioContext) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) this.audioContext = new AudioCtx();
    }
    if (this.audioContext && this.audioContext.state === 'suspended') {
      this.audioContext.resume();
    }
  }

  playTakeoffAlert() {
    if (!this.audioEnabled) return;
    try {
      this.initAudio();
      if (!this.audioContext) return;
      const now = this.audioContext.currentTime;

      // Two-tone rising futuristic chime
      const osc = this.audioContext.createOscillator();
      const gain = this.audioContext.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, now); // D5
      osc.frequency.exponentialRampToValueAtTime(880.00, now + 0.15); // A5

      gain.gain.setValueAtTime(0.001, now);
      gain.gain.linearRampToValueAtTime(0.15, now + 0.04);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.35);

      osc.connect(gain);
      gain.connect(this.audioContext.destination);

      osc.start(now);
      osc.stop(now + 0.36);
    } catch (err) {
      console.warn("Audio chime error:", err);
    }
  }

  // ============================================================
  // API CLIENT COMMUNICATION
  // ============================================================
  async setMode(mode) {
    try {
      const res = await fetch('/api/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
      });
      const data = await res.json();
      this.updateModeButtons(data.mode);
    } catch (err) {
      console.warn("Error changing mode:", err);
    }
  }

  async sendAction(action) {
    this.initAudio(); // user interaction unlocks web audio
    try {
      await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
    } catch (err) {
      console.warn("Error sending action:", err);
    }
  }

  updateModeButtons(activeMode) {
    [this.elements.btnModeReplay, this.elements.btnModeSim, this.elements.btnModeHw].forEach(btn => {
      if (btn.getAttribute('data-mode') === activeMode) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
    this.elements.valActiveMode.textContent = activeMode;
  }

  startPolling() {
    const poll = async () => {
      try {
        const res = await fetch('/api/status');
        if (res.ok) {
          const state = await res.json();
          this.applyState(state);
        }
      } catch (err) {
        // Server might be busy or restarting
      } finally {
        setTimeout(poll, this.pollInterval);
      }
    };
    poll();
  }

  // ============================================================
  // STATE MANAGEMENT & DASHBOARD UPDATE
  // ============================================================
  applyState(state) {
    // 1. Update Mode
    this.updateModeButtons(state.mode || 'REPLAY');

    // 2. Hardware Badges
    this.elements.valBleStatus.textContent = state.npg_status || (state.mode === 'HARDWARE' ? 'CONNECTED' : 'SIMULATOR');
    this.elements.valDroneStatus.textContent = state.drone_status || 'UDP READY';

    // 3. Numeric RMS values
    const leftRms = Number(state.left_rms || 0);
    const rightRms = Number(state.right_rms || 0);
    const threshold = Number(state.left_threshold || 43.3);

    this.elements.valLeftRms.textContent = leftRms.toFixed(1);
    this.elements.valRightRms.textContent = rightRms.toFixed(1);

    // Max scale ~ 120 uV
    const leftPct = Math.min(100, Math.max(3, (leftRms / 120) * 100));
    const rightPct = Math.min(100, Math.max(3, (rightRms / 120) * 100));
    this.elements.barLeftFill.style.width = `${leftPct}%`;
    this.elements.barRightFill.style.width = `${rightPct}%`;

    // 4. Threshold Markers position
    const threshPct = Math.min(100, (threshold / 120) * 100);
    document.getElementById('marker-left-thresh').style.left = `${threshPct}%`;
    document.getElementById('marker-right-thresh').style.left = `${threshPct}%`;
    document.getElementById('lbl-threshold').textContent = `${threshold.toFixed(1)} µV`;

    // Push into history buffers for Canvas oscilloscope
    this.historyLeft.push(leftRms);
    this.historyRight.push(rightRms);
    if (this.historyLeft.length > this.maxDataPoints) {
      this.historyLeft.shift();
      this.historyRight.shift();
    }
    this.historyThreshold = threshold;

    // 5. Contraction Status Badges & Glows
    const leftActive = leftRms >= threshold;
    const rightActive = rightRms >= threshold;
    const isMuscleActivated = state.muscle_activated || leftActive || rightActive;

    this.elements.cardLeft.classList.toggle('active', leftActive);
    this.elements.cardRight.classList.toggle('active', rightActive);
    this.elements.badgeLeft.textContent = leftActive ? 'CONTRACTED' : 'RESTING';
    this.elements.badgeLeft.className = `muscle-status-badge ${leftActive ? 'contracted' : ''}`;
    this.elements.badgeRight.textContent = rightActive ? 'CONTRACTED' : 'RESTING';
    this.elements.badgeRight.className = `muscle-status-badge ${rightActive ? 'contracted' : ''}`;

    // 6. Sound alert trigger on activation edge
    if (isMuscleActivated && !this.lastMuscleActive) {
      this.playTakeoffAlert();
    }
    this.lastMuscleActive = isMuscleActivated;

    // 7. HERO BANNER UPDATE (The Key Requirement!)
    if (isMuscleActivated) {
      this.elements.banner.className = 'readiness-banner state-activated';
      
      let detailMsg = '';
      if (leftActive && rightActive) {
        detailMsg = 'Dual Forearm Contraction Detected &bull; Emergency Brake / Altitude Hold Armed';
        this.elements.headline.textContent = '🚀 MUSCLE ACTIVATED — DRONE IS READY TO TAKE OFF!';
      } else if (leftActive) {
        detailMsg = `Left Muscle Contraction (${leftRms.toFixed(1)} µV) &bull; Yaw/Roll Left Dynamic Takeoff Ready`;
        this.elements.headline.textContent = '🚀 MUSCLE ACTIVATED — DRONE IS READY TO TAKE OFF!';
      } else if (rightActive) {
        detailMsg = `Right Muscle Contraction (${rightRms.toFixed(1)} µV) &bull; Yaw/Roll Right Dynamic Takeoff Ready`;
        this.elements.headline.textContent = '🚀 MUSCLE ACTIVATED — DRONE IS READY TO TAKE OFF!';
      }
      this.elements.subtext.innerHTML = detailMsg;
    } else {
      this.elements.banner.className = 'readiness-banner state-relaxed';
      this.elements.headline.textContent = 'WAITING FOR MUSCLE ACTIVATION...';
      this.elements.subtext.textContent = 'Contract left or right forearm muscle to trigger drone flight sequence';
    }

    // 8. Flight State Pill & Arming
    const droneState = state.drone_state || 'STANDBY';
    this.elements.flightStateText.textContent = droneState;

    this.isArmed = state.is_armed || false;
    this.elements.lblArmedTag.textContent = this.isArmed ? 'ARMED' : 'DISARMED';
    this.elements.lblArmedTag.className = `flight-mode-tag ${this.isArmed ? 'armed' : ''}`;
    this.elements.btnToggleArm.textContent = this.isArmed ? 'DISARM DRONE' : 'ARM DRONE';
    this.elements.btnToggleArm.className = `btn btn-arm ${this.isArmed ? 'armed' : ''}`;

    // 9. Flight Telemetry & Attitude Targets
    const cmd = state.command || 'STOP';
    this.elements.valTelemCmd.textContent = cmd;

    // Attitude Target Calculation
    if (cmd === 'LEFT') {
      this.droneTargetRoll = -22; // Tilt Left
    } else if (cmd === 'RIGHT') {
      this.droneTargetRoll = 22; // Tilt Right
    } else {
      this.droneTargetRoll = 0;
    }

    if (isMuscleActivated || droneState === 'TAKEOFF' || droneState === 'AIRBORNE' || droneState === 'READY_TO_TAKEOFF') {
      this.droneTargetAlt = 1.2; // Altitude in meters
      const thrustPct = isMuscleActivated ? 78 : 65;
      this.elements.valThrust.textContent = `${thrustPct}%`;
      this.elements.valTelemPower.textContent = `${Math.round(thrustPct * 450)} PWM`;
      document.documentElement.style.setProperty('--rotor-speed', '0.08s'); // Rapid spinning
      this.elements.thrustWash.style.opacity = '1';
      this.elements.droneCoreLed.style.backgroundColor = '#10b981';
      this.elements.droneCoreLed.style.boxShadow = '0 0 14px #10b981';
    } else {
      this.droneTargetAlt = 0;
      this.elements.valThrust.textContent = '0%';
      this.elements.valTelemPower.textContent = '0 PWM';
      document.documentElement.style.setProperty('--rotor-speed', '0s'); // Idle
      this.elements.thrustWash.style.opacity = '0';
      this.elements.droneCoreLed.style.backgroundColor = this.isArmed ? '#f59e0b' : '#00f0ff';
      this.elements.droneCoreLed.style.boxShadow = `0 0 10px ${this.isArmed ? '#f59e0b' : '#00f0ff'}`;
    }
  }

  // ============================================================
  // ANIMATION LOOP (Smoothed 60fps Visualizer & Oscilloscope)
  // ============================================================
  startAnimationLoop() {
    const loop = () => {
      this.updateDroneRig();
      this.drawOscilloscope();
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  updateDroneRig() {
    // Smooth interpolation (lerp)
    this.droneRoll += (this.droneTargetRoll - this.droneRoll) * 0.12;
    this.droneAltitude += (this.droneTargetAlt - this.droneAltitude) * 0.08;

    const liftPixels = this.droneAltitude * 24; // Upward translation
    this.elements.droneRig.style.transform = `translateY(-${liftPixels}px) rotate(${this.droneRoll}deg)`;

    this.elements.valRoll.textContent = `${this.droneRoll.toFixed(1)}°`;
    this.elements.valAlt.textContent = `${this.droneAltitude.toFixed(1)} m`;
  }

  drawOscilloscope() {
    const w = this.canvas.width;
    const h = this.canvas.height;
    const ctx = this.ctx;

    // Clear background
    ctx.fillStyle = '#040711';
    ctx.fillRect(0, 0, w, h);

    // Draw Grid
    ctx.strokeStyle = 'rgba(0, 240, 255, 0.06)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let x = 0; x < w; x += 40) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
    }
    for (let y = 0; y < h; y += 30) {
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
    }
    ctx.stroke();

    // Max scale 120 uV
    const maxVal = 120;
    const getY = (val) => h - (Math.min(maxVal, Math.max(0, val)) / maxVal) * (h - 20) - 10;

    // Draw Threshold Line
    const threshY = getY(this.historyThreshold);
    ctx.save();
    ctx.strokeStyle = '#f59e0b';
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(0, threshY);
    ctx.lineTo(w, threshY);
    ctx.stroke();

    ctx.fillStyle = '#f59e0b';
    ctx.font = '10px JetBrains Mono';
    ctx.fillText(`TRIGGER ${this.historyThreshold.toFixed(1)} µV`, 10, threshY - 6);
    ctx.restore();

    // Helper to draw signal line
    const drawTrace = (data, color, glowColor) => {
      ctx.save();
      ctx.strokeStyle = color;
      ctx.shadowColor = glowColor;
      ctx.shadowBlur = 8;
      ctx.lineWidth = 2.5;
      ctx.beginPath();

      const step = w / (this.maxDataPoints - 1);
      for (let i = 0; i < data.length; i++) {
        const x = i * step;
        const y = getY(data[i]);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.restore();
    };

    // Draw Left Channel (Cyan)
    drawTrace(this.historyLeft, '#00f0ff', 'rgba(0, 240, 255, 0.6)');

    // Draw Right Channel (Purple)
    drawTrace(this.historyRight, '#c084fc', 'rgba(192, 132, 252, 0.6)');
  }
}

// Instantiate on DOM load
window.addEventListener('DOMContentLoaded', () => {
  window.avionicsDeck = new AvionicsDeck();
});
