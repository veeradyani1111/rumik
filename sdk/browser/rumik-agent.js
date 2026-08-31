import { LiveKitBridge } from "./livekit-bridge.js";


const noop = () => {};


export function buildSessionPayload(config) {
  const tools = Object.entries(config.tools ?? {}).map(([name, tool]) => ({
    name,
    description: tool.description,
    parameters: tool.parameters ?? {},
  }));
  return {
    prompt: config.prompt,
    vision: config.vision ?? false,
    ...(config.voice ? { voice: config.voice } : {}),
    tools,
    options: config.options ?? {},
  };
}


export async function runToolHandler(tools, call) {
  const handler = tools?.[call.name]?.handler;
  if (typeof handler !== "function") {
    return { type: "tool_result", id: call.id, result: { error: "unknown_tool" } };
  }
  try {
    const result = await handler(call.args ?? {});
    return { type: "tool_result", id: call.id, result };
  } catch (error) {
    return {
      type: "tool_result",
      id: call.id,
      result: { error: error instanceof Error ? error.message : String(error) },
    };
  }
}


class AgentController {
  constructor(config, dependencies = {}) {
    if (!config?.session) throw new TypeError("session URL is required");
    if (!config?.prompt?.trim()) throw new TypeError("prompt is required");
    this.config = config;
    const fetchImpl = dependencies.fetch ?? globalThis.fetch;
    this.fetch = (...args) => fetchImpl.call(globalThis, ...args);
    this.document = dependencies.document ?? globalThis.document;
    this.Bridge = dependencies.Bridge ?? LiveKitBridge;
    this.console = dependencies.console ?? globalThis.console ?? { info: noop, warn: noop, error: noop };
    this.bridge = null;
    this.elements = {};
    this.stopped = false;
  }

  async mount(target) {
    const root = typeof target === "string" ? this.document.querySelector(target) : target;
    if (!root) throw new TypeError("mount target was not found");
    this._render(root);
    this._state("connecting");
    this._emit({ type: "connecting" });

    try {
      const response = await this.fetch(this.config.session, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildSessionPayload(this.config)),
      });
      const session = await response.json();
      if (!response.ok) throw Object.assign(new Error(session.message ?? "Session failed"), session);
      this._log("info", "session created", { room: session.room });
      this._emit({ type: "session_started", room: session.room });

      this.bridge = new this.Bridge({
        onState: (state) => this._state(state),
        onData: (payload) => this._onData(payload),
        onAudioTrack: (track) => {
          this._log("info", "agent audio track subscribed");
          this._emit({ type: "agent_audio" });
          track.attach(this.elements.audio);
        },
      });
      await this.bridge.connect(session.url, session.token);
      this._log("info", "connected to room", { room: session.room });

      try {
        await this.bridge.publishMicrophone();
        this._log("info", "microphone published");
        this._emit({ type: "mic_started" });
      } catch (cause) {
        const error = Object.assign(new Error("Microphone permission is required"), {
          code: "mic_required",
          cause,
        });
        this._error(error);
        await this.stop();
        throw error;
      }

      if (this.config.vision) {
        try {
          const camera = await this.bridge.publishCamera();
          camera.attach(this.elements.video);
          this._log("info", "camera published and attached");
          this._note("");
          this._emit({ type: "camera_started" });
        } catch (cause) {
          this._cameraUnavailable(cause);
        }
      }

      this._state("live");
      this._emit({ type: "live" });
      return this;
    } catch (error) {
      if (error.code !== "mic_required") this._error(error);
      throw error;
    }
  }

  async stop() {
    if (this.stopped) return;
    this.stopped = true;
    await this.bridge?.disconnect();
    this._state("ended");
    this._emit({ type: "ended" });
  }

  async _onData(payload) {
    this._emit(payload);
    if (payload?.type !== "tool_call") return;
    this._log("info", "tool call", { name: payload.name });
    const result = await runToolHandler(this.config.tools ?? {}, payload);
    await this.bridge.sendData(result);
  }

  _render(root) {
    const shell = this.document.createElement("section");
    shell.className = "rumik-agent";
    const video = this.document.createElement("video");
    video.className = "rumik-agent__preview";
    video.autoplay = true;
    video.muted = true;
    video.playsInline = true;
    video.hidden = !this.config.vision;
    const audio = this.document.createElement("audio");
    audio.autoplay = true;
    const note = this.document.createElement("p");
    note.className = "rumik-agent__note";
    note.hidden = true;
    const status = this.document.createElement("p");
    status.className = "rumik-agent__status";
    shell.append(video, audio, note, status);
    root.replaceChildren(shell);
    this.elements = { shell, video, audio, note, status };
  }

  _state(state) {
    const label = STATUS_LABELS[state] ?? state;
    if (this.elements.status) this.elements.status.textContent = label;
    (this.config.onState ?? noop)(state);
  }

  _note(text) {
    const el = this.elements.note;
    if (!el) return;
    el.textContent = text;
    el.hidden = !text;
  }

  _cameraUnavailable(cause) {
    const reason = cause instanceof Error ? cause.message : String(cause ?? "");
    this._log("warn", "camera unavailable", { reason });
    this._note("Camera is blocked or unavailable. Allow camera access, then restart. KYC needs the camera to read your card.");
    this._emit({ type: "camera_unavailable", reason });
  }

  _emit(event) {
    try {
      (this.config.onEvent ?? noop)(event);
    } catch (error) {
      this._log("error", "onEvent handler threw", { error: String(error) });
    }
  }

  _log(level, message, detail) {
    const fn = this.console[level] ?? this.console.info ?? noop;
    fn.call(this.console, `[rumik-agent] ${message}`, detail ?? "");
  }

  _error(error) {
    this._log("error", "session error", { message: error?.message, code: error?.code });
    (this.config.onError ?? noop)(error);
    this._state("error");
  }
}


const STATUS_LABELS = {
  connecting: "Connecting…",
  live: "Live — the agent is listening",
  reconnecting: "Reconnecting…",
  ended: "Session ended",
  error: "Something went wrong",
};


export const RumikAgent = {
  create(config, dependencies) {
    return new AgentController(config, dependencies);
  },
};
